"""Deterministic paper-trading automation."""

from .paper import PaperPolicy, build_paper_entries, compute_paper_capacity
from .delivery import deliver_paper_entry, deliver_ops_alert, deliver_live_status, format_paper_slip
from .settlement import evaluate_leg, settle_mlb_entries, void_stale_open_entries
from .scheduler import PaperScheduler

__all__ = [
    "PaperPolicy",
    "PaperScheduler",
    "build_paper_entries",
    "compute_paper_capacity",
    "deliver_paper_entry",
    "deliver_ops_alert",
    "deliver_live_status",
    "format_paper_slip",
    "evaluate_leg",
    "settle_mlb_entries",
    "void_stale_open_entries",
]
