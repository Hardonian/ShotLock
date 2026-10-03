"""ShotLock: turn approved edit requests into preservation constraints and evidence."""

__version__ = "0.0.1"

from .intent import approval_covers, validate_intent, validate_run_record
from .report import crosscheck_report, validate_report

__all__ = [
    "validate_intent",
    "approval_covers",
    "validate_run_record",
    "validate_report",
    "crosscheck_report",
]
