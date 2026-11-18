"""Presentation-only highlighting of explicit, source-authored detail paragraphs.

No financial figures or conclusions are generated. All characters of the source
paragraphs remain visible, with selected source phrases styled for on-air use.
Other formats keep using the repository's existing Markdown renderer unchanged.
"""
from __future__ import annotations

import re
from typing import Callable


ORDINAL = re.compile(r"^Thứ\s+(?:nhất|hai|ba|tư|năm|sáu)\s*,\s+", re.I)
AMOUNT = re.compile(r"(?<!\w)\d[\d.,]*\s*(?:tỷ|triệu)\s+đồng\b", re.I)
INCOME_INTRO = re.compile(r"^Ba\s+khoản\b.*\b(?:gồm|bao gồm)\s*:\s*$", re.I)


def _blocks(lines: list[str]) -> list[str]:
    blocks, current = [], []
    for line in [*lines, ""]:
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    return blocks


def _ordinal_item(block: str) -> tuple[str, str] | None:
    # Only transform an explicit numbered argument, not arbitrary prose.
    if "\n" in block or not ORDINAL.match(block):
        return None
    mark = block.find(". ")
    if mark < 0 or mark > 125:
        return None
    head, body = block[:mark + 1], block[mark + 2:]
    if not body.strip():
        return None
    return head, body


def _money_item(block: str) -> re.Match[str] | None:
    if "\n" in block or len(block) > 300:
        return None
    return AMOUNT.search(block)


def render_detail_section(
    lines: list[str],
    markdown_renderer: Callable[[str], tuple[str, str]],
    inline_renderer: Callable[[str], str],
) -> str:
    """Beautify only clearly structured source; preserve fallback and full wording.

    Existing Markdown sections, notes and bullets are rendered unchanged whenever
    the source has no explicit source-authored ordinal/income enumeration.
    """
    blocks = _blocks(lines)
    numbered = [b for b in blocks if _ordinal_item(b) is not None]
    # Avoid turning a lone casual 'Thứ nhất' sentence into a special layout.
    enhance_ordinals = len(numbered) >= 2
    # Only format a clearly identified 3-item source list, otherwise leave it intact.
    has_income = any(
        INCOME_INTRO.search(b) and sum(
            _money_item(candidate) is not None for candidate in blocks[i + 1:i + 4]
        ) >= 2
        for i, b in enumerate(blocks)
    )
    if not enhance_ordinals and not has_income:
        return markdown_renderer("\n".join(lines))[1]

    rendered: list[str] = []
    ordinary: list[str] = []
    income_remaining = 0

    def flush() -> None:
        if ordinary:
            body = markdown_renderer("\n\n".join(ordinary))[1]
            if body:
                rendered.append(body)
            ordinary.clear()

    for b in blocks:
        ordinal = _ordinal_item(b) if enhance_ordinals else None
        amount = _money_item(b) if income_remaining else None
        if ordinal:
            flush()
            head, body = ordinal
            rendered.append(
                "<div class='min-nd-point' style='background:#101f30;border:1px solid #2c4358;"
                "border-left:3px solid #43d6a1;border-radius:8px;padding:10px 12px;margin:8px 0;"
                "color:#dce5f0;font-size:13px;line-height:1.7'>"
                f"<div style='font-weight:800;color:#e8f3fb'>{inline_renderer(head)} </div>"
                f"<div style='margin-top:4px'>{inline_renderer(body)}</div></div>"
            )
        elif amount:
            flush()
            rendered.append(
                "<div class='min-nd-income' style='border:1px solid #29384d;border-radius:8px;"
                "padding:9px 12px;margin:7px 0;color:#dce5f0;font-size:13px;line-height:1.7'>"
                "<span style='color:#43d6a1;font-weight:900;padding-right:8px'>•</span>"
                + inline_renderer(b[:amount.start()])
                + "<strong style='color:#f5c46d;font-size:14px'>"
                + inline_renderer(b[amount.start():amount.end()])
                + "</strong>"
                + inline_renderer(b[amount.end():]) + "</div>"
            )
            income_remaining -= 1
        else:
            # A conclusion is highlighted, not reworded.
            if b.strip().startswith("Vì vậy,") and (enhance_ordinals or has_income):
                flush()
                rendered.append(
                    "<div class='min-nd-takeaway' style='background:#142333;border-left:3px solid #f5c46d;"
                    "padding:9px 12px;border-radius:7px;margin-top:10px;color:#e6edf7;"
                    "font-size:13px;line-height:1.7'>" + inline_renderer(b) + "</div>"
                )
            else:
                ordinary.append(b)
            if has_income and INCOME_INTRO.search(b):
                income_remaining = 3  # the original source explicitly says 'Ba khoản'
            elif income_remaining and not _money_item(b):
                # If the source list is interrupted, do not style later amounts.
                if not INCOME_INTRO.search(b):
                    income_remaining = 0
    flush()
    return "".join(rendered)