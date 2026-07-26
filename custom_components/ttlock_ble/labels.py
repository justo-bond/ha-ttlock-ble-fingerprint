"""Persistent local labels for TTLock credentials."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_KEY = f"{DOMAIN}_labels"
STORAGE_VERSION = 1
DATA_MANAGER = f"{DOMAIN}_labels_manager"


class TtlockBleLabelsManager:
    """Persist local labels for passcodes and fingerprints."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Load labels from storage once."""
        if self._data is not None:
            return
        self._data = await self._store.async_load() or {
            "passcodes": {},
            "fingerprints": {},
        }

    def get_passcode_label(self, lock_mac: str, code: str) -> str | None:
        """Return the local label for one passcode, if set."""
        assert self._data is not None
        return self._data["passcodes"].get(lock_mac, {}).get(code)

    def get_fingerprint_label(
        self,
        lock_mac: str,
        fingerprint_number: str,
    ) -> str | None:
        """Return the local label for one fingerprint, if set."""
        assert self._data is not None
        return self._data["fingerprints"].get(lock_mac, {}).get(fingerprint_number)

    async def async_set_passcode_label(
        self,
        lock_mac: str,
        code: str,
        label: str,
    ) -> None:
        """Create/update or clear one passcode label."""
        assert self._data is not None
        scoped = self._data["passcodes"].setdefault(lock_mac, {})
        if label:
            scoped[code] = label
        else:
            scoped.pop(code, None)
        if not scoped:
            self._data["passcodes"].pop(lock_mac, None)
        await self._store.async_save(self._data)

    async def async_set_fingerprint_label(
        self,
        lock_mac: str,
        fingerprint_number: str,
        label: str,
    ) -> None:
        """Create/update or clear one fingerprint label."""
        assert self._data is not None
        scoped = self._data["fingerprints"].setdefault(lock_mac, {})
        if label:
            scoped[fingerprint_number] = label
        else:
            scoped.pop(fingerprint_number, None)
        if not scoped:
            self._data["fingerprints"].pop(lock_mac, None)
        await self._store.async_save(self._data)

    async def async_delete_passcode(self, lock_mac: str, code: str) -> None:
        """Remove one passcode label after deleting the credential."""
        await self.async_set_passcode_label(lock_mac, code, "")

    async def async_delete_fingerprint(
        self,
        lock_mac: str,
        fingerprint_number: str,
    ) -> None:
        """Remove one fingerprint label after deleting the credential."""
        await self.async_set_fingerprint_label(lock_mac, fingerprint_number, "")

    async def async_clear_passcodes(self, lock_mac: str) -> None:
        """Clear all passcode labels for one lock."""
        assert self._data is not None
        self._data["passcodes"].pop(lock_mac, None)
        await self._store.async_save(self._data)

    async def async_clear_fingerprints(self, lock_mac: str) -> None:
        """Clear all fingerprint labels for one lock."""
        assert self._data is not None
        self._data["fingerprints"].pop(lock_mac, None)
        await self._store.async_save(self._data)


async def async_get_labels_manager(hass: HomeAssistant) -> TtlockBleLabelsManager:
    """Return the singleton labels manager for this HA instance."""
    manager = hass.data.get(DATA_MANAGER)
    if manager is None:
        manager = TtlockBleLabelsManager(hass)
        await manager.async_load()
        hass.data[DATA_MANAGER] = manager
    return manager
