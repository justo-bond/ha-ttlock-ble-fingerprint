"""Fingerprint credential model."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(slots=True)
class Fingerprint:
    """A fingerprint credential stored on the lock."""

    fingerprint_number: str
    start_date: dt.datetime | None
    end_date: dt.datetime | None

    def to_dict(self) -> dict[str, str | None]:
        """Return a JSON-serialisable representation."""
        return {
            "fingerprint_number": self.fingerprint_number,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }
