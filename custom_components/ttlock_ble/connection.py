"""
Persistent BLE connection wrapper for ttlock_ble.

Each `TtlockBleConnection` owns a long-lived `TTLockClient` for a single
`VirtualKey`, runs a background reconnect loop, and serializes state
queries and lock commands through a single `asyncio.Lock`. Push events
arriving on that connection are dispatched live via HA's dispatcher
under the signal `ttlock_ble_event_<mac>`.

The reconnect loop waits on an `asyncio.Event` that the SDK's
`disconnected_callback` toggles, so the watchdog wakes up the instant
the BLE link drops instead of poll-sleeping.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ttlock_ble import KeyboardPwdType, TTLockClient, TTLockError

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from bleak import BleakClient
    from homeassistant.core import HomeAssistant

    from ttlock_ble import LockEvent, LockState, LogEntry, VirtualKey
    from ttlock_ble.models import Fingerprint, Passcode


RECONNECT_INITIAL_BACKOFF = 1.0
RECONNECT_MAX_BACKOFF = 300.0
RECONNECT_COOLDOWN_SECONDS = 3600.0


def event_signal(mac: str) -> str:
    """Dispatcher signal that carries `LockEvent`s for `mac`."""
    return f"{DOMAIN}_event_{mac.lower()}"


def log_signal(mac: str) -> str:
    """Dispatcher signal that carries `LogEntry` records for `mac`."""
    return f"{DOMAIN}_log_{mac.lower()}"


def connection_signal(mac: str) -> str:
    """Dispatcher signal that carries BLE up/down transitions for `mac`."""
    return f"{DOMAIN}_connection_{mac.lower()}"


def fingerprint_signal(mac: str) -> str:
    """Dispatcher signal that carries the cached fingerprint list for `mac`."""
    return f"{DOMAIN}_fingerprints_{mac.lower()}"


def passcode_signal(mac: str) -> str:
    """Dispatcher signal that carries the cached passcode list for `mac`."""
    return f"{DOMAIN}_passcodes_{mac.lower()}"


class TtlockBleConnection:
    """Maintain a long-lived BLE session with one TTLock lock."""

    def __init__(self, hass: HomeAssistant, key: VirtualKey) -> None:
        """Bind to the HA instance and the credentials for a single lock."""
        self._hass = hass
        self._key = key
        self._client: TTLockClient | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self._disconnected = asyncio.Event()
        self._cooldown_until: float = 0.0
        self._seen_records: set[int] = set()
        self._fingerprints: list[Fingerprint] | None = None
        self._passcodes: list[Passcode] | None = None

    @property
    def key(self) -> VirtualKey:
        """Return the `VirtualKey` this connection wraps."""
        return self._key

    @property
    def fingerprints(self) -> list[Fingerprint] | None:
        """Return the last fingerprint list read from the lock, if known."""
        return self._fingerprints

    @property
    def passcodes(self) -> list[Passcode] | None:
        """Return the last passcode list read from the lock, if known."""
        return self._passcodes

    @property
    def is_connected(self) -> bool:
        """True iff the underlying `TTLockClient` is currently connected."""
        return self._client is not None and self._client.is_connected

    async def async_start(self) -> None:
        """Begin maintaining the BLE connection in the background."""
        if self._task is not None:
            return
        self._closing = False
        self._task = self._hass.async_create_background_task(
            self._async_maintain(),
            name=f"ttlock_ble.connection.{self._key.lockMac}",
        )

    async def async_stop(self) -> None:
        """Cancel the background loop and release the BLE connection."""
        self._closing = True
        self._disconnected.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        async with self._lock:
            await self._async_disconnect_locked()

    async def async_query_state(
        self,
        *,
        force_cooldown_bypass: bool = False,
    ) -> tuple[LockState | None, int | None] | None:
        """
        Return `(lock_state, battery)` through the live connection.

        Returns `None` immediately while a long-backoff cooldown is in
        effect — letting periodic coordinator polls hammer the lock would
        defeat the very cooldown the maintain loop entered. User-driven
        callers (`async_lock`/`async_unlock`, or the lock entity's
        post-command follow-up) opt out via `force_cooldown_bypass=True`.
        """
        if not force_cooldown_bypass and time.monotonic() < self._cooldown_until:
            LOGGER.debug(
                "Skipping query for %s — connection cooldown active",
                self._key.lockMac,
            )
            return None
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                return None
            try:
                return await client.query_state()
            except TTLockError as exc:
                LOGGER.warning(
                    "query_state failed for %s: %s",
                    self._key.lockMac,
                    exc,
                )
                await self._async_disconnect_locked()
                return None

    async def async_lock(self) -> None:
        """Send a LOCK command on the live connection (raises on failure)."""
        await self._async_run_command("lock")

    async def async_unlock(self) -> None:
        """Send an UNLOCK command on the live connection (raises on failure)."""
        await self._async_run_command("unlock")

    async def async_get_operation_log(self, *, dispatch: bool = True) -> list[LogEntry]:
        """Fetch operation records from the lock and dispatch new ones."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                LOGGER.warning("get_operation_log: no client for %s", self._key.lockMac)
                return []
            try:
                entries = await client.get_operation_log()
            except TTLockError as exc:
                LOGGER.warning(
                    "get_operation_log failed for %s: %s",
                    self._key.lockMac,
                    exc,
                )
                return []
        LOGGER.debug(
            "get_operation_log for %s: %d entries, seen=%d",
            self._key.lockMac,
            len(entries),
            len(self._seen_records),
        )
        new_entries: list[LogEntry] = []
        for entry in entries:
            if entry.record_number not in self._seen_records:
                self._seen_records.add(entry.record_number)
                new_entries.append(entry)
        if new_entries and dispatch:
            LOGGER.debug(
                "Lock %s: dispatching %d new log entries",
                self._key.lockMac,
                len(new_entries),
            )
            for entry in new_entries:
                async_dispatcher_send(
                    self._hass,
                    log_signal(self._key.lockMac),
                    entry,
                )
        return new_entries

    async def async_add_fingerprint(
        self,
        *,
        start_date: str,
        end_date: str,
        scan_timeout: float,
    ) -> Fingerprint:
        """Scan and store a fingerprint through the live BLE connection."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                fingerprint = await client.add_fingerprint(
                    start_date=start_date,
                    end_date=end_date,
                    scan_timeout=scan_timeout,
                )
            except TTLockError:
                await self._async_disconnect_locked()
                raise
            if self._fingerprints is not None:
                self._fingerprints = [
                    item
                    for item in self._fingerprints
                    if item.fingerprint_number != fingerprint.fingerprint_number
                ]
                self._fingerprints.append(fingerprint)
                self._broadcast_fingerprints()
            with contextlib.suppress(TTLockError):
                await self._async_refresh_fingerprints_locked(client)
            return fingerprint

    async def async_get_fingerprints(self) -> list[Fingerprint]:
        """Read fingerprint credentials from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                return await self._async_refresh_fingerprints_locked(client)
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_update_fingerprint(
        self,
        fingerprint_number: str,
        *,
        start_date: str,
        end_date: str,
    ) -> None:
        """Update one fingerprint validity window."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                await client.update_fingerprint(
                    fingerprint_number,
                    start_date=start_date,
                    end_date=end_date,
                )
                if self._fingerprints is not None:
                    await self._async_refresh_fingerprints_locked(client)
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_delete_fingerprint(self, fingerprint_number: str) -> None:
        """Delete one fingerprint from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                await client.delete_fingerprint(fingerprint_number)
                if self._fingerprints is not None:
                    self._fingerprints = [
                        item
                        for item in self._fingerprints
                        if item.fingerprint_number != fingerprint_number
                    ]
                    self._broadcast_fingerprints()
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_clear_fingerprints(self) -> None:
        """Delete all fingerprints from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                await client.clear_fingerprints()
                self._fingerprints = []
                self._broadcast_fingerprints()
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_get_passcodes(self) -> list[Passcode]:
        """Read keypad passcodes from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                return await self._async_refresh_passcodes_locked(client)
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_add_passcode(
        self,
        code: str,
        *,
        pwd_type: KeyboardPwdType,
        start_date: str,
        end_date: str,
    ) -> None:
        """Create one keypad passcode on the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                await client.add_passcode(
                    code,
                    pwd_type=pwd_type,
                    start_date=start_date,
                    end_date=end_date,
                )
                if self._passcodes is not None:
                    await self._async_refresh_passcodes_locked(client)
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_update_passcode(
        self,
        old_code: str,
        new_code: str,
        *,
        pwd_type: KeyboardPwdType,
        start_date: str,
        end_date: str,
    ) -> None:
        """Update one keypad passcode on the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                await client.update_passcode(
                    old_code,
                    new_code,
                    pwd_type=pwd_type,
                    start_date=start_date,
                    end_date=end_date,
                )
                if self._passcodes is not None:
                    await self._async_refresh_passcodes_locked(client)
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_delete_passcode(
        self,
        code: str,
        *,
        pwd_type: KeyboardPwdType,
    ) -> None:
        """Delete one keypad passcode from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                await client.delete_passcode(code, pwd_type=pwd_type)
                if self._passcodes is not None:
                    self._passcodes = [
                        item for item in self._passcodes if item.code != code
                    ]
                    self._broadcast_passcodes()
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def async_clear_passcodes(self) -> None:
        """Delete all keypad passcodes from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                await client.clear_passcodes()
                self._passcodes = []
                self._broadcast_passcodes()
            except TTLockError:
                await self._async_disconnect_locked()
                raise

    async def _async_refresh_fingerprints_locked(
        self,
        client: TTLockClient,
    ) -> list[Fingerprint]:
        """Read fingerprints, cache them, and notify HA entities."""
        self._fingerprints = await client.get_fingerprints()
        self._broadcast_fingerprints()
        return self._fingerprints

    async def _async_refresh_passcodes_locked(
        self,
        client: TTLockClient,
    ) -> list[Passcode]:
        """Read passcodes, cache them, and notify HA entities."""
        self._passcodes = await client.get_passcodes()
        self._broadcast_passcodes()
        return self._passcodes

    async def _async_run_command(self, action: str) -> None:
        """
        Acquire the lock, ensure connected, then call `lock`/`unlock`.

        Catches `asyncio.TimeoutError` as a defensive belt-and-suspenders
        in case a future SDK release lets one slip through; converts it
        to `TTLockError` so callers only ever see the integration's own
        exception hierarchy.
        """
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                if action == "lock":
                    await client.lock()
                else:
                    await client.unlock()
            except TTLockError:
                await self._async_disconnect_locked()
                raise
            except TimeoutError as exc:
                await self._async_disconnect_locked()
                msg = f"Lock {self._key.lockMac} timed out responding to {action}"
                raise TTLockError(msg) from exc

    async def _async_ensure_connected_locked(self) -> TTLockClient | None:
        """
        Return a live client, opening a new BLE session if needed.

        Caller must hold `self._lock`. Returns `None` on failure (lock
        not discoverable or BLE connect raised).
        """
        if self._client is not None and self._client.is_connected:
            return self._client
        await self._async_disconnect_locked()
        device = async_ble_device_from_address(
            self._hass,
            self._key.lockMac,
            connectable=True,
        )
        if device is None:
            return None
        client = TTLockClient.from_ble_device(
            device,
            self._key,
            disconnected_callback=self._on_disconnected,
        )
        try:
            await client.connect()
        except TTLockError as exc:
            LOGGER.debug("BLE connect failed for %s: %s", self._key.lockMac, exc)
            return None
        client.add_event_listener(self._on_event)
        self._client = client
        self._disconnected.clear()
        self._broadcast_connection_state(connected=True)
        return client

    async def _async_disconnect_locked(self) -> None:
        """Tear down the BLE session if up. Caller must hold `self._lock`."""
        if self._client is None:
            return
        client = self._client
        self._client = None
        self._broadcast_connection_state(connected=False)
        client.remove_event_listener(self._on_event)
        with contextlib.suppress(Exception):
            await client.disconnect()

    def _broadcast_connection_state(self, *, connected: bool) -> None:
        """Notify subscribers that the BLE link to this lock just changed."""
        async_dispatcher_send(
            self._hass,
            connection_signal(self._key.lockMac),
            connected,
        )

    def _broadcast_fingerprints(self) -> None:
        """Notify subscribers that the cached fingerprint list changed."""
        async_dispatcher_send(
            self._hass,
            fingerprint_signal(self._key.lockMac),
            self._fingerprints,
        )

    def _broadcast_passcodes(self) -> None:
        """Notify subscribers that the cached passcode list changed."""
        async_dispatcher_send(
            self._hass,
            passcode_signal(self._key.lockMac),
            self._passcodes,
        )

    def _on_event(self, event: LockEvent) -> None:
        """Forward a push event onto HA's dispatcher (called by the BLE layer)."""
        async_dispatcher_send(
            self._hass,
            event_signal(self._key.lockMac),
            event,
        )

    def _on_disconnected(self, _client: BleakClient) -> None:
        """Wake the maintain loop the moment bleak signals a drop."""
        self._disconnected.set()

    async def _async_maintain(self) -> None:
        """
        Background loop that opens one BLE session and cools down on drop.

        After any disconnect, sleeps `RECONNECT_COOLDOWN_SECONDS` before
        reconnecting. No immediate retry — locks that drop us aggressively
        (TTLock's idle-sleep) would otherwise produce a reconnect storm
        that drains the lock's battery. Connect failures (device not yet
        advertising) use a separate exponential backoff so first-boot
        scans don't wait the full cooldown.
        """
        backoff = RECONNECT_INITIAL_BACKOFF
        while not self._closing:
            try:
                async with self._lock:
                    client = await self._async_ensure_connected_locked()
                if client is None:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, RECONNECT_MAX_BACKOFF)
                    continue
                backoff = RECONNECT_INITIAL_BACKOFF
                await self._disconnected.wait()
                self._cooldown_until = time.monotonic() + RECONNECT_COOLDOWN_SECONDS
                try:
                    await asyncio.sleep(RECONNECT_COOLDOWN_SECONDS)
                finally:
                    self._cooldown_until = 0.0
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                LOGGER.exception(
                    "Connection maintenance error for %s",
                    self._key.lockMac,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX_BACKOFF)
