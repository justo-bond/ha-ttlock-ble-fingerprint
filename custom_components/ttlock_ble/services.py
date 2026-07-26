"""Domain services for TTLock BLE."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.helpers import entity_registry as er
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from ttlock_ble import KeyboardPwdType, TTLockError

from .const import DOMAIN
from .labels import async_get_labels_manager

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall
    from ttlock_ble.models import Fingerprint, LogEntry, Passcode

    from .connection import TtlockBleConnection
    from .data import TtlockBleConfigEntry

ATTR_ADMIN_PASSWORD = "admin_password"
ATTR_AUTO_LOCK_SECONDS = "auto_lock_seconds"
ATTR_END_DATE = "end_date"
ATTR_FINGERPRINT_NUMBER = "fingerprint_number"
ATTR_LABEL = "label"
ATTR_LOCK_MAC = "lock_mac"
ATTR_NEW_PASSCODE = "new_passcode"
ATTR_OLD_PASSCODE = "old_passcode"
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
SERVICE_LIST_OPERATION_LOG = "list_operation_log"
SERVICE_LIST_PASSCODES = "list_passcodes"
SERVICE_LIST_FINGERPRINTS = "list_fingerprints"
SERVICE_GET_AUTO_LOCK = "get_auto_lock"
SERVICE_REVEAL_PASSCODE = "reveal_passcode"
SERVICE_SET_AUTO_LOCK = "set_auto_lock"
SERVICE_SET_FINGERPRINT_LABEL = "set_fingerprint_label"
SERVICE_SET_PASSCODE_LABEL = "set_passcode_label"
SERVICE_UPDATE_PASSCODE = "update_passcode"
SERVICE_UPDATE_FINGERPRINT = "update_fingerprint"

DEFAULT_END_DATE = "209912312359"
DEFAULT_PASSCODE_TYPE = "period"
DEFAULT_SCAN_TIMEOUT = 45.0
DEFAULT_START_DATE = "200001010000"
DEFAULT_PASSCODE_END_DATE = "9912311400"
DEFAULT_PASSCODE_START_DATE = "0001311400"

_DATE = vol.All(str, vol.Match(r"^\d{10}(\d{2})?$"))
_FINGERPRINT_NUMBER = vol.All(str, vol.Match(r"^\d+$"))
_LOCK_SCHEMA = {vol.Required(ATTR_LOCK_MAC): str}
_PASSCODE = vol.All(str, vol.Match(r"^\d{4,9}$"))
_PASSCODE_TYPE = vol.In({"permanent", "period"})
_PASSCODE_DATE = vol.All(str, vol.Match(r"^\d{10}(\d{2})?$"))

ADD_PASSCODE_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_PASSCODE): _PASSCODE,
        vol.Optional(ATTR_PASSCODE_TYPE, default=DEFAULT_PASSCODE_TYPE): _PASSCODE_TYPE,
        vol.Optional(ATTR_START_DATE, default=DEFAULT_PASSCODE_START_DATE): _PASSCODE_DATE,
        vol.Optional(ATTR_END_DATE, default=DEFAULT_PASSCODE_END_DATE): _PASSCODE_DATE,
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
GET_AUTO_LOCK_SCHEMA = vol.Schema(_LOCK_SCHEMA)
LIST_OPERATION_LOG_SCHEMA = vol.Schema(_LOCK_SCHEMA)
REVEAL_PASSCODE_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_PASSCODE): _PASSCODE,
        vol.Required(ATTR_ADMIN_PASSWORD): str,
    },
)
SET_AUTO_LOCK_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_AUTO_LOCK_SECONDS): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=65535),
        ),
    },
)
UPDATE_FINGERPRINT_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_FINGERPRINT_NUMBER): _FINGERPRINT_NUMBER,
        vol.Optional(ATTR_START_DATE, default=DEFAULT_START_DATE): _DATE,
        vol.Optional(ATTR_END_DATE, default=DEFAULT_END_DATE): _DATE,
    },
)
SET_FINGERPRINT_LABEL_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_FINGERPRINT_NUMBER): _FINGERPRINT_NUMBER,
        vol.Optional(ATTR_LABEL, default=""): str,
    },
)
SET_PASSCODE_LABEL_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_PASSCODE): _PASSCODE,
        vol.Optional(ATTR_LABEL, default=""): str,
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
LIST_PASSCODES_SCHEMA = vol.Schema(_LOCK_SCHEMA)
DELETE_PASSCODE_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_PASSCODE): _PASSCODE,
        vol.Optional(ATTR_PASSCODE_TYPE, default=DEFAULT_PASSCODE_TYPE): _PASSCODE_TYPE,
    },
)
UPDATE_PASSCODE_SCHEMA = vol.Schema(
    {
        **_LOCK_SCHEMA,
        vol.Required(ATTR_OLD_PASSCODE): _PASSCODE,
        vol.Required(ATTR_NEW_PASSCODE): _PASSCODE,
        vol.Optional(ATTR_PASSCODE_TYPE, default=DEFAULT_PASSCODE_TYPE): _PASSCODE_TYPE,
        vol.Optional(ATTR_START_DATE, default=DEFAULT_PASSCODE_START_DATE): _PASSCODE_DATE,
        vol.Optional(ATTR_END_DATE, default=DEFAULT_PASSCODE_END_DATE): _PASSCODE_DATE,
    },
)


def _passcode_type(value: str) -> KeyboardPwdType:
    """Map a service string to the SDK enum."""
    return {
        "permanent": KeyboardPwdType.PERMANENT,
        "period": KeyboardPwdType.PERIOD,
    }[value]


def _passcode_date(value: str) -> str:
    """Normalize passcode dates to TTLock's YYMMDDHHmm wire format."""
    if len(value) == 12:
        return value[2:]
    return value


