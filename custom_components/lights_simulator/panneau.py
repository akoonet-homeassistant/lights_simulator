"""Panneau latéral : enregistrement, affichage ou masquage dans la barre latérale."""

from __future__ import annotations

from homeassistant.components import panel_custom
from homeassistant.components.frontend import async_remove_panel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_ELEMENT, PANEL_ICON, PANEL_TITLE, PANEL_URL, STATIC_URL, VERSION

CLE_VISIBLE = f"{DOMAIN}_panneau_visible"


def visible_dans_options(entry: ConfigEntry) -> bool:
    """Réglage « afficher dans la barre latérale » (oui par défaut)."""
    return bool(entry.options.get("barre_laterale", True))


async def async_installer_panneau(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Enregistre le panneau, visible ou non dans la barre latérale.

    Masqué, le panneau reste ouvert à l'adresse /lights-simulator (carte Lovelace,
    bouton « Configurer » de l'intégration).
    """
    visible = visible_dans_options(entry)
    if hass.data.get(CLE_VISIBLE) is not None:
        if hass.data[CLE_VISIBLE] == visible:
            return
        async_remove_panel(hass, PANEL_URL)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_ELEMENT,
        frontend_url_path=PANEL_URL,
        module_url=f"{STATIC_URL}/{PANEL_ELEMENT}.js?v={VERSION}",
        sidebar_title=PANEL_TITLE if visible else None,
        sidebar_icon=PANEL_ICON if visible else None,
        require_admin=False,
        config={"entry_id": entry.entry_id},
    )
    hass.data[CLE_VISIBLE] = visible


def async_retirer_panneau(hass: HomeAssistant) -> None:
    """Retire le panneau (déchargement de l'intégration)."""
    if hass.data.pop(CLE_VISIBLE, None) is not None:
        async_remove_panel(hass, PANEL_URL)
