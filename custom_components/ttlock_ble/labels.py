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
            "passcode_meta": {},
            "camera_entities": {},
            "history_media": {},
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

    def get_passcode_meta(self, lock_mac: str) -> list[dict[str, str | None]]:
        """Return locally cached passcode metadata for one lock."""
        assert self._data is not None
        scoped = self._data["passcode_meta"].get(lock_mac, {})
        return [dict(item) for item in scoped.values()]

    async def async_upsert_passcode_meta(
        self,
        lock_mac: str,
        code: str,
        *,
        passcode_type: str,
        start_date: str | None,
        end_date: str | None,
    ) -> None:
        """Store local metadata for one passcode managed through HA."""
        assert self._data is not None
        scoped = self._data["passcode_meta"].setdefault(lock_mac, {})
        scoped[code] = {
            "code": code,
            "type": passcode_type,
            "start_date": start_date,
            "end_date": end_date,
        }
        await self._store.async_save(self._data)

    async def async_delete_passcode_meta(self, lock_mac: str, code: str) -> None:
        """Remove local metadata for one passcode."""
        assert self._data is not None
        scoped = self._data["passcode_meta"].get(lock_mac, {})
        scoped.pop(code, None)
        if not scoped:
            self._data["passcode_meta"].pop(lock_mac, None)
        await self._store.async_save(self._data)

    async def async_clear_passcode_meta(self, lock_mac: str) -> None:
        """Clear all locally cached passcode metadata for one lock."""
        assert self._data is not None
        self._data["passcode_meta"].pop(lock_mac, None)
        await self._store.async_save(self._data)

    def get_camera_entity(self, lock_mac: str) -> str | None:
        """Return the linked camera entity for one lock, if configured."""
        assert self._data is not None
        return self._data["camera_entities"].get(lock_mac)

    async def async_set_camera_entity(self, lock_mac: str, entity_id: str) -> None:
        """Store or clear the linked camera entity for one lock."""
        assert self._data is not None
        if entity_id:
            self._data["camera_entities"][lock_mac] = entity_id
        else:
            self._data["camera_entities"].pop(lock_mac, None)
        await self._store.async_save(self._data)

    def get_history_media(
        self,
        lock_mac: str,
        history_key: str,
    ) -> dict[str, str] | None:
        """Return locally linked media for one history record, if any."""
        assert self._data is not None
        scoped = self._data["history_media"].get(lock_mac, {})
        item = scoped.get(history_key)
        return dict(item) if item else None

    async def async_set_history_media(
        self,
        lock_mac: str,
        history_key: str,
        *,
        media_url: str,
        content_type: str,
        label: str,
    ) -> None:
        """Store or replace media attached to one history record."""
        assert self._data is not None
        scoped = self._data["history_media"].setdefault(lock_mac, {})
        scoped[history_key] = {
            "media_url": media_url,
            "content_type": content_type,
            "label": label,
        }
        await self._store.async_save(self._data)

    async def async_delete_history_media(self, lock_mac: str, history_key: str) -> None:
        """Delete one linked media item from lock history."""
        assert self._data is not None
        scoped = self._data["history_media"].get(lock_mac, {})
        scoped.pop(history_key, None)
        if not scoped:
            self._data["history_media"].pop(lock_mac, None)
        await self._store.async_save(self._data)


async def async_get_labels_manager(hass: HomeAssistant) -> TtlockBleLabelsManager:
    """Return the singleton labels manager for this HA instance."""
    manager = hass.data.get(DATA_MANAGER)
    if manager is None:
        manager = TtlockBleLabelsManager(hass)
        await manager.async_load()
        hass.data[DATA_MANAGER] = manager
    return manager
