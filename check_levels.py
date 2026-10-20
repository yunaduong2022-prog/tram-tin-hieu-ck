"""Chẩn đoán hỗ trợ/kháng cự của 1 mã: python check_levels.py DCM
Đọc data/eod_prices.csv, dựng nến D/W/M đúng như app, in ra mức kháng cự từng khung đến từ NẾN NÀO,
và cảnh báo nến bất thường (râu quá dài, nhảy giá, trùng ngày, thiếu phiên)."""
import sys
import pandas as pd
import engine as E, mtf_levels as ML

code = (sys.argv[1] if len(sys.argv) > 1 else "DCM").upper()
path = sys.argv[2] if len(sys.argv) > 2 else "data/eod_prices.csv"
raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
g = raw[raw["Mã"] == code][["Mã", "Ngày"] + E.NUMERIC_COLS]
print(f"{code}: {len(g)} dòng, {g['Ngày'].min():%d/%m/%Y} -> {g['Ngày'].max():%d/%m/%Y}; trùng ngày: {int(g['Ngày'].duplicated().sum())}")
H, L, C, O = "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Giá mở cửa"
print("\n25 phiên gần nhất:"); print(g.tail(25)[["Ngày", O, H, L, C, E.VOL]].to_string(index=False))

fr = {tf: E.resample_ohlcv(g, tf) for tf in ("D", "W", "M")}
res = ML.analyze_dwm_timeframe(fr["D"], fr["W"], fr["M"])
for tf in ("D", "W", "M"):
    r, f = res[tf], fr[tf]
    if not r["ok"]:
        print(f"\n[{tf}] {r['cmt']}"); continue
    w20, w60 = f.tail(20), f.tail(60)
    print(f"\n[{tf}] close={r['close']} sup={r['sup']} res={r['res']} (đỉnh sóng ngày {r.get('res_date')}) res2={r.get('res2')} | max high 20 nến={w20[H].max():.2f} "
          f"(ngày {w20.loc[w20[H].idxmax(), 'Ngày']:%d/%m/%Y}) | max high 60 nến={w60[H].max():.2f} "
          f"(ngày {w60.loc[w60[H].idxmax(), 'Ngày']:%d/%m/%Y})")

d = fr["D"].copy()
body_hi = d[[O, C]].max(axis=1)
d["râu_trên_%"] = (d[H] / body_hi - 1) * 100
d["nhảy_%"] = d[C].pct_change().abs() * 100
bad = d[(d["râu_trên_%"] > 6) | (d["nhảy_%"] > 8)].tail(10)
print("\nNến nghi bất thường (râu trên >6% hoặc nhảy đóng cửa >8%):")
print(bad[["Ngày", O, H, L, C, "râu_trên_%", "nhảy_%"]].round(2).to_string(index=False) if len(bad) else "  không có")
