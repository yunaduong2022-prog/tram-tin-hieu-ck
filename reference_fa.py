"""Shared display policy; each industry retains its own scoring engine."""
import port_fa
import shipping_fa
SYMBOLS=port_fa.SYMBOLS|shipping_fa.SYMBOLS
assert not port_fa.SYMBOLS&shipping_fa.SYMBOLS
compact_notes=port_fa.compact_notes
score_grade=port_fa.score_grade
reference_total=port_fa.reference_total
