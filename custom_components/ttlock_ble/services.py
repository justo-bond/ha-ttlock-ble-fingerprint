"""Domain services for TTLock BLE."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from ttlock_ble import KeyboardPwdType, TTLockError

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall
    from ttlock_ble.models import Fingerprint

    from .connection import TtlockBleConnection
    from .data import TtlockBleConfigEntry

ATTR_END_DATE = "end_date"
ATTR_FINGERPRINT_NUMBER = "fingerprint_number"
ATTR_LOCK_MAC = "lock_mac"
ATTR_PASSCODE = "passcode"
ATTR_PASSCODE_TYPE = "passcode_type"
ATTR_SCAN_TIMEOUT = "scan_timeout"
ATTR_START_DATE = "start_date"

SERVICE_ADD_PASSCODE = "add_passcode"
SERVICE_ADD_FINGERPRINT = "add_fingerprint"
SERVICE_CLEAR_PASSCODES = "clear_passcodes"
SERVICE_CLEAR_FINGERPRINTS = "clear_fingerprints"
SERVICE_DELETE_PASSCODE = "delete_passcode"
SERVICE_DELETE_FINGERPRINT = "delete_fingerprint"
SERVICE_LIST_FINGERPRINTS = "list_fingerprints"
SERVICE_UPDATE_FINGERPRINT = "update_fingerprint"

DEFAULT_END_DATE = "209912312359"
DEFAULT_PASSCODE_TYPE = "period"
DEFAULT_SCAN_TIMEOUT = 45.0
DEFAULT_START_DATE = "200001010000"

_DATE = vol.All(str, vol.Match(r"^\d{10}(\d{2})?$"))
_FINGERPRINT_NUMBER = vol.All(str, vol.Match(r"^\d+$"))
_LOCK_SCHEMA = {vol.Required(ATTR_LOCK_MAC): str}
_PASSCODE = vol.All(str, vol.Match(r"^\d{4,9}$"))
_PASSCODE_TYPE = vol.In({"permanent", "period"})

ADD_PASSCODE_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_PASSCODE): _PASSCODE,
        vol.Optional(ATTR_PASSCODE_TYPE, default=DEFAULT_PASSCODE_TYPE): _PASSCODE_TYPE,
        vol.Optional(ATTR_START_DATE, default=DEFAULT_START_DATE): _DATE,
        vol.Optional(ATTR_END_DATE, default=DEFAULT_END_DATE): _DATE,
    },
)

ADD_FINGERPRINT_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Optional(ATTR_START_DATE, default=DEFAULT_START_DATE): _DATE,
        vol.Optional(ATTR_END_DATE, default=DEFAULT_END_DATE): _DATE,
        vol.Optional(ATTR_SCAN_TIMEOUT, default=DEFAULT_SCAN_TIMEOUT): vol.All(
            vol.Coerce(float),
            vol.Range(min=5, max=180),
        ),
    },
)
LIST_FINGERPRINTS_SCHEMA = vol.Schema(_LOCK_SCHEMA)
UPDATE_FINGERPRINT_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_FINGERPRINT_NUMBER): _FINGERPRINT_NUMBER,
        vol.Optional(ATTR_START_DATE, default=DEFAULT_START_DATE): _DATE,
        vol.Optional(ATTR_END_DATE, default=DEFAULT_END_DATE): _DATE,
    },
)
DELETE_FINGERPRINT_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_FINGERPRINT_NUMBER): _FINGERPRINT_NUMBER,
    },
)
CLEAR_PASSCODES_SCHEMA = vol.Schema(_LOCK_SCHEMA)
CLEAR_FINGERPRINTS_SCHEMA = vol.Schema(_LOCK_SCHEMA)
DELETE_PASSCODE_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_PASSCODE): _PASSCODE,
        vol.Optional(ATTR_PASSCODE_TYPE, default=DEFAULT_PASSCODE_TYPE): _PASSCODE_TYPE,
    },
)


def _passcode_type(value: str) -> KeyboardPwdType:
    """Map a service string to the SDK enum."""
    return {
        "permanent": KeyboardPwdType.PERMANENT,
        "period": KeyboardPwdType.PERIOD,
    }[value]


def async_setup_services(hass: HomeAssistant) -> None:
    """Register TTLock BLE domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_FINGERPRINT):
        return

    async def async_add_passcode(call: ServiceCall) -> dict[str, object]:
        return await _async_add_passcode(hass, call)

    async def async_add_fingerprint(call: ServiceCall) -> dict[str, object]:
        return await _async_add_fingerprint(hass, call)

    async def async_list_fingerprints(call: ServiceCall) -> dict[str, object]:
        return await _async_list_fingerprints(hass, call)

    async def async_update_fingerprint(call: ServiceCall) -> None:
        await _async_update_fingerprint(hass, call)

    async def async_delete_fingerprint(call: ServiceCall) -> None:
        await _async_delete_fingerprint(hass, call)

    async def async_delete_passcode(call: ServiceCall) -> None:
        await _async_delete_passcode(hass, call)

    async def async_clear_passcodes(call: ServiceCall) -> None:
        await _async_clear_passcodes(hass, call)

    async def async_clear_fingerprints(call: ServiceCall) -> None:
        await _async_clear_fingerprints(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PASSCODE,
        async_add_passcode,
        schema=ADD_PASSCODE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_FINGERPRINT,
        async_add_fingerprint,
        schema=ADD_FINGERPRINT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_FINGERPRINTS,
        async_list_fingerprints,
        schema=LIST_FINGERPRINTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_FINGERPRINT,
        async_update_fingerprint,
        schema=UPDATE_FINGERPRINT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FINGERPRINT,
        async_delete_fingerprint,
        schema=DELETE_FINGERPRINT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_PASSCODE,
        async_delete_passcode,
        schema=DELETE_PASSCODE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_PASSCODES,
        async_clear_passcodes,
        schema=CLEAR_PASSCODES_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_FINGERPRINTS,
        async_clear_fingerprints,
        schema=CLEAR_FINGERPRINTS_SCHEMA,
    )


async def _async_add_fingerprint(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.add_fingerprint`."""
    connection = _connection_from_call(hass, call)
    try:
        fingerprint = await connection.async_add_fingerprint(
            start_date=call.data[ATTR_START_DATE],
            end_date=call.data[ATTR_END_DATE],
            scan_timeout=call.data[ATTR_SCAN_TIMEOUT],
        )
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    return {"fingerprint": _fingerprint_response(fingerprint)}


async def _async_add_passcode(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.add_passcode`."""
    connection = _connection_from_call(hass, call)
    passcode_type = _passcode_type(call.data[ATTR_PASSCODE_TYPE])
    try:
        await connection.async_add_passcode(
            call.data[ATTR_PASSCODE],
            pwd_type=passcode_type,
            start_date=call.data[ATTR_START_DATE],
            end_date=call.data[ATTR_END_DATE],
        )
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    return {
        "passcode": {
            "code": call.data[ATTR_PASSCODE],
            "type": call.data[ATTR_PASSCODE_TYPE],
            "start_date": call.data[ATTR_START_DATE],
            "end_date": call.data[ATTR_END_DATE],
        },
    }


async def _async_list_fingerprints(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.list_fingerprints`."""
    connection = _connection_from_call(hass, call)
    try:
        fingerprints = await connection.async_get_fingerprints()
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    return {"fingerprints": [_fingerprint_response(item) for item in fingerprints]}


async def _async_update_fingerprint(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.update_fingerprint`."""
    connection = _connection_from_call(hass, call)
    try:
        await connection.async_update_fingerprint(
            call.data[ATTR_FINGERPRINT_NUMBER],
            start_date=call.data[ATTR_START_DATE],
            end_date=call.data[ATTR_END_DATE],
        )
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _async_delete_fingerprint(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.delete_fingerprint`."""
    connection = _connection_from_call(hass, call)
    try:
        await connection.async_delete_fingerprint(call.data[ATTR_FINGERPRINT_NUMBER])
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _async_delete_passcode(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.delete_passcode`."""
    connection = _connection_from_call(hass, call)
    passcode_type = _passcode_type(call.data[ATTR_PASSCODE_TYPE])
    try:
        await connection.async_delete_passcode(
            call.data[ATTR_PASSCODE],
            pwd_type=passcode_type,
        )
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _async_clear_fingerprints(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.clear_fingerprints`."""
    connection = _connection_from_call(hass, call)
    try:
        await connection.async_clear_fingerprints()
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _async_clear_passcodes(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.clear_passcodes`."""
    connection = _connection_from_call(hass, call)
    try:
        await connection.async_clear_passcodes()
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc


def _connection_from_call(
    hass: HomeAssistant,
    call: ServiceCall,
) -> TtlockBleConnection:
    """Resolve a service call's lock identifier to a connection."""
    requested = call.data[ATTR_LOCK_MAC].strip().lower()
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime_data = getattr(entry, "runtime_data", None)
        if runtime_data is None:
            continue
        config_entry = entry  # type: TtlockBleConfigEntry
        for mac, connection in config_entry.runtime_data.connections.items():
            aliases = {
                mac.lower(),
                connection.key.lockAlias.lower(),
                connection.key.lockName.lower(),
            }
            if requested in aliases:
                return connection
    raise HomeAssistantError(f"TTLock BLE lock not found: {call.data[ATTR_LOCK_MAC]}")


def _fingerprint_response(fingerprint: Fingerprint) -> dict[str, str | None]:
    """Convert a fingerprint model to a service response payload."""
    return fingerprint.to_dict()
