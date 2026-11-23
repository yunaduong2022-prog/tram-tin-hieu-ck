"""Fail-closed daily NHNN interbank overnight-rate ingestion.

Only append a new, proven date to data/macro_vn.csv. No guessing, no deletion,
no historical rewrites. The independent GitHub Actions workflow is responsible
for scheduling and committing the CSV change; it never updates trading data.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE = "https://sbv.gov.vn/vi/l%C3%A3i-su%E1%BA%A5t1"
IDENTIFIER = "INTERBANK_ON"
FRESHNESS_DAYS = 7
COLUMNS = ["id", "group", "label", "period", "asof", "value", "unit", "comparison", "source", "source_url", "note"]
VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return " ".join(text.split())


class SBVHtml(HTMLParser):
    """Collect table rows and document text in order, ignoring non-visible tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.all_text: list[str] = []
        self.tables: list[tuple[int, list[list[str]]]] = []
        self.ignore_depth = 0
        self.table_depth = 0
        self.rows: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.table_start: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag == "table":
            if self.table_depth == 0:
                self.rows = []
                self.table_start = len(self.all_text)
            self.table_depth += 1
        elif self.table_depth and tag == "tr":
            self.row = []
        elif self.table_depth and tag in {"td", "th"}:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.ignore_depth:
            return
        word = " ".join(data.split())
        if not word:
            return
        self.all_text.append(word)
        if self.cell is not None:
            self.cell.append(word)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth:
            return
        if self.table_depth and tag in {"td", "th"}:
            if self.row is not None and self.cell is not None:
                self.row.append(" ".join(self.cell).strip())
            self.cell = None
        elif self.table_depth and tag == "tr":
            if self.rows is not None and self.row:
                self.rows.append(self.row)
            self.row = None
        elif self.table_depth and tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0 and self.rows is not None:
                self.tables.append((self.table_start, self.rows))
                self.rows = None


@dataclass(frozen=True)
class Observation:
    asof: date
    rate: Decimal


class SourceError(ValueError):
    pass


def parse_official_page(html_text: str, today: date | None = None) -> Observation:
    today = today or datetime.now(VIETNAM).date()
    doc = SBVHtml()
    doc.feed(html_text)
    candidates: list[Observation] = []
    for start, rows in doc.tables:
        header = normalized(" ".join(" ".join(r) for r in rows[:2]))
        if "thoi han" not in header or "lai suat" not in header or "lien ngan hang" not in header:
            continue
        # Require an explicit page heading AND a publication date next to the table,
        # never a date from a news widget or the policy-rate table.
        context = normalized(" ".join(doc.all_text[max(0, start-140):start]))
        heading_pos = context.rfind("lai suat thi truong lien ngan hang")
        if heading_pos < 0:
            continue
        scoped = context[heading_pos:]
        dates = re.findall(r"ngay\s+ap\s+dung\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", scoped)
        if len(dates) != 1:
            raise SourceError("MISSING_OR_AMBIGUOUS_INTERBANK_DATE")
        try:
            published = datetime.strptime(dates[0], "%d/%m/%Y").date()
        except ValueError as exc:
            raise SourceError("INVALID_DATE") from exc
        if published > today or published < date(2014, 1, 1):
            raise SourceError("OUT_OF_RANGE_DATE")
        overnight = [r for r in rows[1:] if r and normalized(r[0]) == "qua dem"]
        if len(overnight) != 1 or len(overnight[0]) < 2:
            raise SourceError("MISSING_OR_AMBIGUOUS_OVERNIGHT_ROW")
        raw = overnight[0][1].strip()
        if not re.fullmatch(r"\d{1,2}(?:[,.]\d{1,3})?", raw):
            raise SourceError("INVALID_RATE_FORMAT")
        try:
            rate = Decimal(raw.replace(",", "."))
        except InvalidOperation as exc:
            raise SourceError("INVALID_RATE_NUMBER") from exc
        if not Decimal("0.01") <= rate <= Decimal("25.00"):
            raise SourceError("RATE_OUT_OF_BOUNDS")
        candidates.append(Observation(published, rate))
    if len(candidates) != 1:
        raise SourceError(f"EXPECTED_EXACTLY_ONE_INTERBANK_TABLE_GOT_{len(candidates)}")
    return candidates[0]


def fetch_official_html() -> str:
    request = Request(SOURCE, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MinMacroSBVVerifiedSync/1.0)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    with urlopen(request, timeout=22) as response:
        actual = urlparse(response.geturl())
        if actual.scheme != "https" or actual.hostname not in {"sbv.gov.vn", "www.sbv.gov.vn"}:
            raise SourceError("UNEXPECTED_SOURCE_REDIRECT")
        data = response.read(3_000_001)
        if len(data) > 3_000_000:
            raise SourceError("HTML_SIZE_LIMIT_EXCEEDED")
        content_type = response.headers.get("Content-Type", "")
        charset = "utf-8"
        match = re.search(r"charset\s*=\s*['\"]?([\w-]+)", content_type, flags=re.I)
        if match:
            charset = match.group(1)
        try:
            return data.decode(charset)
        except (LookupError, UnicodeDecodeError) as exc:
            raise SourceError("INVALID_HTML_ENCODING") from exc