def async_setup_services(hass: HomeAssistant) -> None:
    """Register TTLock BLE domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_FINGERPRINT):
        return

    async def async_add_passcode(call: ServiceCall) -> dict[str, object]:
        return await _async_add_passcode(hass, call)

    async def async_add_fingerprint(call: ServiceCall) -> dict[str, object]:
        return await _async_add_fingerprint(hass, call)

    async def async_list_passcodes(call: ServiceCall) -> dict[str, object]:
        return await _async_list_passcodes(hass, call)

    async def async_list_fingerprints(call: ServiceCall) -> dict[str, object]:
        return await _async_list_fingerprints(hass, call)

    async def async_list_operation_log(call: ServiceCall) -> dict[str, object]:
        return await _async_list_operation_log(hass, call)

    async def async_get_auto_lock(call: ServiceCall) -> dict[str, object]:
        return await _async_get_auto_lock(hass, call)

    async def async_reveal_passcode(call: ServiceCall) -> dict[str, object]:
        return await _async_reveal_passcode(hass, call)

    async def async_update_passcode(call: ServiceCall) -> None:
        await _async_update_passcode(hass, call)

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

    async def async_set_fingerprint_label(call: ServiceCall) -> None:
        await _async_set_fingerprint_label(hass, call)

    async def async_set_passcode_label(call: ServiceCall) -> None:
        await _async_set_passcode_label(hass, call)

    async def async_set_auto_lock(call: ServiceCall) -> None:
        await _async_set_auto_lock(hass, call)

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
        SERVICE_LIST_PASSCODES,
        async_list_passcodes,
        schema=LIST_PASSCODES_SCHEMA,
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
        SERVICE_GET_AUTO_LOCK,
        async_get_auto_lock,
        schema=GET_AUTO_LOCK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_OPERATION_LOG,
        async_list_operation_log,
        schema=LIST_OPERATION_LOG_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVEAL_PASSCODE,
        async_reveal_passcode,
        schema=REVEAL_PASSCODE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_PASSCODE,
        async_update_passcode,
        schema=UPDATE_PASSCODE_SCHEMA,
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FINGERPRINT_LABEL,
        async_set_fingerprint_label,
        schema=SET_FINGERPRINT_LABEL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PASSCODE_LABEL,
        async_set_passcode_label,
        schema=SET_PASSCODE_LABEL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AUTO_LOCK,
        async_set_auto_lock,
        schema=SET_AUTO_LOCK_SCHEMA,
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
            start_date=_passcode_date(call.data[ATTR_START_DATE]),
            end_date=_passcode_date(call.data[ATTR_END_DATE]),
        )
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    labels = await async_get_labels_manager(hass)
    await labels.async_upsert_passcode_meta(
        connection.key.lockMac,
        call.data[ATTR_PASSCODE],
        passcode_type=call.data[ATTR_PASSCODE_TYPE],
        start_date=_passcode_iso(call.data[ATTR_START_DATE]),
        end_date=_passcode_iso(call.data[ATTR_END_DATE]),
    )
    return {
        "passcode": {
            "code": call.data[ATTR_PASSCODE],
            "type": call.data[ATTR_PASSCODE_TYPE],
            "start_date": _passcode_iso(call.data[ATTR_START_DATE]),
            "end_date": _passcode_iso(call.data[ATTR_END_DATE]),
        },
    }


async def _async_list_fingerprints(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.list_fingerprints`."""
    connection = _connection_from_call(hass, call)
    labels = await async_get_labels_manager(hass)
    try:
        fingerprints = await connection.async_get_fingerprints()
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    return {
        "fingerprints": [
            _fingerprint_response(
                connection,
                item,
                label=labels.get_fingerprint_label(
                    connection.key.lockMac,
                    item.fingerprint_number,
                ),
            )
            for item in fingerprints
        ],
    }


