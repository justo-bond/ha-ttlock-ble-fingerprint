"""Sensor platform for ttlock_ble — battery level."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ttlock_ble import TTLockError

from .connection import event_signal, fingerprint_signal, passcode_signal
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LockEvent, VirtualKey
    from ttlock_ble.models import Fingerprint, Passcode

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensors per `VirtualKey`."""
    data = entry.runtime_data
    entities: list[SensorEntity] = []
    for key in data.virtual_keys:
        entities.extend(
            [
                TtlockBleBatterySensor(data.coordinator, key),
                TtlockBleFingerprintCountSensor(
                    data.coordinator,
                    key,
                    data.connections[key.lockMac],
                ),
                TtlockBlePasscodeCountSensor(
                    data.coordinator,
                    key,
                    data.connections[key.lockMac],
                ),
            ],
        )
    async_add_entities(entities)


class TtlockBleBatterySensor(TtlockBleEntity, SensorEntity):
    """Battery level reported by the lock — refreshed on poll and on every push."""

    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the sensor to its key + coordinator."""
        super().__init__(coordinator, key)
        self._attr_native_value: int | None = None
        self._sync_from_coordinator()

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_battery"

    async def async_added_to_hass(self) -> None:
        """Subscribe to push-event notifications for the lock's MAC."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                event_signal(self._key.lockMac),
                self._on_lock_event,
            ),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Adopt the coordinator's freshest battery reading, if any."""
        self._sync_from_coordinator()
        super()._handle_coordinator_update()

    @callback
    def _on_lock_event(self, event: LockEvent) -> None:
        """Adopt the battery byte the lock embedded in its push payload."""
        if event.battery is None:
            return
        self._attr_native_value = event.battery
        self.async_write_ha_state()

    def _sync_from_coordinator(self) -> None:
        """Copy `battery_level` from the coordinator snapshot, if known."""
        state = self._lock_state
        if state is None:
            return
        battery = state.get("battery_level")
        if battery is None:
            return
        self._attr_native_value = battery


class TtlockBleFingerprintCountSensor(TtlockBleEntity, SensorEntity):
    """Number of fingerprints cached for the lock."""

    _attr_translation_key = "fingerprints_count"
    _attr_icon = "mdi:fingerprint"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind the sensor to its key + connection cache."""
        super().__init__(coordinator, key)
        self._connection = connection
        self._attr_native_value: int | None = None
        self._sync_from_connection()

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_fingerprints_count"

    async def async_added_to_hass(self) -> None:
        """Subscribe to fingerprint cache updates for the lock's MAC."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                fingerprint_signal(self._key.lockMac),
                self._on_fingerprints,
            ),
        )

    async def async_update(self) -> None:
        """Refresh the fingerprint list when HA explicitly updates this entity."""
        try:
            await self._connection.async_get_fingerprints()
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc
        self._sync_from_connection()

    @callback
    def _on_fingerprints(self, _fingerprints: list[Fingerprint] | None) -> None:
        """Update the state from the connection's cached fingerprint list."""
        self._sync_from_connection()
        self.async_write_ha_state()

    def _sync_from_connection(self) -> None:
        """Copy the cached fingerprint list into state and attributes."""
        fingerprints = self._connection.fingerprints
        if fingerprints is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = None
            return
        self._attr_native_value = len(fingerprints)
        self._attr_extra_state_attributes = {
            "fingerprints": [fingerprint.to_dict() for fingerprint in fingerprints],
        }


class TtlockBlePasscodeCountSensor(TtlockBleEntity, SensorEntity):
    """Number of passcodes cached for the lock."""

    _attr_translation_key = "passcodes_count"
    _attr_icon = "mdi:form-textbox-password"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind the sensor to its key + connection cache."""
        super().__init__(coordinator, key)
        self._connection = connection
        self._attr_native_value: int | None = None
        self._sync_from_connection()

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_passcodes_count"

    async def async_added_to_hass(self) -> None:
        """Subscribe to passcode cache updates for the lock's MAC."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                passcode_signal(self._key.lockMac),
                self._on_passcodes,
            ),
        )

    async def async_update(self) -> None:
        """Refresh the passcode list when HA explicitly updates this entity."""
        try:
            await self._connection.async_get_passcodes()
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc
        self._sync_from_connection()

    @callback
    def _on_passcodes(self, _passcodes: list[Passcode] | None) -> None:
        """Update the state from the connection's cached passcode list."""
        self._sync_from_connection()
        self.async_write_ha_state()

    def _sync_from_connection(self) -> None:
        """Copy the cached passcode list into state and attributes."""
        passcodes = self._connection.passcodes
        if passcodes is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = None
            return
        self._attr_native_value = len(passcodes)
        self._attr_extra_state_attributes = {
            "passcodes": [passcode.to_dict() for passcode in passcodes],
        }
