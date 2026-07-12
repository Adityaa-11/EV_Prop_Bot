"""Deterministic paper-trading automation."""

from .paper import PaperPolicy, build_paper_entries
from .delivery import deliver_paper_entry, format_paper_slip
from .settlement import evaluate_leg, settle_mlb_entries
from .scheduler import PaperScheduler

__all__ = [
    "PaperPolicy",
    "PaperScheduler",
    "build_paper_entries",
    "deliver_paper_entry",
    "format_paper_slip",
    "evaluate_leg",
    "settle_mlb_entries",
]
