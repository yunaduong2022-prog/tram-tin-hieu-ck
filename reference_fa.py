"""Shared display policy; each industry retains its own scoring engine."""
import port_fa
import shipping_fa
import steel_fa
import oil_fa
SYMBOLS=port_fa.SYMBOLS|shipping_fa.SYMBOLS|steel_fa.SYMBOLS|oil_fa.SYMBOLS
assert not oil_fa.SYMBOLS & (port_fa.SYMBOLS|shipping_fa.SYMBOLS|steel_fa.SYMBOLS)
assert not steel_fa.SYMBOLS & (port_fa.SYMBOLS|shipping_fa.SYMBOLS)
assert not port_fa.SYMBOLS&shipping_fa.SYMBOLS
def compact_notes(tags):
    if any(str(t).startswith('FA tham khảo | Dầu khí |') for t in (tags or [])):
        return oil_fa.compact_notes(tags)
    if any(str(t).startswith('FA tham khảo | Thép |') for t in (tags or [])):
        return steel_fa.compact_notes(tags)
    return port_fa.compact_notes(tags)
score_grade=port_fa.score_grade
reference_total=port_fa.reference_total
