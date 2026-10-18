#!/usr/bin/env python3
"""Lấy dữ liệu OHLCV ngày CUỐI PHIÊN cho cả rổ mã, ghi vào data/eod_prices.csv (cập nhật tăng dần).

Chạy một lần mỗi ngày sau khi thị trường đóng cửa (GitHub Actions: .github/workflows/eod.yml),
thay cho việc app tự gọi nguồn dữ liệu liên tục. App chỉ đọc file CSV nên không bị giới hạn tần suất.

- Mỗi mã 1 yêu cầu/ngày. Thử lần lượt các nguồn vnstock: vci -> kbs -> vnd (đổi bằng --sources).
- Cập nhật tăng dần: lấy lại ~14 ngày gần nhất; nếu giá cũ lệch giá mới (đã điều chỉnh cổ tức/chia tách)
  thì tải lại toàn bộ lịch sử của mã đó để chuỗi giá không bị đứt đoạn.
- Nếu chạy khi phiên chưa đóng (trước 15:10 giờ VN), nến của hôm nay bị loại bỏ để chỉ giữ dữ liệu đã chốt.
- Ghi data/eod_meta.json (thời điểm cập nhật, nguồn đã dùng, mã lỗi) để app hiển thị.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import pandas as pd
import requests

import realtime_data as RD
import watchlist as WL

TZ = "Asia/Ho_Chi_Minh"
CSV_PATH = "data/eod_prices.csv"
META_PATH = "data/eod_meta.json"
EXTRA_PATH = "data/extra_symbols.txt"
DATE_FMT = "%d/%m/%Y"          # cùng định dạng file CafeF để engine.clean_raw đọc không nhầm ngày/tháng
COLS = ["Mã", "Ngày", "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]
PRICE = COLS[2:6]
VOL = COLS[6]
CLOSE_TIME = (15, 10)          # sau 15:10 coi như đã đóng cửa mọi sàn (HOSE/HNX/UPCOM)
RATE_WAIT = 60                 # giây chờ khi nguồn báo giới hạn tần suất


class Fatal(Exception):
    """Hết hạn mức ngày/tháng: dừng hẳn, không thử tiếp."""


def _is_fatal(e: Exception) -> bool:
    code, text = str(getattr(e, "code", "")).upper(), str(e).lower()
    return "DAY_LIMIT" in code or "MONTH_LIMIT" in code or "hết hạn mức" in text


def _is_rate(e: Exception) -> bool:
    code, text = str(getattr(e, "code", "")).upper(), str(e).lower()
    return "RATE_LIMIT" in code or any(k in text for k in ("429", "too many", "rate limit", "ratelimit", "giới hạn tần suất"))


# ------------------------------------------------------------------ HÀM GỬI TELEGRAM
def send_telegram_alert(message):
    """Hàm gửi tin nhắn tóm tắt về Telegram"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Chưa cấu hình Secrets Telegram trên GitHub.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Đã gửi thông báo Telegram thành công!")
        else:
            print(f"❌ Lỗi gửi Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Lỗi kết nối Telegram: {e}")


# ------------------------------------------------------------------ CHUẨN HÓA
def normalize(raw: pd.DataFrame, sym: str) -> pd.DataFrame:
    empty = pd.DataFrame(columns=COLS)
    df = RD._rename(raw)
    if df.empty or "Ngày" not in df or any(c not in df for c in PRICE):
        return empty
    t = df["Ngày"]
    if pd.api.types.is_numeric_dtype(t):
        t = pd.to_datetime(t, unit="s" if t.dropna().abs().max() < 1e11 else "ms", errors="coerce", utc=True)
    else:
        t = pd.to_datetime(t, errors="coerce", utc=True)
    out = pd.DataFrame({"Mã": sym, "Ngày": t.dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()})
    for c in PRICE:
        out[c] = pd.to_numeric(df[c], errors="coerce")
    out[VOL] = pd.to_numeric(df[VOL], errors="coerce").fillna(0) if VOL in df else 0.0
    out = out.dropna(subset=["Ngày"] + PRICE)
    out = out[(out[PRICE] > 0).all(axis=1)]
    if out.empty:
        return empty
    if out["Giá đóng cửa"].median() > 1000:      # nguồn trả đồng đầy đủ -> đổi sang nghìn đồng như file CafeF
        out[PRICE] = out[PRICE] / 1000.0
    return out.drop_duplicates("Ngày", keep="last").sort_values("Ngày").reset_index(drop=True)[COLS]


