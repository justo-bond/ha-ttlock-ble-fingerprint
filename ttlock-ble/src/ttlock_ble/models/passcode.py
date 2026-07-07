"""Keypad passcode record stored on the lock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..constants import KeyboardPwdType


@dataclass(slots=True)
class Passcode:
    """One keypad code and its validity window as reported by the lock."""

    code: str
    keyboard_pwd_type: KeyboardPwdType
    start_date: datetime | None = None
    end_date: datetime | None = None
    new_code: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Serialize to a Home Assistant friendly payload."""
        return {
            "code": self.code,
            "new_code": self.new_code,
            "type": self.keyboard_pwd_type.name.lower(),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }
