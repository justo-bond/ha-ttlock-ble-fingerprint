"""Button platform for TTLock BLE fingerprint management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError

from ttlock_ble import KeyboardPwdType, TTLockError

from .entity import TtlockBleEntity
from .labels import async_get_labels_manager
from .services import DEFAULT_END_DATE, DEFAULT_SCAN_TIMEOUT, DEFAULT_START_DATE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry, TtlockBlePasscodeDraft


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create fingerprint and passcode management buttons per lock."""
    data = entry.runtime_data
    entities: list[ButtonEntity] = []
    for key in data.virtual_keys:
        connection = data.connections[key.lockMac]
        draft = data.passcode_drafts[key.lockMac]
        entities.extend(
            [
                TtlockBleAddPasscodeButton(data.coordinator, key, connection, draft),
                TtlockBleDeletePasscodeButton(data.coordinator, key, connection, draft),
                TtlockBleClearPasscodesButton(data.coordinator, key, connection),
                TtlockBleRefreshPasscodesButton(data.coordinator, key, connection),
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


class TtlockBlePasscodeButton(TtlockBleFingerprintButton):
    """Base class for passcode actions tied to a shared draft."""

    _attr_icon = "mdi:form-textbox-password"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
        draft: TtlockBlePasscodeDraft,
    ) -> None:
        super().__init__(coordinator, key, connection)
        self._draft = draft

    def _state_value(self, suffix: str, fallback: str) -> str:
        entity_id = f"{self.platform.platform_name}.{self._key.lockMac}_{suffix}".lower()
        state = self.hass.states.get(entity_id)
        if state is None or state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
            return fallback
        return state.state

    def _code(self) -> str:
        code = self._state_value("passcode_value", self._draft.code).strip()
        if not code:
            raise HomeAssistantError("Enter a passcode in the device field first")
        return code

    def _pwd_type(self) -> KeyboardPwdType:
        current = self._state_value("passcode_type", self._draft.passcode_type)
        return {
            "period": KeyboardPwdType.PERIOD,
            "permanent": KeyboardPwdType.PERMANENT,
        }[current]

    def _start_date(self) -> str:
        return self._state_value("passcode_start_date", self._draft.start_date)

    def _end_date(self) -> str:
        return self._state_value("passcode_end_date", self._draft.end_date)

    async def _async_store_passcode_meta(self, code: str) -> None:
        """Persist local metadata so passcodes stay visible without list support."""
        labels = await async_get_labels_manager(self.hass)
        await labels.async_upsert_passcode_meta(
            self._key.lockMac,
            code,
            passcode_type=self._state_value("passcode_type", self._draft.passcode_type),
            start_date=_passcode_iso(self._start_date()),
            end_date=_passcode_iso(self._end_date()),
        )


class TtlockBleAddPasscodeButton(TtlockBlePasscodeButton):
    """Create a keypad passcode from the current draft values."""

    _attr_translation_key = "add_passcode"

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_add_passcode"

    async def async_press(self) -> None:
        code = self._code()
        try:
            await self._connection.async_add_passcode(
                code,
                pwd_type=self._pwd_type(),
                start_date=self._start_date(),
                end_date=self._end_date(),
            )
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await self._async_store_passcode_meta(code)


class TtlockBleDeletePasscodeButton(TtlockBlePasscodeButton):
    """Delete the currently entered keypad passcode."""

    _attr_translation_key = "delete_passcode"

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_delete_passcode"

    async def async_press(self) -> None:
        code = self._code()
        try:
            await self._connection.async_delete_passcode(
                code,
                pwd_type=self._pwd_type(),
            )
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc
        labels = await async_get_labels_manager(self.hass)
        await labels.async_delete_passcode(self._key.lockMac, code)
        await labels.async_delete_passcode_meta(self._key.lockMac, code)


class TtlockBleClearPasscodesButton(TtlockBleFingerprintButton):
    """Delete all keypad passcodes from the lock."""

    _attr_translation_key = "clear_passcodes"
    _attr_icon = "mdi:lock-reset"

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_clear_passcodes"

    async def async_press(self) -> None:
        try:
            await self._connection.async_clear_passcodes()
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc
        labels = await async_get_labels_manager(self.hass)
        await labels.async_clear_passcodes(self._key.lockMac)
        await labels.async_clear_passcode_meta(self._key.lockMac)


class TtlockBleRefreshPasscodesButton(TtlockBleFingerprintButton):
    """Refresh the cached passcode list from the lock."""

    _attr_translation_key = "refresh_passcodes"
    _attr_icon = "mdi:refresh"

    @property
    def unique_id(self) -> str:
        return f"{self._key.lockMac}_refresh_passcodes"

    async def async_press(self) -> None:
        try:
            await self._connection.async_get_passcodes()
        except TTLockError as exc:
            raise HomeAssistantError(str(exc)) from exc


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


def _passcode_iso(value: str) -> str | None:
    """Convert a TTLock passcode date into an ISO-like local timestamp."""
    normalized = value if len(value) == 12 else f"20{value}"
    if len(normalized) != 12:
        return None
    return (
        f"{normalized[0:4]}-{normalized[4:6]}-{normalized[6:8]}"
        f"T{normalized[8:10]}:{normalized[10:12]}:00"
    )
