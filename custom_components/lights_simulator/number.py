"""Un poids par lampe (0 = jamais, 5 = souvent et longtemps)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EntiteLampe


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, ajouter: AddEntitiesCallback) -> None:
    moteur = hass.data[DOMAIN][entry.entry_id]
    ajouter([Poids(moteur, l) for l in moteur.reglages["lampes"]])


class Poids(EntiteLampe, NumberEntity):
    """Fréquence et durée relatives de la lampe."""

    _attr_icon = "mdi:scale-balance"
    _attr_native_min_value = 0
    _attr_native_max_value = 5
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, moteur, lampe: dict) -> None:
        super().__init__(moteur, lampe, "poids", f"{lampe['nom']} poids")

    @property
    def native_value(self) -> float:
        return float((self.lampe or {}).get("poids", 0))

    async def async_set_native_value(self, value: float) -> None:
        await self.maj_lampe(poids=int(value))
