"""Min Invest — curated primary segments for the 33 real-estate watchlist tickers.

A company can have material secondary activities; these are dashboard filtering
labels, NOT an official exchange industry classification. No I/O or network.
"""
from __future__ import annotations

from collections import OrderedDict

ALL = "Tất cả BĐS"
SUBSECTORS = OrderedDict([
    ("Nhà ở – đô thị", (
        "VHM", "NVL", "KDH", "DXG", "DIG", "PDR", "NLG", "TCH", "AGG",
        "NTL", "HQC", "SGR", "HPX", "HDC", "LDG", "NBB", "SCR", "QCG", "VPI")),
    ("Khu công nghiệp", ("KBC", "IDC", "SZC", "BCM", "IJC", "VGC")),
    ("Thương mại – bán lẻ", ("VRE",)),
    ("Nghỉ dưỡng – du lịch", ("CEO",)),
    ("Dịch vụ – môi giới", ("DXS", "CRE")),
    ("Đa ngành – kết hợp", ("VIC", "HDG", "HTN", "HHS")),
])

# Optional notes; segment assignment is by primary category only to avoid duplicates.
SECONDARY = {
    "TCH": "ô tô", "VGC": "vật liệu xây dựng", "IJC": "hạ tầng",
    "HDG": "năng lượng", "VIC": "tập đoàn đa ngành", "HHS": "ô tô",
    "HTN": "xây dựng", "CEO": "nhà ở",
}


def validate(expected):
    """Reject stale or overlapping mappings; keep the existing watchlist canonical."""
    configured = {str(code).strip().upper() for code in expected}
    all_codes = [code for values in SUBSECTORS.values() for code in values]
    duplicated = sorted(code for code in set(all_codes) if all_codes.count(code) > 1)
    missing = sorted(configured - set(all_codes))
    extra = sorted(set(all_codes) - configured)
    if duplicated or missing or extra:
        raise ValueError(f"BDS mapping mismatch: duplicated={duplicated}, missing={missing}, extra={extra}")
    return True


def symbols_for(segment, configured):
    allowed = {str(code).strip().upper() for code in configured}
    if segment == ALL:
        return allowed
    if segment not in SUBSECTORS:
        raise ValueError(f"Unknown real estate segment: {segment}")
    return allowed.intersection(SUBSECTORS[segment])


def options(configured):
    validate(configured)
    return [ALL] + list(SUBSECTORS)


def label(segment, configured):
    return f"{segment} ({len(symbols_for(segment, configured))} mã)"
