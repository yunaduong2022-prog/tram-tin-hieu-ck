#!/usr/bin/env python3
"""Backtest các setup của "Phân loại trạng thái" (setups.py) trên toàn bộ dữ liệu, ghi kết quả ra data/ để app đọc.

Thay cho bảng số cứng SETUP_BT trong app.py: chạy lại script này mỗi khi có dữ liệu mới (hoặc mỗi tuần) là số liệu tự cập nhật.

Quy tắc giao dịch (giống mô tả cũ trong app, chi phí lấy từ engine.BT_COST):
  - Tín hiệu: BOTTOM / BASE_HL / BREAKOUT = nến bùng nổ đầu tiên; TREND / RANGE / WEAK = nến đầu tiên chuyển sang trạng thái đó.
  - Vào ở giá MỞ CỬA phiên kế tiếp (+ trượt giá, làm tròn lên bước giá). Phiên mở cửa khóa trần: không mua được (bỏ, có đếm).
  - Cắt lỗ theo setups.choose_stop() tính từ điểm vào tham chiếu (đỉnh nền với bùng nổ, giá đóng cửa với TREND).
  - Thoát khi chạm cắt lỗ (gap xuống thì khớp ở giá mở cửa), hoặc đóng cửa dưới Supertrend (thoát ở mở cửa phiên sau,
    chỉ áp khi Supertrend đã từng tăng kể từ lúc vào), hoặc hết MAX_HOLD phiên.
  - T+2: từ lúc mua, 2 phiên đầu không bán được; cắt lỗ chạm trong thời gian đó thì bán ở mở cửa phiên đầu tiên bán được.
  - Chi phí: phí 0,15%/chiều + thuế bán 0,1% + trượt giá 0,1%/chiều. R = lãi ròng / (giá vào − cắt lỗ).
  - BASE (mức nền) = vào ngẫu nhiên, cùng cách cắt lỗ và thoát, để biết setup có thật sự hơn mua bừa hay không.

Chống tự lừa mình (điều backtest cũ chưa làm):
  - Tách IS (trước SPLIT_DATE) và OOS (từ SPLIT_DATE): tham số chọn trên giai đoạn nào thì phải kiểm trên giai đoạn còn lại.
  - Báo cả trung vị, profit factor, drawdown tối đa (đơn vị R) và khoảng tin cậy 95% của R trung bình, vì lợi nhuận đến từ vài lệnh lớn.
  - Tách theo chế độ thị trường (VNINDEX trên / dưới MA200 tại ngày tín hiệu).
  - Báo "độ lệch sống sót": số mã trong dữ liệu đã ngừng giao dịch (nếu 0 thì mẫu chỉ có mã còn niêm yết, kết quả có xu hướng lạc quan).

Kết quả:
  data/setup_stats.csv        thống kê theo (setup, giai đoạn)  <- app đọc file này
  data/setup_trades.csv       từng lệnh (để kiểm tra / vẽ lại)
  data/setup_stats_meta.json  ngày chạy, khoảng dữ liệu, số mã, tham số

    python backtest_setups.py
    python backtest_setups.py --split 2024-01-01 --max-hold 60
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import engine as E
import setups as SU
from telegram_alert import SKIP

CSV_PATH = "data/eod_prices.csv"
OUT_STATS, OUT_TRADES, OUT_META = "data/setup_stats.csv", "data/setup_trades.csv", "data/setup_stats_meta.json"

MAX_HOLD = 60                 # tối đa 60 phiên
LOCK_BARS = 2                 # T+2
SPLIT_DATE = "2024-01-01"     # IS: trước ngày này, OOS: từ ngày này
MIN_PRICE, MIN_VOL = 5.0, 100_000      # lọc thanh khoản như setups_scan (giá & khối lượng trung vị 20 phiên)
WARMUP = 260                  # cần đủ lịch sử cho Kijun 129 và đỉnh 250 phiên
RANDOM_SEED = 7

FRESH = ("BOTTOM", "BASE_HL", "BREAKOUT")
STATE_SETUPS = ("TREND", "RANGE", "WEAK")
SETUPS = FRESH + STATE_SETUPS
LABEL = {**SU.LABEL, "BASE": "Vào ngẫu nhiên (mức nền)"}
REGIME_COL = "Chế độ VNI"


# ------------------------------------------------------------------ tín hiệu
def signal_events(f: pd.DataFrame) -> dict[str, np.ndarray]:
    """Chỉ số nến báo tín hiệu lần đầu của từng setup (không lặp lại khi trạng thái còn hiệu lực)."""
    ev: dict[str, np.ndarray] = {}
    for name, col in (("BOTTOM", "bottom"), ("BASE_HL", "base_hl"), ("BREAKOUT", "breakout")):
        s = f[col].fillna(False).astype(bool)
        # nến bùng nổ đầu tiên của cụm (không có bùng nổ cùng loại trong ACTIVE_BARS nến trước đó)
        prev = s.shift(1).rolling(SU.ACTIVE_BARS, min_periods=1).max().fillna(0).astype(bool)
        ev[name] = np.flatnonzero((s & ~prev).to_numpy())
    cls = SU.classify(f)
    for name in STATE_SETUPS:
        now = (cls == name).to_numpy()
        ev[name] = np.flatnonzero(now & ~np.r_[False, now[:-1]])
    return ev


def entry_reference(f: pd.DataFrame, i: int, setup: str) -> tuple[float, float]:
    """(điểm vào tham chiếu, cắt lỗ) tại nến báo i, giống setups.plan()."""
    r = f.iloc[i]
    c = float(r["c"])
    if setup in FRESH:
        ref = float(r["res25"]) if pd.notna(r["res25"]) else c
        kind = setup
    else:
        ref, kind = c, "TREND"      # TREND / RANGE / WEAK / BASE: cắt lỗ theo ATR (+ Supertrend nếu có), tính từ giá đóng cửa
        if setup != "TREND":
            kind = "OTHER"
    return ref, SU.choose_stop(ref, r, kind)


# ------------------------------------------------------------------ mô phỏng một lệnh
def simulate(g: pd.DataFrame, f: pd.DataFrame, i: int, stop: float, cost=None, max_hold: int = MAX_HOLD,
             lock_bars: int = LOCK_BARS) -> dict | None:
    """Mô phỏng lệnh mua báo ở nến i (vào mở cửa nến i+1). Trả dict kết quả, hoặc None nếu không khớp được.
    Dùng chung cho backtest và theo dõi tín hiệu thực (forward_log.py) để hai bên đo bằng cùng một thước."""
    cfg = {**E.BT_COST, **(cost or {})}
    op, hi, lo, cl = (pd.to_numeric(g[k], errors="coerce").to_numpy(float) for k in ("Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa"))
    st_up = f["st_up"].to_numpy(bool)
    n = len(g)
    e = i + 1
    if e >= n:
        return {"status": "chưa vào", "entry_i": None}
    # phiên mở cửa khóa trần: nến một giá, tăng gần hết biên độ -> không mua được
    if hi[e] == lo[e] and e >= 1 and cl[e] / cl[e - 1] - 1 >= 0.9 * cfg["limit"]:
        return {"status": "khóa trần", "entry_i": e}
    entry = E.tick_round(op[e] * (1 + cfg["slip"]), up=True)
    if not (entry > stop):
        return {"status": "gap dưới cắt lỗ", "entry_i": e}
    risk = entry - stop
    end = min(n, e + max_hold)
    exit_px, exit_i, reason, pending, armed = None, None, "", False, False
    for j in range(e, end):
        k = j - e
        locked_day = k < lock_bars
        if not locked_day and pending:
            exit_px, exit_i, reason = op[j], j, "cắt lỗ (T+2)"
            break
        if locked_day:
            if lo[j] <= stop:
                pending = True
            armed = armed or st_up[j]
            continue
        if lo[j] <= stop:
            exit_px, exit_i, reason = min(op[j], stop), j, "cắt lỗ"
            break
        armed = armed or st_up[j]
        if armed and not st_up[j] and j + 1 < end:
            exit_px, exit_i, reason = op[j + 1], j + 1, "thủng Supertrend"
            break
    open_trade = False
    if exit_px is None:
        if end - e < max_hold and end == n:      # chưa đủ phiên để kết luận
            open_trade = True
            exit_px, exit_i, reason = cl[end - 1], end - 1, "đang mở"
        else:
            exit_px, exit_i, reason = cl[end - 1], end - 1, "hết hạn"
    exit_net = E.tick_round(exit_px * (1 - cfg["slip"]), up=False)
    costs = cfg["fee"] * (entry + exit_net) + cfg["sell_tax"] * exit_net
    pnl = exit_net - entry - costs
    return {"status": "mở" if open_trade else "đóng", "entry_i": e, "exit_i": exit_i, "entry": entry, "stop": stop,
            "exit": exit_net, "reason": reason, "R": pnl / risk, "ret_pct": pnl / entry * 100,
            "hold": exit_i - e + 1, "risk_pct": risk / entry * 100}


# ------------------------------------------------------------------ chạy toàn bộ
def load_prices(path: str) -> pd.DataFrame:
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    return raw


def market_regime(raw: pd.DataFrame) -> pd.Series | None:
    """Series theo ngày: 'Tăng' nếu VNINDEX đóng cửa > MA200, ngược lại 'Giảm'. None nếu dữ liệu không có chỉ số."""
    v = raw[raw["Mã"].str.upper().isin(E.INDEX_CODES)]
    if v.empty:
        return None
    v = v.sort_values("Ngày").drop_duplicates("Ngày").set_index("Ngày")["Giá đóng cửa"]
    ma = v.rolling(200, min_periods=150).mean()
    out = pd.Series(np.where(v > ma, "Tăng", "Giảm"), index=v.index)
    return out.where(ma.notna())


def liquid_ok(g: pd.DataFrame, i: int) -> bool:
    """Thanh khoản tại nến i: giá & khối lượng trung vị 20 phiên liền trước (không nhìn tương lai)."""
    w = g.iloc[max(0, i - 19):i + 1]
    return (pd.to_numeric(w["Giá đóng cửa"], errors="coerce").median() >= MIN_PRICE
            and pd.to_numeric(w["Khối lượng khớp lệnh"], errors="coerce").median() >= MIN_VOL)


def run(path: str = CSV_PATH, split: str = SPLIT_DATE, max_hold: int = MAX_HOLD) -> tuple[pd.DataFrame, dict]:
    raw = load_prices(path)
    regime = market_regime(raw)
    latest = pd.Timestamp(raw["Ngày"].max())
    rng = np.random.default_rng(RANDOM_SEED)
    trades, skipped, n_codes, dead = [], {}, 0, []
    per_code_events: dict[str, dict] = {}
    for code, g in raw.groupby("Mã"):
        if str(code).upper() in SKIP or str(code).upper() in E.INDEX_CODES:
            continue
        g = g.sort_values("Ngày").reset_index(drop=True)
        if len(g) < WARMUP + max_hold // 2:
            continue
        n_codes += 1
        if g["Ngày"].iat[-1] < latest - pd.Timedelta(days=7):
            dead.append(code)
        try:
            f = SU.features(g)
        except Exception as ex:                       # một mã lỗi không làm hỏng cả lần chạy
            print(f"  bỏ {code}: {ex}", file=sys.stderr)
            continue
        ev = signal_events(f)
        for setup in SETUPS:
            for i in ev[setup]:
                per_code_events.setdefault(code, {}).setdefault(setup, []).append(int(i))
                if i < WARMUP or not liquid_ok(g, i):
                    continue
                ref, stop = entry_reference(f, int(i), setup)
                res = simulate(g, f, int(i), stop, max_hold=max_hold)
                if res is None or res["status"] not in ("đóng",):
                    if res is not None and res["status"] != "mở":
                        skipped[res["status"]] = skipped.get(res["status"], 0) + 1
                    continue
                trades.append({"Mã": code, "Setup": setup, "Ngày tín hiệu": g["Ngày"].iat[i], "Ngày vào": g["Ngày"].iat[res["entry_i"]],
                               "Ngày ra": g["Ngày"].iat[res["exit_i"]], **{k: res[k] for k in ("entry", "stop", "exit", "reason", "R", "ret_pct", "hold", "risk_pct")}})
        # ứng viên "vào ngẫu nhiên": mọi nến đủ thanh khoản, chọn mẫu sau
        per_code_events.setdefault(code, {})["_g"] = (g, f)
    # mức nền: lấy ngẫu nhiên số lệnh bằng tổng số lệnh setup, phân bổ đều theo mã (cùng cắt lỗ và thoát)
    target_n = max(len(trades), 1)
    pool = []
    for code, d in per_code_events.items():
        g, f = d["_g"]
        ok = np.arange(WARMUP, len(g) - 2)
        if len(ok):
            pool.append((code, g, f, ok))
    per = max(target_n // max(len(pool), 1), 5)
    base_rows = []
    for code, g, f, ok in pool:
        pick = rng.choice(ok, size=min(per, len(ok)), replace=False)
        for i in sorted(pick):
            i = int(i)
            if not liquid_ok(g, i):
                continue
            ref, stop = entry_reference(f, i, "BASE")
            res = simulate(g, f, i, stop, max_hold=max_hold)
            if res is None or res["status"] != "đóng":
                continue
            base_rows.append({"Mã": code, "Setup": "BASE", "Ngày tín hiệu": g["Ngày"].iat[i], "Ngày vào": g["Ngày"].iat[res["entry_i"]],
                              "Ngày ra": g["Ngày"].iat[res["exit_i"]], **{k: res[k] for k in ("entry", "stop", "exit", "reason", "R", "ret_pct", "hold", "risk_pct")}})
    t = pd.DataFrame(trades + base_rows)
    if t.empty:
        raise SystemExit("Không có lệnh nào: kiểm tra dữ liệu.")
    t["Ngày tín hiệu"] = pd.to_datetime(t["Ngày tín hiệu"])
    t["Năm"] = t["Ngày tín hiệu"].dt.year
    t["Giai đoạn"] = np.where(t["Ngày tín hiệu"] < pd.Timestamp(split), "IS", "OOS")
    if regime is not None:
        t[REGIME_COL] = t["Ngày tín hiệu"].map(regime)
    else:
        t[REGIME_COL] = np.nan
    meta = {"chạy lúc": datetime.now().strftime("%Y-%m-%d %H:%M"), "dữ liệu từ": str(raw["Ngày"].min().date()), "dữ liệu đến": str(latest.date()),
            "số mã": n_codes, "số mã đã ngừng giao dịch": len(dead), "ngày tách IS/OOS": split, "max_hold": max_hold,
            "chi phí": E.BT_COST, "lệnh bị loại": skipped, "seed": RANDOM_SEED}
    return t, meta


# ------------------------------------------------------------------ thống kê
def _stats(r: pd.Series, ret: pd.Series, hold: pd.Series) -> dict:
    n = len(r)
    if n == 0:
        return {}
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf
    eq = r.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    se = r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    top = r.sort_values(ascending=False).head(max(1, int(round(n * 0.05))))
    return {"Số lệnh": n, "Lãi TB %": round(ret.mean(), 2), "Lãi trung vị %": round(ret.median(), 2), "Thắng %": round(len(wins) / n * 100, 1),
            "R TB": round(r.mean(), 3), "R trung vị": round(r.median(), 3), "R TB (CI95 thấp)": round(r.mean() - 1.96 * se, 3) if n > 1 else np.nan,
            "R TB (CI95 cao)": round(r.mean() + 1.96 * se, 3) if n > 1 else np.nan, "Profit factor": round(pf, 2) if np.isfinite(pf) else np.nan,
            "MDD (R)": round(float(abs((eq - peak).min())), 2), "Giữ TB (phiên)": round(hold.mean(), 1),
            "R TB bỏ 5% lệnh tốt nhất": round(float(r.drop(top.index).mean()), 3) if n > len(top) else np.nan}


def summarize(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    t = t.sort_values("Ngày vào")
    groups = [("ALL", t)] + [(p, t[t["Giai đoạn"] == p]) for p in ("IS", "OOS")]
    groups += [(f"Năm {y}", t[t["Năm"] == y]) for y in sorted(t["Năm"].unique())]
    groups += [(f"VNI {x}", t[t[REGIME_COL] == x]) for x in ("Tăng", "Giảm")]
    for setup in (*SETUPS, "BASE"):
        ts = t[t["Setup"] == setup]
        for name, _ in groups:
            sub = ts if name == "ALL" else ts[ts["Giai đoạn"] == name] if name in ("IS", "OOS") else \
                ts[ts["Năm"] == int(name[4:])] if name.startswith("Năm ") else ts[ts[REGIME_COL] == name[4:]]
            if sub.empty:
                continue
            rows.append({"Setup": setup, "Nhãn": LABEL.get(setup, setup), "Nhóm": name, **_stats(sub["R"], sub["ret_pct"], sub["hold"])})
    out = pd.DataFrame(rows)
    # đối chiếu với mức nền cùng nhóm: setup hơn nền bao nhiêu R, có ý nghĩa không (CI không chạm R nền)
    base = out[out["Setup"] == "BASE"].set_index("Nhóm")["R TB"]
    out["R hơn nền"] = [round(r - base.get(g, np.nan), 3) if s != "BASE" else np.nan for s, g, r in zip(out["Setup"], out["Nhóm"], out["R TB"])]
    out["Vượt nền (CI95)"] = [bool(lo > base.get(g, np.inf)) if s != "BASE" and pd.notna(lo) else False
                              for s, g, lo in zip(out["Setup"], out["Nhóm"], out["R TB (CI95 thấp)"])]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--split", default=SPLIT_DATE, help="ngày tách IS/OOS (YYYY-MM-DD)")
    ap.add_argument("--max-hold", type=int, default=MAX_HOLD)
    a = ap.parse_args()
    t, meta = run(a.csv, a.split, a.max_hold)
    stats = summarize(t)
    Path(OUT_STATS).parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(OUT_STATS, index=False, encoding="utf-8-sig")
    t.drop(columns=["Năm"]).to_csv(OUT_TRADES, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    Path(OUT_META).write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    show = stats[stats["Nhóm"].isin(["ALL", "IS", "OOS"])][["Setup", "Nhóm", "Số lệnh", "Lãi TB %", "Thắng %", "R TB", "R hơn nền", "Vượt nền (CI95)", "Profit factor"]]
    print(show.to_string(index=False))
    print(f"\nĐã ghi {OUT_STATS} ({len(stats)} dòng), {OUT_TRADES} ({len(t)} lệnh), {OUT_META}")
    if meta["số mã đã ngừng giao dịch"] == 0:
        print("Lưu ý: dữ liệu không có mã nào đã ngừng giao dịch nên kết quả có thể lạc quan (độ lệch sống sót).")


if __name__ == "__main__":
    main()