async def _async_list_passcodes(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.list_passcodes`."""
    connection = _connection_from_call(hass, call)
    labels = await async_get_labels_manager(hass)
    try:
        passcodes = await connection.async_get_passcodes()
    except (TTLockError, ValueError, RuntimeError) as exc:
        fallback = labels.get_passcode_meta(connection.key.lockMac)
        if not fallback:
            return {
                "passcodes": [],
                "warning": _passcode_list_warning(fallback_used=False),
                "error": str(exc),
            }
        return {
            "passcodes": [
                {
                    **item,
                    "label": labels.get_passcode_label(connection.key.lockMac, item["code"]),
                    "lock_mac": connection.key.lockMac,
                    "source": "local_cache",
                }
                for item in fallback
            ],
            "warning": _passcode_list_warning(fallback_used=True),
            "error": str(exc),
        }
    return {
        "passcodes": [
            _passcode_response(
                connection,
                item,
                label=labels.get_passcode_label(connection.key.lockMac, item.code),
            )
            for item in passcodes
        ],
    }


async def _async_list_operation_log(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.list_operation_log`."""
    connection = _connection_from_call(hass, call)
    try:
        entries = await connection.async_get_operation_log(
            dispatch=False,
            only_new=False,
        )
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    return {"entries": [_log_entry_response(item) for item in entries]}


async def _async_get_auto_lock(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.get_auto_lock`."""
    connection = _connection_from_call(hass, call)
    try:
        seconds = await connection.async_get_auto_lock_time()
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    return {"auto_lock_seconds": seconds}


async def _async_reveal_passcode(
    hass: HomeAssistant,
    call: ServiceCall,
) -> dict[str, object]:
    """Handle `ttlock_ble.reveal_passcode`."""
    connection = _connection_from_call(hass, call)
    if not connection.key.adminPs:
        raise HomeAssistantError("This lock key does not include an admin password")
    if call.data[ATTR_ADMIN_PASSWORD].strip() != connection.key.adminPs.strip():
        raise HomeAssistantError("Invalid admin password")
    return {"passcode": call.data[ATTR_PASSCODE]}


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


async def _async_update_passcode(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.update_passcode`."""
    connection = _connection_from_call(hass, call)
    passcode_type = _passcode_type(call.data[ATTR_PASSCODE_TYPE])
    try:
        await connection.async_update_passcode(
            call.data[ATTR_OLD_PASSCODE],
            call.data[ATTR_NEW_PASSCODE],
            pwd_type=passcode_type,
            start_date=_passcode_date(call.data[ATTR_START_DATE]),
            end_date=_passcode_date(call.data[ATTR_END_DATE]),
        )
    except (TTLockError, ValueError, RuntimeError) as exc:
        raise HomeAssistantError(str(exc)) from exc
    labels = await async_get_labels_manager(hass)
    old_code = call.data[ATTR_OLD_PASSCODE]
    new_code = call.data[ATTR_NEW_PASSCODE]
    old_label = labels.get_passcode_label(connection.key.lockMac, old_code)
    await labels.async_delete_passcode_meta(connection.key.lockMac, old_code)
    await labels.async_upsert_passcode_meta(
        connection.key.lockMac,
        new_code,
        passcode_type=call.data[ATTR_PASSCODE_TYPE],
        start_date=_passcode_iso(call.data[ATTR_START_DATE]),
        end_date=_passcode_iso(call.data[ATTR_END_DATE]),
    )
    if old_code != new_code and old_label:
        await labels.async_delete_passcode(connection.key.lockMac, old_code)
        await labels.async_set_passcode_label(connection.key.lockMac, new_code, old_label)


async def _async_delete_fingerprint(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.delete_fingerprint`."""
    connection = _connection_from_call(hass, call)
    labels = await async_get_labels_manager(hass)
    try:
        await connection.async_delete_fingerprint(call.data[ATTR_FINGERPRINT_NUMBER])
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    await labels.async_delete_fingerprint(
        connection.key.lockMac,
        call.data[ATTR_FINGERPRINT_NUMBER],
    )


async def _async_delete_passcode(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.delete_passcode`."""
    connection = _connection_from_call(hass, call)
    passcode_type = _passcode_type(call.data[ATTR_PASSCODE_TYPE])
    labels = await async_get_labels_manager(hass)
    try:
        await connection.async_delete_passcode(
            call.data[ATTR_PASSCODE],
            pwd_type=passcode_type,
        )
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    await labels.async_delete_passcode(connection.key.lockMac, call.data[ATTR_PASSCODE])
    await labels.async_delete_passcode_meta(
        connection.key.lockMac,
        call.data[ATTR_PASSCODE],
    )


async def _async_clear_fingerprints(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.clear_fingerprints`."""
    connection = _connection_from_call(hass, call)
    labels = await async_get_labels_manager(hass)
    try:
        await connection.async_clear_fingerprints()
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    await labels.async_clear_fingerprints(connection.key.lockMac)


async def _async_clear_passcodes(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.clear_passcodes`."""
    connection = _connection_from_call(hass, call)
    labels = await async_get_labels_manager(hass)
    try:
        await connection.async_clear_passcodes()
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc
    await labels.async_clear_passcodes(connection.key.lockMac)
    await labels.async_clear_passcode_meta(connection.key.lockMac)


async def _async_set_fingerprint_label(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.set_fingerprint_label`."""
    connection = _connection_from_call(hass, call)
    labels = await async_get_labels_manager(hass)
    await labels.async_set_fingerprint_label(
        connection.key.lockMac,
        call.data[ATTR_FINGERPRINT_NUMBER],
        call.data[ATTR_LABEL].strip(),
    )


async def _async_set_passcode_label(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.set_passcode_label`."""
    connection = _connection_from_call(hass, call)
    labels = await async_get_labels_manager(hass)
    await labels.async_set_passcode_label(
        connection.key.lockMac,
        call.data[ATTR_PASSCODE],
        call.data[ATTR_LABEL].strip(),
    )


async def _async_set_auto_lock(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle `ttlock_ble.set_auto_lock`."""
    connection = _connection_from_call(hass, call)
    try:
        await connection.async_set_auto_lock_time(call.data[ATTR_AUTO_LOCK_SECONDS])
    except TTLockError as exc:
        raise HomeAssistantError(str(exc)) from exc


def _connection_from_call(
    hass: HomeAssistant,
    call: ServiceCall,
) -> TtlockBleConnection:
    """Resolve a service call's lock identifier to a connection."""
    requested = call.data[ATTR_LOCK_MAC].strip().lower()
    registry = er.async_get(hass)
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
            for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
                if not entity_entry.unique_id.startswith(f"{mac}_"):
                    continue
                aliases.add(entity_entry.entity_id.lower())
                state = hass.states.get(entity_entry.entity_id)
                friendly_name = state.attributes.get("friendly_name") if state else None
                if isinstance(friendly_name, str):
                    aliases.add(friendly_name.lower())
            if requested in aliases:
                return connection
    raise HomeAssistantError(f"TTLock BLE lock not found: {call.data[ATTR_LOCK_MAC]}")


def _fingerprint_response(
    connection: TtlockBleConnection,
    fingerprint: Fingerprint,
    *,
    label: str | None = None,
) -> dict[str, str | None]:
    """Convert a fingerprint model to a service response payload."""
    return {
        **fingerprint.to_dict(),
        "label": label,
        "lock_mac": connection.key.lockMac,
    }


def _passcode_response(
    connection: TtlockBleConnection,
    passcode: Passcode,
    *,
    label: str | None = None,
) -> dict[str, str | None]:
    """Convert a passcode model to a service response payload."""
    return {
        **passcode.to_dict(),
        "label": label,
        "lock_mac": connection.key.lockMac,
    }


def _log_entry_response(entry: LogEntry) -> dict[str, object | None]:
    """Convert an operation log entry to a service response payload."""
    record_type = (
        entry.record_type.name.lower()
        if hasattr(entry.record_type, "name")
        else str(entry.record_type)
    )
    return {
        "record_number": entry.record_number,
        "record_type": record_type,
        "operate_date": entry.operate_date.isoformat() if entry.operate_date else None,
        "lock_battery": entry.lock_battery,
        "uid": entry.uid,
        "record_id": entry.record_id,
        "password": entry.password,
        "new_password": entry.new_password,
        "delete_date": entry.delete_date.isoformat() if entry.delete_date else None,
        "key_id": entry.key_id,
        "accessory_battery": entry.accessory_battery,
        "start_date": entry.start_date.isoformat() if entry.start_date else None,
        "end_date": entry.end_date.isoformat() if entry.end_date else None,
    }


def _passcode_iso(value: str) -> str | None:
    """Convert a TTLock passcode date into an ISO-like local timestamp."""
    normalized = value if len(value) == 12 else f"20{value}"
    if len(normalized) != 12:
        return None
    return (
        f"{normalized[0:4]}-{normalized[4:6]}-{normalized[6:8]}"
        f"T{normalized[8:10]}:{normalized[10:12]}:00"
    )


def _passcode_list_warning(*, fallback_used: bool) -> str:
    """Return a user-facing explanation for locks that reject passcode listing."""
    if fallback_used:
        return (
            "This lock rejects direct passcode listing over BLE. "
            "Showing passcodes saved locally by this Home Assistant integration."
        )
    return (
        "This lock rejects direct passcode listing over BLE. "
        "New passcodes created here will appear after they are saved locally."
    )
