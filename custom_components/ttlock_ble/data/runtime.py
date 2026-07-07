"""State stored on `entry.runtime_data` for the TTLock BLE integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE

    from custom_components.ttlock_ble.connection import TtlockBleConnection
    from custom_components.ttlock_ble.coordinator import (
        TtlockBleDataUpdateCoordinator,
    )
    from ttlock_ble import VirtualKey

    from .stored_key import TtlockBleStoredKey


@dataclass
class TtlockBlePasscodeDraft:
    """Mutable passcode form values shared by device-management entities."""

    code: str = ""
    start_date: str = "200001010000"
    end_date: str = "209912312359"
    passcode_type: str = "period"


@dataclass
class TtlockBleData:
    """State stored on `entry.runtime_data` for the TTLock BLE integration."""

    keys: list[TtlockBleStoredKey]
    virtual_keys: list[VirtualKey]
    connections: dict[str, TtlockBleConnection]
    passcode_drafts: dict[str, TtlockBlePasscodeDraft]
    coordinator: TtlockBleDataUpdateCoordinator
    bluetooth_unsubs: list[CALLBACK_TYPE]
