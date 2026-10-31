"""Rổ mã theo nhóm ngành cho Trạm Tín Hiệu.

- Nhóm VN30 lấy trực tiếp từ vnstock (danh mục đổi theo kỳ cơ cấu); nếu không lấy được thì dùng VN30_DU_PHONG.
- Các nhóm ngành là danh sách khởi đầu do người dùng liệt kê; sửa trực tiếp trong GROUPS bên dưới.
- Một mã có thể thuộc nhiều nhóm (ví dụ GVR vừa trong VN30 vừa trong Cao su).
"""
from __future__ import annotations

# Danh mục dự phòng nếu không lấy được VN30 từ nguồn (ước lượng sau kỳ cơ cấu tháng 7/2026, cần đối chiếu lại)
VN30_DU_PHONG = ["ACB", "BCM", "BID", "BSR", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB", "MBB", "MCH", "MSN", "MWG",
                 "SAB", "SHB", "SSB", "SSI", "STB", "TCB", "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"]

GROUPS: dict[str, list[str]] = {
    "Dầu khí": ["GAS", "PLX", "BSR", "PVD", "PVS", "PVC", "OIL", "PGD",
                "POS", "PPT", "PTV", "PVB", "PVM", "PXS", "PVE"],
    "Cảng biển": ["MVN", "PHP", "GMD", "DXP", "VSC", "SGP", "CDN", "TCL",
                  "CAG", "CCR", "CCT", "CLL", "CMP", "CQN", "DVP", "GIC", "ILB", "IST", "NAP", "PAP", "PDN",
                  "PQN", "PSN", "STG", "TCW", "TMS", "VGP", "VGR", "VIN", "VMS", "CCP", "CPI", "DS3", "QNP"],
    "Vận tải biển hàng hóa": ["HAH", "VTO", "VOS", "PVT", "PVP", "VIP", "PPH"],
    "Vận tải": ["GSP", "SAS", "VJC", "HVN", "SCS"],
    "Cao su": ["GVR", "DRI", "PHR", "DPR", "TRC", "BRC", "HRC", "DRC", "CSM", "SRC"],
    "Phân bón": ["DPM", "DCM", "BFC", "LAS", "SFG", "VAF", "CSV", "DDV"],
    "Bán lẻ": ["MWG", "FRT", "PNJ", "DGW", "PET", "MSN"],
    "Ngân hàng": ["VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "HDB", "STB", "SHB", "TPB", "VIB", "LPB", "MSB", "OCB",
                  "SSB", "EIB", "KLB", "NAB", "VAB", "NVB", "ABB", "BVB", "EVF",
                  "BAB", "VBB", "SGB", "PGB", "PCB", "TIN"],
    "Chứng khoán": ["SSI", "VND", "VCI", "HCM", "VIX", "SHS", "MBS", "FTS", "BSI", "CTS", "ORS", "TCX", "AGR", "TVS", "VDS",
                    "VFS", "APG", "DSC", "BMS", "BVS", "IVS", "SBS", "PSI", "VPX", "LPS", "APS", "DSE", "AAS", "VIG", "VCK", "ABW"],
    "Bảo hiểm": ["BVH"],
    "Bất động sản": ["VHM", "VIC", "VRE", "NVL", "KDH", "DXG", "DIG", "CEO", "PDR", "NLG", "KBC", "IDC", "SZC", "BCM", "TCH",
                     "HDG", "AGG", "IJC", "HTN", "NTL", "HQC", "DXS", "SGR", "HHS", "HPX", "HDC", "LDG", "NBB", "SCR", "QCG",
                     "VPI", "CRE", "VGC"],
    "Khai khoáng": ["MSR", "KSV", "BMC", "DHM", "KSB", "NNC", "BKC"],
    "Thép": ["HPG", "HSG", "NKG", "SMC", "TLH", "POM", "VGS", "TVN", "HMC"],
    "Thủy sản": ["VHC", "ANV", "FMC", "IDI", "MPC", "CMX", "ACL", "ABT"],
    "Dược phẩm": ["DCL", "DHG", "IMP", "TRA", "DBD", "DHT", "DVN", "TTD", "DTP", "DP3"],
    "Nông nghiệp & thực phẩm": ["MCH", "MSN", "VNM", "CLX"],
    "Thịt & chăn nuôi": ["BAF"],
    "Đường": ["SBT", "QNS"],
    "Đồ uống": ["SAB", "SMB"],
    "May mặc": ["VGT"],
    "Công nghệ": ["FPT"],
    "Xây dựng": ["CDC", "VCG", "CTD"],
    "Họ Vingroup": ["VIC", "VHM", "VRE", "VPL", "VEF", "VNB"],
    "Vật liệu xây dựng": ["HT1", "VGC", "NTP", "DHA", "VLB"],
    "Hàng công nghiệp": ["DHC", "HHP", "VEA", "MZG"],
    "Hàng tiêu dùng": ["TLG"],
    "Điện": ["NT2", "GEE", "POW", "REE", "PGV", "DNH", "VSH", "QTP", "HNA", "SBH", "GEG", "HND", "CHP", "TMP", "SHP", "PPC", "AVC", "VPD", "TBC"],
    "Nhựa": ["NTP"],
    "Hạ tầng giao thông": ["CII"],
    "Đa ngành": ["VGC", "SAM", "THD"],
    "Họ Gelex": ["GEX", "GEL", "GEE", "VIX", "VSC", "EIB"],
}

# Danh mục cũ của người dùng (giữ lại để chọn khi cần)
OLD_LIST = ("SAS,GMD,KSV,MWG,MSN,MSB,NTP,TCB,BVH,BSR,VPB,TLG,MVN,MCH,HDB,PVT,VGT,NVB,BAF,DCM,FRT,PHP,ABB,PVS,HCM,DGW,VEA,MSR,"
            "BFC,VHM,CTG,SHB,BID,VRE,LPB,SSB,GVR,VNM,SSI,HPG,VCB,VIB,FPT,VJC,ACB,SAB,STB,GAS,TCX,MBB,VIC,CTS,BSI,SBS,TVS,"
            "FTS,PSI,AAS,VIX,SHS,APG,VCI,AGR,ORS,DSC,BMS,BVS,IVS,VDS,VFS,VIG,VND,VPX,LPS,MBS,VCK,APS,DSE,TPB,OCB,KLB,EVF,NAB,"
            "VAB,EIB,KDH,AGG,IJC,HDG,HTN,NTL,HQC,TCH,DXS,SGR,HHS,HPX,NLG,VCG,CEO,CLX,HDC,LDG,NBB,SAM,NVL,DIG,PDR,DXG,QCG,SCR,"
            "VPI,CRE,DCL,CDC,BKC,QNS,PVP,VTO,DHA,VOS,SMB,PPH,HHP,DHC,VLB,TRC,DRI").split(",")

VN30 = "VN30"
OLD = "Danh mục cũ của bạn"
DEFAULT_PICK = [VN30] + list(GROUPS)


def group_names() -> list[str]:
    return [VN30] + list(GROUPS) + [OLD]


def _symbols_from(obj) -> list[str]:
    """Rút danh sách mã từ Series/DataFrame/list mà các phiên bản vnstock trả về."""
    if obj is None:
        return []
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            col = next((c for c in obj.columns if str(c).lower() in ("symbol", "ticker", "code", "stock_code")), obj.columns[0])
            obj = obj[col]
    except Exception:
        pass
    return [str(s).strip().upper() for s in list(obj) if str(s).strip()]


def fetch_vn30() -> tuple[list[str], str]:
    """Lấy rổ VN30 từ vnstock (thế hệ 5 rồi bản cũ). Trả về (danh sách mã, ghi chú nguồn)."""
    errors = []
    try:
        from vnstock import Reference
        for call in (lambda: Reference().equity.list_by_group("VN30"),
                     lambda: Reference().equity.list_by_group(group="VN30")):
            try:
                syms = _symbols_from(call())
                if 25 <= len(syms) <= 35:
                    return syms, "vnstock (Reference)"
            except Exception as e:  # thử cách gọi kế tiếp
                errors.append(str(e))
    except Exception as e:
        errors.append(str(e))
    try:
        from vnstock import Listing
        for src in ("VCI", "KBS"):
            try:
                syms = _symbols_from(Listing(source=src).symbols_by_group("VN30"))
                if 25 <= len(syms) <= 35:
                    return syms, f"vnstock (Listing {src})"
            except Exception as e:
                errors.append(str(e))
    except Exception as e:
        errors.append(str(e))
    return list(VN30_DU_PHONG), "danh sách dự phòng trong watchlist.py (không lấy được từ nguồn)"


def membership(vn30: list[str]) -> dict[str, list[str]]:
    """Mã -> các nhóm mã đó thuộc về."""
    m: dict[str, list[str]] = {}
    for s in vn30:
        m.setdefault(s, []).append(VN30)
    for g, syms in GROUPS.items():
        for s in syms:
            if g not in m.setdefault(s, []):
                m[s].append(g)
    return m


def symbols_for(picked: list[str], vn30: list[str]) -> list[str]:
    out: list[str] = []
    for g in picked:
        if g == VN30:
            out += vn30
        elif g == OLD:
            out += OLD_LIST
        else:
            out += GROUPS.get(g, [])
    return list(dict.fromkeys(out))
