"""Un interrupteur par lampe : utilisée ou non par le simulateur."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EntiteLampe


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, ajouter: AddEntitiesCallback) -> None:
    moteur = hass.data[DOMAIN][entry.entry_id]
    ajouter([Utilisee(moteur, l) for l in moteur.reglages["lampes"]])


class Utilisee(EntiteLampe, SwitchEntity):
    """La lampe fait-elle partie de la simulation ?"""

    _attr_icon = "mdi:lightbulb-auto"

    def __init__(self, moteur, lampe: dict) -> None:
        super().__init__(moteur, lampe, "utilisee", lampe["nom"])

    @property
    def is_on(self) -> bool:
        return bool((self.lampe or {}).get("utilisee"))

    @property
    def extra_state_attributes(self) -> dict:
        return {"lampe": (self.lampe or {}).get("entity_id")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.maj_lampe(utilisee=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.maj_lampe(utilisee=False)
