"""Text entities for TTLock BLE passcode management."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import TtlockBleEntity
from .services import DEFAULT_END_DATE, DEFAULT_START_DATE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .data import TtlockBleConfigEntry, TtlockBlePasscodeDraft


_DATE_RE = re.compile(r"^\d{10}(\d{2})?$")
_PASSCODE_RE = re.compile(r"^\d{4,9}$")


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create text entities for passcode entry fields."""
    data = entry.runtime_data
    entities: list[TextEntity] = []
    for key in data.virtual_keys:
        draft = data.passcode_drafts[key.lockMac]
        entities.extend(
            [
                TtlockBlePasscodeValueText(data.coordinator, key, draft),
                TtlockBlePasscodeStartText(data.coordinator, key, draft),
                TtlockBlePasscodeEndText(data.coordinator, key, draft),
            ],
        )
    async_add_entities(entities)


class TtlockBlePasscodeText(TtlockBleEntity, TextEntity, RestoreEntity):
    """Base text entity backed by a shared per-lock passcode draft."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        key: VirtualKey,
        draft: TtlockBlePasscodeDraft,
    ) -> None:
        super().__init__(coordinator, key)
        self._draft = draft

    async def async_added_to_hass(self) -> None:
        """Restore the last entered value after a Home Assistant restart."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is None or state.state in {"unknown", "unavailable"}:
            return
        self._restore_value(state.state)
        self.async_write_ha_state()

    def _restore_value(self, value: str) -> None:
        """Apply a restored string to the shared draft and local state."""
        raise NotImplementedError


class TtlockBlePasscodeValueText(TtlockBlePasscodeText):
    """Editable keypad passcode value."""

    _attr_translation_key = "passcode_value"
    _attr_icon = "mdi:numeric"
    _attr_mode = TextMode.PASSWORD
    _attr_native_min = 4
    _attr_native_max = 9

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_passcode_value"

    @property
    def native_value(self) -> str:
        return self._draft.code

    async def async_set_value(self, value: str) -> None:
        if value and not _PASSCODE_RE.fullmatch(value):
            raise HomeAssistantError("Passcode must be 4-9 digits")
        self._draft.code = value
        self.async_write_ha_state()

    def _restore_value(self, value: str) -> None:
        if _PASSCODE_RE.fullmatch(value):
            self._draft.code = value


class TtlockBlePasscodeStartText(TtlockBlePasscodeText):
    """Editable keypad passcode start date."""

    _attr_translation_key = "passcode_start_date"
    _attr_icon = "mdi:calendar-start"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 10
    _attr_native_max = 12

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_passcode_start_date"

    @property
    def native_value(self) -> str:
        return self._draft.start_date

    async def async_set_value(self, value: str) -> None:
        if not _DATE_RE.fullmatch(value):
            raise HomeAssistantError("Date must be YYMMDDHHmm or YYYYMMDDHHmm")
        self._draft.start_date = value
        self.async_write_ha_state()

    def _restore_value(self, value: str) -> None:
        self._draft.start_date = value if _DATE_RE.fullmatch(value) else DEFAULT_START_DATE


class TtlockBlePasscodeEndText(TtlockBlePasscodeText):
    """Editable keypad passcode end date."""

    _attr_translation_key = "passcode_end_date"
    _attr_icon = "mdi:calendar-end"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 10
    _attr_native_max = 12

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_passcode_end_date"

    @property
    def native_value(self) -> str:
        return self._draft.end_date

    async def async_set_value(self, value: str) -> None:
        if not _DATE_RE.fullmatch(value):
            raise HomeAssistantError("Date must be YYMMDDHHmm or YYYYMMDDHHmm")
        self._draft.end_date = value
        self.async_write_ha_state()

    def _restore_value(self, value: str) -> None:
        self._draft.end_date = value if _DATE_RE.fullmatch(value) else DEFAULT_END_DATE
