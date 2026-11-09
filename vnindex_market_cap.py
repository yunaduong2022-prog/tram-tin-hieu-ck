"""Sector-specific market-cap eligibility for VNINDEX representative tickers.

Uses existing data/shares_outstanding.csv and the *same EOD close* used by
Dong dan song (price in THOUSANDS of VND). No API/network calls and no
changes to the underlying sector strength ranking.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
import math
from pathlib import Path

# Market cap thresholds, in BILLIONS of VND (ty dong). User-approved initial policy.
SECTOR_MIN_CAP_BIL = {
    "Ngân hàng": 20000,
    "Chứng khoán": 5000,
    "Bất động sản": 5000,
    "Thép": 3000,
    "Đầu tư công": 3000,
    "Dầu khí": 3000,
    "Bán lẻ": 3000,
    "Vận tải": 2000,
    "Vận tải biển hàng hóa": 2000,
    "Cảng biển": 2000,
    "Vật liệu xây dựng": 2000,
    "Khai khoáng": 2000,
    "Đồ uống": 1000,
}


def threshold_for_group(name: str, member_count: int) -> int:
    """Return minimum market cap in billions VND; small groups are less restrictive."""
    return SECTOR_MIN_CAP_BIL.get(name, 1000 if member_count <= 4 else 2000)


def load_shares(path: Path, *, as_of: date | None = None) -> dict[str, int]:
    """Read validated outstanding-share counts; skip future-dated rows.

    The CSV's legacy 'tay' update marker has no date and is treated as a manual
    current estimate, *not* an as-of historical estimate for backtesting.
    Invalid/missing data never passes the capitalization filter.
    """
    if not path.is_file():
        return {}
    output: dict[str, int] = {}
    invalid: set[str] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not {"Mã", "Số CP lưu hành"}.issubset(reader.fieldnames or []):
                return {}
            for row in reader:
                code = (row.get("Mã") or "").strip().upper()
                if not code or not code.isascii() or not code.isalnum():
                    continue
                stamp = (row.get("Cập nhật") or "").strip()
                if as_of is not None and stamp:
                    try:
                        updated = datetime.strptime(stamp, "%d/%m/%Y").date()
                    except ValueError:
                        updated = None  # 'tay' / legacy undated records
                    if updated is not None and updated > as_of:
                        continue
                raw = (row.get("Số CP lưu hành") or "").strip().replace(",", "")
                try:
                    shares = int(raw)
                except (ValueError, TypeError):
                    continue
                if not (0 < shares < 100_000_000_000):
                    continue
                if code in output and output[code] != shares:
                    invalid.add(code)  # conflicting duplicates: fail closed
                else:
                    output[code] = shares
    except (OSError, UnicodeError, csv.Error):
        return {}
    for code in invalid:
        output.pop(code, None)
    return output


def capitalization_bil(price_thousand_vnd: object, shares: object) -> float | None:
    """close (nghin dong) * shares / 1,000,000 = ty dong."""
    try:
        close = float(price_thousand_vnd)
        count = int(shares)
    except (ValueError, TypeError, OverflowError):
        return None
    if not (math.isfinite(close) and close > 0 and 0 < count < 100_000_000_000):
        return None
    return (close * count) / 1_000_000


def filtered_top_codes(rows: list[dict], shares: dict[str, int], minimum_bil: int,
                       top: int = 5) -> list[str]:
    """Keep the canonical price-strength order, skipping unverified/undersized codes."""
    if minimum_bil <= 0 or top <= 0:
        return []
    selected: list[str] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row.get("Mã", "")).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        cap = capitalization_bil(row.get("Giá"), shares.get(code))
        if cap is not None and cap >= minimum_bil:
            selected.append(code)
            if len(selected) == top:
                break
    return selected
