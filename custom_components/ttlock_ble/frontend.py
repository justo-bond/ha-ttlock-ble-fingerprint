"""Frontend registration for the TTLock BLE passcode manager panel."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PANEL_FRONTEND_URL_PATH = "ttlock-ble"
PANEL_SIDEBAR_TITLE = "TTLock"
PANEL_SIDEBAR_ICON = "mdi:lock-smart"
PANEL_WEBCOMPONENT_NAME = "ttlock-ble-panel"
PANEL_FILE_NAME = "ttlock-ble-panel.js"
PANEL_STATIC_URL = f"/{DOMAIN}/{PANEL_FILE_NAME}"

DATA_FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"


async def async_register_frontend(hass: HomeAssistant, *, version: str) -> None:
    """Register the TTLock BLE frontend assets and sidebar panel once."""
    if hass.data.get(DATA_FRONTEND_REGISTERED):
        return

    panel_path = Path(__file__).parent / "frontend" / PANEL_FILE_NAME

    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_URL, str(panel_path), cache_headers=False)],
    )

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=PANEL_FRONTEND_URL_PATH,
        webcomponent_name=PANEL_WEBCOMPONENT_NAME,
        module_url=f"{PANEL_STATIC_URL}?v={version}",
        sidebar_title=PANEL_SIDEBAR_TITLE,
        sidebar_icon=PANEL_SIDEBAR_ICON,
        require_admin=True,
        embed_iframe=False,
    )

    hass.data[DATA_FRONTEND_REGISTERED] = True