def history_rows(csv_path: Path) -> tuple[bytes, list[dict[str, str]]]:
    """Parse the CSV but retain its exact original bytes (Windows CRLF included)."""
    if not csv_path.is_file():
        raise SourceError("CSV_NOT_FOUND")
    original = csv_path.read_bytes()
    try:
        decoded = original.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceError("CSV_INVALID_ENCODING") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if reader.fieldnames != COLUMNS:
        raise SourceError("CSV_UNEXPECTED_COLUMNS")
    records = list(reader)
    if not records or any(None in r or any(v is None for v in r.values()) for r in records):
        raise SourceError("CSV_MALFORMED")
    return original, records


def make_new_row(obs: Observation) -> dict[str, str]:
    period = obs.asof.strftime("%d/%m/%Y")
    return {
        "id": IDENTIFIER,
        "group": "monetary",
        "label": "Lãi suất liên ngân hàng O/N",
        "period": period,
        "asof": obs.asof.isoformat(),
        "value": f"{obs.rate:.2f}",
        "unit": "%/năm",
        "comparison": "Lãi suất bình quân liên ngân hàng kỳ hạn qua đêm",
        "source": "Ngân hàng Nhà nước Việt Nam (đồng bộ trang nguồn)",
        "source_url": SOURCE,
        "note": f"Tự động kiểm tra bảng NHNN kỳ {period}; không phải dữ liệu theo phiên cổ phiếu",
    }


def update_history(csv_path: Path, obs: Observation, today: date | None = None) -> str:
    today = today or datetime.now(VIETNAM).date()
    original, rows = history_rows(csv_path)
    ages = (today - obs.asof).days
    previous = [r for r in rows if r["id"] == IDENTIFIER]
    if not previous:
        raise SourceError("EXPECTED_EXISTING_ON_SNAPSHOT_FOR_GUARD")
    try:
        latest_date = max(date.fromisoformat(r["asof"]) for r in previous)
    except ValueError as exc:
        raise SourceError("INVALID_PRIOR_DATE") from exc
    if obs.asof < latest_date:
        raise SourceError(f"SOURCE_REGRESSED_{obs.asof}_BEHIND_{latest_date}")
    if ages > FRESHNESS_DAYS:
        raise SourceError(f"SOURCE_STALE_{ages}_DAYS_ASOF_{obs.asof}")
    existing = [r for r in previous if r["asof"] == obs.asof.isoformat()]
    if existing:
        if len(existing) != 1:
            raise SourceError("DUPLICATE_STORED_DATE")
        try:
            prior_value = Decimal(existing[0]["value"])
        except InvalidOperation as exc:
            raise SourceError("INVALID_PRIOR_RATE") from exc
        if obs.rate != prior_value:
            raise SourceError("SAME_DATE_DIFFERENT_RATE_REQUIRES_MANUAL_REVIEW")
        return "ALREADY_CURRENT"
    if obs.asof <= latest_date:
        raise SourceError("NON_MONOTONIC_DATE")
    # Preserve every original byte, including BOM, newline convention, and
    # historical records. On Windows, text-mode read/write would rewrite CRLF.
    # Use the final line ending rather than normalizing mixed legacy files.
    if original.endswith(b"\r\n"):
        newline = b"\r\n"
    elif original.endswith(b"\n"):
        newline = b"\n"
    elif original.endswith(b"\r"):
        newline = b"\r"
    else:
        last_nl = max(original.rfind(b"\n"), original.rfind(b"\r"))
        newline = b"\r\n" if last_nl > 0 and original[last_nl - 1:last_nl + 1] == b"\r\n" else b"\n"
    prefix = b"" if original.endswith((b"\n", b"\r")) else newline
    s = io.StringIO(newline="")
    writer = csv.DictWriter(s, fieldnames=COLUMNS, lineterminator="\n")
    writer.writerow(make_new_row(obs))
    added = s.getvalue().encode("utf-8").replace(b"\n", newline)
    updated = original + prefix + added
    # Validate the candidate before any file replacement; prohibit rewriting history.
    if not updated.startswith(original):
        raise SourceError("HISTORICAL_BYTES_MODIFIED")
    try:
        updated_reader = csv.DictReader(io.StringIO(updated.decode("utf-8-sig"), newline=""))
        updated_rows = list(updated_reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise SourceError("PROPOSED_CSV_INVALID_ENCODING_OR_STRUCTURE") from exc
    if (len(updated_rows) != len(rows) + 1
            or updated_rows[-1] != make_new_row(obs)
            or updated_rows[:-1] != rows):
        raise SourceError("PROPOSED_CSV_INVALID")
    with tempfile.NamedTemporaryFile("wb", dir=csv_path.parent,
                                     prefix=".macro_sbv_", suffix=".tmp", delete=False) as stream:
        tmp_name = stream.name
        stream.write(updated)
    try:
        os.replace(tmp_name, csv_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return "NEW_DATE_APPENDED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/macro_vn.csv")
    parser.add_argument("--html-file", default=None,
                        help="Offline test only: parse saved HTML instead of fetching NHNN")
    args = parser.parse_args()
    try:
        html = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else fetch_official_html()
        obs = parse_official_page(html)
        status = update_history(Path(args.csv), obs)
        print(f"SBV_SYNC_{status} | SOURCE=NHNN | DATE={obs.asof} | ON={obs.rate:.2f}%")
        return 0
    except Exception as exc:
        # GitHub Actions recognizes ::error:: annotations. Do not commit anything.
        msg = f"SBV_SYNC_BLOCKED_NO_CSV_WRITE: {type(exc).__name__}: {exc}"
        print(f"::error::{msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