def fetch_one(market, sym: str, start: str, end: str, sources: tuple, accept_empty: bool):
    """Trả về (DataFrame, nguồn). Thử lần lượt các nguồn; chỉ báo lỗi khi mọi nguồn đều lỗi."""
    last_err = None
    for src in sources:
        for attempt in range(3):
            try:
                raw = market.equity(sym).ohlcv(start=start, end=end, source=src)
                df = normalize(raw, sym)
                if df.empty:
                    if accept_empty:
                        return df, src
                    last_err = RuntimeError(f"{src}: không trả dữ liệu")
                    break
                return df, src
            except Exception as e:  # noqa: BLE001
                if _is_fatal(e):
                    raise Fatal(str(e)) from e
                if _is_rate(e) and attempt < 2:
                    print(f"  {sym}/{src}: bị giới hạn tần suất, chờ {RATE_WAIT}s rồi thử lại...", flush=True)
                    time.sleep(RATE_WAIT)
                    continue
                last_err = e
                break
    raise RuntimeError(f"{type(last_err).__name__}: {last_err}")


def price_mismatch(old: pd.DataFrame, new: pd.DataFrame) -> bool:
    """Giá cũ trong file khác giá nguồn trả về cho cùng ngày -> nghi đã điều chỉnh quyền."""
    m = old.merge(new, on="Ngày", suffixes=("_o", "_n"))
    if m.empty:
        return False
    diff = (m["Giá đóng cửa_o"] - m["Giá đóng cửa_n"]).abs()
    return bool(((diff > 0.02) & (diff / m["Giá đóng cửa_o"] > 0.002)).any())


# ------------------------------------------------------------------ KHO DỮ LIỆU
def read_store() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame({c: pd.Series(dtype="datetime64[ns]" if c == "Ngày" else "object" if c == "Mã" else "float64")
                             for c in COLS})
    df = pd.read_csv(CSV_PATH, dtype={"Mã": str})
    df["Ngày"] = pd.to_datetime(df["Ngày"], format=DATE_FMT, errors="coerce")
    for c in PRICE + [VOL]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"])[COLS]


