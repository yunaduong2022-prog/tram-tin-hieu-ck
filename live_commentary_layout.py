"""Compact, read-only Livestream commentary layout.

All facts remain authored in data/nhan_dinh_ma/<TICKER>.md. This module only
reorders the display: a literal extract, one existing earnings table, and
collapsible source sections. It neither writes data nor generates financial facts.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable


HEADING = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*(?:[-*•–]|👉\s*[-*•])\s+")
KQKD_WORDS = ("chỉ tiêu", "kqkd", "doanh thu", "lợi nhuận")


@dataclass
class SourceSection:
    label: str
    lines: list[str]


def _split_sections(markdown: str) -> tuple[str, list[SourceSection]]:
    """Split on existing headings, without inventing sections or dropping prose."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title = ""
    groups: list[SourceSection] = []
    current_label = ""
    current: list[str] = []
    seen_heading = False

    def emit() -> None:
        nonlocal current_label, current
        if any(line.strip() for line in current) or current_label:
            groups.append(SourceSection(current_label or "Nội dung nhận định", current))
        current_label, current = "", []

    for line in lines:
        match = HEADING.match(line)
        if not match:
            current.append(line)
            continue
        heading = match.group(2).strip()
        # A first, unnumbered '# ...' is the document title. A numbered '# 1.'
        # heading (as in KDH) is a real content section and must remain visible.
        if (not seen_heading and match.group(1) == "#"
                and not re.match(r"^\d+[.)]\s*", heading)):
            emit()  # preserve any prose before the title
            title = heading
            seen_heading = True
            continue
        emit()
        current_label = heading
        seen_heading = True
    emit()
    return title, groups


def _is_kqkd_header(cells: list[str]) -> bool:
    if len(cells) < 2:
        return False
    first = cells[0].casefold()
    return any(word in first for word in KQKD_WORDS)


def _lift_kqkd_table(
    sections: list[SourceSection],
    table_parser: Callable[[list[str], int], tuple[str, int]],
) -> str:
    """Move one existing financial table to the preview. Its rows are not edited."""
    for section in sections:
        for i, line in enumerate(section.lines):
            if not line.strip().startswith("|"):
                continue
            columns = [v.strip() for v in line.strip().strip("|").split("|")]
            if not _is_kqkd_header(columns):
                continue
            table_html, next_i = table_parser(section.lines, i)
            if not table_html:
                continue
            # Replace the block with an empty line, so adjacent paragraphs do
            # not get accidentally concatenated by the source Markdown parser.
            section.lines[i:next_i] = [""]
            return table_html
    return ""


def _source_paragraphs(lines: list[str]) -> list[str]:
    """Short literal excerpts only; never synthesize financial conclusions."""
    paragraphs: list[str] = []
    block: list[str] = []

    def emit() -> None:
        if block:
            value = " ".join(block).strip()
            block.clear()
            if value:
                paragraphs.append(value)

    for line in [*lines, ""]:
        s = line.strip()
        if not s:
            emit()
            continue
        if s.startswith("|") or s.startswith("<!--") or s.startswith("-->"):
            emit()
            continue
        s = BULLET.sub("", s)
        block.append(s)
    return paragraphs


def _quick_points(sections: list[SourceSection]) -> list[str]:
    """One verbatim excerpt from each section, then last conclusion if needed."""
    points: list[str] = []
    candidates = [_source_paragraphs(s.lines) for s in sections]
    for paragraphs in candidates:
        if paragraphs:
            points.append(paragraphs[0])
        if len(points) == 3:
            break
    if len(points) < 3:
        for paragraphs in reversed(candidates):
            for paragraph in reversed(paragraphs):
                if paragraph not in points:
                    points.append(paragraph)
                if len(points) == 3:
                    break
            if len(points) == 3:
                break
    # At most three excerpts, from the exact source, with display truncation.
    return [p if len(p) <= 215 else p[:212].rstrip() + "…" for p in points[:3]]


def compact_commentary(
    markdown: str,
    markdown_renderer: Callable[[str], tuple[str, str]],
    table_parser: Callable[[list[str], int], tuple[str, int]],
    inline_renderer: Callable[[str], str],
) -> tuple[str, str]:
    """Return (document title, compact HTML). Markup is for st.markdown only.

    Preview always shows literal short excerpts and the original financial
    Markdown table, if one exists. Each original section remains expandable.
    """
    title, sections = _split_sections(markdown)
    kqkd_html = _lift_kqkd_table(sections, table_parser)
    points = _quick_points(sections)
    out: list[str] = []

    if points:
        out.append("<div class='min-nd-label' style='color:#8fa1b8;font-weight:800;font-size:11px;margin-top:8px'>"
                   "TÓM TẮT NHANH · TRÍCH NỘI DUNG GỐC</div>")
        out.append("<div style='margin-top:7px;margin-bottom:11px'>")
        for p in points:
            out.append("<div style='display:flex;gap:9px;align-items:flex-start;margin:6px 0;"
                       "color:#dce5f0;font-size:13px;line-height:1.55'>"
                       "<span style='color:#43d6a1;font-weight:800' aria-hidden='true'>•</span>"
                       f"<span>{inline_renderer(p)}</span></div>")
        out.append("</div>")

    if kqkd_html:
        out.extend(("<div style='color:#c7d4e5;font-weight:800;font-size:12px;margin-top:13px'>"
                    "📊 KẾT QUẢ KINH DOANH · THEO BÁO CÁO NGUỒN</div>", kqkd_html))

    rendered = []
    for section in sections:
        section_text = "\n".join(section.lines)
        _, body = markdown_renderer(section_text)
        # Empty headings still retain their source heading in the clickable row.
        if not body and not section.label:
            continue
        label = section.label or "Nội dung nhận định"
        # Preserve exact original headings in the detail labels, safely escaped.
        rendered.append((label, body))

    if rendered:
        out.append("<div style='color:#8fa1b8;font-weight:800;font-size:11px;margin:14px 0 7px'>"
                   "PHÂN TÍCH CHI TIẾT · BẤM ĐỂ MỞ</div>")
        for label, body in rendered:
            out.append("<details class='min-nd-detail' style='border:1px solid #29384d;border-radius:9px;"
                       "margin:6px 0;background:#0e1828'>"
                       "<summary style='cursor:pointer;color:#e5edf6;font-size:13px;font-weight:750;"
                       "padding:11px 12px;line-height:1.5;list-style-position:inside'>"
                       f"{inline_renderer(label)}</summary>"
                       "<div style='padding:2px 12px 13px;border-top:1px solid #29384d'>"
                       f"{body}</div></details>")
    # For heading-only files, commentary_card already displays `title`; avoid
    # repeating the same line below the header.
    return title, "".join(out)
