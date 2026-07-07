"""Button platform for TTLock BLE fingerprint management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from ttlock_ble import TTLockError

from .entity import TtlockBleEntity
from .services import DEFAULT_END_DATE, DEFAULT_SCAN_TIMEOUT, DEFAULT_START_DATE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create fingerprint management buttons per lock."""
    data = entry.runtime_data
    entities: list[ButtonEntity] = []
    for key in data.virtual_keys:
        connection = data.connections[key.lockMac]
        entities.extend(
            [
                TtlockBleAddFingerprintButton(data.coordinator, key, connection),
                TtlockBleRefreshFingerprintsButton(data.coordinator, key, connection),
            ],
        )
    async_add_entities(entities)


class TtlockBleFingerprintButton(TtlockBleEntity, ButtonEntity):
    """Base class for lock fingerprint action buttons."""

    _attr_icon = "mdi:fingerprint"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind the button to its lock connection."""
        super().__init__(coordinator, key)
        self._connection = connection


class TtlockBleAddFingerprintButton(TtlockBleFingerprintButton):
    """Start local fingerprint enrollment with default validity dates."""

    _attr_translation_key = "add_fingerprint"

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_add_fingerprint"

    async def async_press(self) -> None:
        """Start fingerprint enrollment on the lock."""
        try:
            await self._connection.async_add_fingerprint(
                start_date=DEFAULT_START_DATE,
                end_date=DEFAULT_END_DATE,
                scan_timeout=DEFAULT_SCAN_TIMEOUT,
            )
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc


class TtlockBleRefreshFingerprintsButton(TtlockBleFingerprintButton):
    """Refresh the cached fingerprint list from the lock."""

    _attr_translation_key = "refresh_fingerprints"

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_refresh_fingerprints"

    async def async_press(self) -> None:
        """Read fingerprints from the lock and update HA entities."""
        try:
            await self._connection.async_get_fingerprints()
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc
