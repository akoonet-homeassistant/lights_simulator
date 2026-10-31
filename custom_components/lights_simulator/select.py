"""Sélecteur du mode."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODE_LIBELLES, MODES
from .entity import EntiteSimulateur


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, ajouter: AddEntitiesCallback) -> None:
    ajouter([Mode(hass.data[DOMAIN][entry.entry_id])])


class Mode(EntiteSimulateur, SelectEntity):
    """Arrêt, Auto (alarme ou personnes) ou Forcé."""

    _attr_icon = "mdi:home-lightbulb"

    def __init__(self, moteur) -> None:
        super().__init__(moteur, "mode", "Mode")
        self._attr_options = [MODE_LIBELLES[m] for m in MODES]

    @property
    def current_option(self) -> str:
        return MODE_LIBELLES[self.moteur.mode]

    async def async_select_option(self, option: str) -> None:
        mode = next(m for m, libelle in MODE_LIBELLES.items() if libelle == option)
        await self.moteur.async_changer_mode(mode)
