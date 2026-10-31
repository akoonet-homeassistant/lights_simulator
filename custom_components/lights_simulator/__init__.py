"""Lights Simulator : simulation de présence par les lumières."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.frontend import add_extra_js_url, async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from . import websocket
from .const import (
    CARD_ELEMENT,
    DOMAIN,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL,
    STATIC_URL,
    VERSION,
)
from .engine import Moteur

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]
CLE_FRONTEND = f"{DOMAIN}_frontend"

_LOGGER = logging.getLogger(__name__)


async def _preparer_frontend(hass: HomeAssistant) -> None:
    """Fichiers du panneau et de la carte (une seule fois par démarrage de HA)."""
    if hass.data.get(CLE_FRONTEND):
        return
    dossier = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(dossier), False)]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/{CARD_ELEMENT}.js?v={VERSION}")
    websocket.async_enregistrer(hass)
    hass.data[CLE_FRONTEND] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Démarre le simulateur."""
    await _preparer_frontend(hass)
    moteur = Moteur(hass, entry)
    await moteur.async_demarrer()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = moteur

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_ELEMENT,
        frontend_url_path=PANEL_URL,
        module_url=f"{STATIC_URL}/{PANEL_ELEMENT}.js?v={VERSION}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=True,
        config={"entry_id": entry.entry_id},
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Arrête le simulateur sans toucher aux lampes (elles reprennent au rechargement)."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        moteur: Moteur = hass.data[DOMAIN].pop(entry.entry_id)
        await moteur.async_arreter()
        async_remove_panel(hass, PANEL_URL)
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Suppression : éteint les lampes encore allumées par le simulateur et efface son état."""
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    donnees = await store.async_load() or {}
    for entity_id in donnees.get("allumees", {}):
        try:
            await hass.services.async_call("light", "turn_off", {"entity_id": entity_id}, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Extinction de %s impossible à la suppression : %s", entity_id, err)
    await store.async_remove()