def universe(args) -> list[str]:
    if args.symbols.strip():
        return list(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    vn30, note = WL.fetch_vn30()
    print(f"VN30: {len(vn30)} mã · {note}")
    syms = list(vn30)
    for g in WL.GROUPS.values():
        syms += g
    if not args.no_old:
        syms += WL.OLD_LIST
    if os.path.exists(EXTRA_PATH):
        with open(EXTRA_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0].replace(";", ",")
                syms += [x.strip().upper() for x in line.split(",") if x.strip()]
    return list(dict.fromkeys(s for s in syms if s))


def maybe_login() -> None:
    key = os.getenv("VNSTOCK_API_KEY", "").strip()
    if not key:
        print("Không có VNSTOCK_API_KEY: chạy ở cấp Khách (hạn mức chặt nhất).")
        return
    import vnstock
    for name in ("login", "setup_api_key"):
        fn = getattr(vnstock, name, None)
        if fn:
            try:
                fn(key)
                print("Đã đăng nhập vnstock bằng khóa API.")
                return
            except Exception as e:  # noqa: BLE001
                print(f"Không đăng nhập được vnstock ({type(e).__name__}); tiếp tục ở cấp Khách.")
                return


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Lấy dữ liệu OHLCV cuối phiên và ghi data/eod_prices.csv")
    p.add_argument("--start", default=os.getenv("EOD_START", "2021-01-01"), help="Ngày bắt đầu lịch sử khi tải đầy đủ")
    p.add_argument("--symbols", default="", help="Chỉ lấy các mã này (cách nhau bằng dấu phẩy); bỏ trống = cả rổ")
    p.add_argument("--no-old", action="store_true", help="Không gộp 'Danh mục cũ' trong watchlist.py")
    p.add_argument("--sources", default="vci,kbs,vnd", help="Thứ tự nguồn vnstock thử lần lượt")
    p.add_argument("--sleep", type=float, default=1.0, help="Giây nghỉ giữa hai mã")
    p.add_argument("--overlap-days", type=int, default=14, help="Số ngày lấy lại để phát hiện điều chỉnh giá")
    p.add_argument("--max-minutes", type=float, default=45, help="Dừng nếu chạy quá số phút này")
    p.add_argument("--full", action="store_true", help="Tải lại toàn bộ lịch sử từ --start cho mọi mã")
    p.add_argument("--now", default="", help="Giả lập giờ VN 'YYYY-MM-DD HH:MM' (kiểm thử)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    now = pd.Timestamp(args.now, tz=TZ) if args.now else pd.Timestamp.now(tz=TZ)
    end = now.strftime("%Y-%m-%d")
    session_open = now.weekday() < 5 and (now.hour, now.minute) < CLOSE_TIME
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    try:
        from vnstock import Market
    except ImportError:
        print("Chưa cài vnstock. Chạy: pip install -r requirements-eod.txt")
        return 1
    maybe_login()

    symbols = universe(args)
    sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())
    store = read_store()
    by_sym = {s: g for s, g in store.groupby("Mã")}
    market = Market()
    print(f"Rổ {len(symbols)} mã · kho hiện có {len(by_sym)} mã · nguồn thử: {', '.join(sources)} · "
          f"{'PHIÊN CHƯA ĐÓNG, sẽ bỏ nến hôm nay' if session_open else 'đã sau giờ đóng cửa'}")

    t0, updated, failed, adjusted, used, fatal = time.time(), {}, [], [], {}, None
    for i, sym in enumerate(symbols, 1):
        if time.time() - t0 > args.max_minutes * 60:
            fatal = f"Quá {args.max_minutes:g} phút, dừng ở mã thứ {i}/{len(symbols)}"
            break
        old = by_sym.get(sym)
        try:
            if args.full or old is None or old.empty:
                merged, src = fetch_one(market, sym, args.start, end, sources, accept_empty=False)
            else:
                last = old["Ngày"].max()
                start = (last - pd.Timedelta(days=args.overlap_days)).strftime("%Y-%m-%d")
                new, src = fetch_one(market, sym, start, end, sources, accept_empty=True)
                if new.empty:
                    merged = old
                elif price_mismatch(old, new):
                    merged, src = fetch_one(market, sym, args.start, end, sources, accept_empty=False)
                    adjusted.append(sym)
                else:
                    merged = pd.concat([old[old["Ngày"] < new["Ngày"].min()], new], ignore_index=True)
        except Fatal as e:
            fatal = str(e)
            break
        except Exception as e:  # noqa: BLE001
            failed.append(f"{sym}: {e}")
            print(f"  ✗ {sym}: {e}", flush=True)
            continue
        updated[sym] = merged
        used[src] = used.get(src, 0) + 1
        if i % 20 == 0:
            print(f"  ... {i}/{len(symbols)} mã", flush=True)
        time.sleep(args.sleep)

    skipped = [s for s in symbols if s not in updated and not any(f.startswith(s + ":") for f in failed)]
    if not updated:
        print("Không cập nhật được mã nào." + (f" Lý do: {fatal}" if fatal else ""))
        return 1

    keep = store[~store["Mã"].isin(updated)]
    result = pd.concat(([keep] if len(keep) else []) + list(updated.values()), ignore_index=True)
    result["Ngày"] = pd.to_datetime(result["Ngày"])          # bảo đảm kiểu ngày để ghi đúng định dạng dd/mm/YYYY
    if session_open:
        result = result[result["Ngày"] < now.normalize().tz_localize(None)]
    result = result.drop_duplicates(["Mã", "Ngày"], keep="last").sort_values(["Mã", "Ngày"]).reset_index(drop=True)
    result[PRICE] = result[PRICE].round(2)
    result[VOL] = result[VOL].fillna(0).round(0).astype("int64")
    result[COLS].to_csv(CSV_PATH, index=False, date_format=DATE_FMT)

    latest = result["Ngày"].max()
    n_latest = int((result.groupby("Mã")["Ngày"].max() == latest).sum())
    meta = {"updated_at": now.strftime("%d/%m/%Y %H:%M") + " (giờ VN)", "latest_date": latest.strftime("%Y-%m-%d"),
            "symbols": int(result["Mã"].nunique()), "symbols_on_latest_date": n_latest, "rows": int(len(result)),
            "sources": used, "failed": failed[:50], "skipped": len(skipped), "adjusted": adjusted, "stopped": fatal}
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    line = (f"Xong: {len(updated)}/{len(symbols)} mã cập nhật · ngày mới nhất {latest:%d/%m/%Y} ({n_latest} mã có nến này) · "
            f"nguồn {used} · lỗi {len(failed)} · điều chỉnh giá {len(adjusted)}" + (f" · DỪNG: {fatal}" if fatal else ""))
    print(line)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"### Dữ liệu cuối phiên\n\n{line}\n\n" + ("\n".join(f"- {x}" for x in failed[:20]) if failed else "") + "\n")

    # --- TÍCH HỢP GỬI BÁO CÁO TELEGRAM CUỐI PHIÊN ---
    try:
        if not result.empty:
            # Lọc các mã có tín hiệu dòng tiền chớm vào hoặc bứt phá để gửi thông báo
            msg = f"📊 *TRẠM TÍN HIỆU CK - BÁO CÁO CUỐI PHIÊN*\n"
            msg += f"🗓 Ngày: {now.strftime('%d/%m/%Y')}\n"
            msg += f"📈 Tổng số mã cập nhật thành công: *{len(updated)}/{len(symbols)}*\n\n"
            msg += f"ℹ️ Hệ thống đã hoàn tất quét dữ liệu EOD và ghi file thành công."
            
            send_telegram_alert(msg)
    except Exception as err:
        print(f"Lỗi khi xử lý dữ liệu gửi Telegram: {err}")

    return 0 if (not fatal and len(updated) >= 0.7 * len(symbols)) else 1


if __name__ == "__main__":
    sys.exit(main())
