"""Select entities for TTLock BLE passcode management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .data import TtlockBleConfigEntry, TtlockBlePasscodeDraft


OPTIONS = ["period", "permanent"]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create passcode type selectors."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBlePasscodeTypeSelect(
            data.coordinator,
            key,
            data.passcode_drafts[key.lockMac],
        )
        for key in data.virtual_keys
    )


class TtlockBlePasscodeTypeSelect(TtlockBleEntity, SelectEntity, RestoreEntity):
    """Editable passcode type selector for one lock."""

    _attr_translation_key = "passcode_type"
    _attr_icon = "mdi:form-select"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = OPTIONS

    def __init__(self, coordinator, key: VirtualKey, draft: TtlockBlePasscodeDraft) -> None:
        super().__init__(coordinator, key)
        self._draft = draft

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_passcode_type"

    @property
    def current_option(self) -> str:
        return self._draft.passcode_type

    async def async_select_option(self, option: str) -> None:
        if option not in OPTIONS:
            raise HomeAssistantError(f"Unsupported passcode type: {option}")
        self._draft.passcode_type = option
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is None or state.state not in OPTIONS:
            return
        self._draft.passcode_type = state.state
        self.async_write_ha_state()
