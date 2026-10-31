"""Capteurs binaires : simulation en cours, maison vide, plage, pièce éclairée."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EntiteLampe, EntiteSimulateur


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, ajouter: AddEntitiesCallback) -> None:
    moteur = hass.data[DOMAIN][entry.entry_id]
    entites: list = [
        Indicateur(moteur, "actif", "Actif", "mdi:home-lightbulb", lambda m: m.actif),
        Indicateur(moteur, "maison_vide", "Maison vide", "mdi:home-export-outline", lambda m: m.vide),
        Indicateur(moteur, "plage", "Plage", "mdi:clock-time-eight-outline", lambda m: m.plage),
    ]
    entites += [Eclairee(moteur, l) for l in moteur.reglages["lampes"] if l.get("capteur")]
    ajouter(entites)


class Indicateur(EntiteSimulateur, BinarySensorEntity):
    """État général du simulateur."""

    def __init__(self, moteur, cle, nom, icone, lecture) -> None:
        super().__init__(moteur, cle, nom)
        self._attr_icon = icone
        self._lecture = lecture

    @property
    def is_on(self) -> bool:
        return bool(self._lecture(self.moteur))


class Eclairee(EntiteLampe, BinarySensorEntity):
    """La pièce de la lampe est-elle déjà éclairée (selon son capteur et son seuil) ?"""

    _attr_device_class = BinarySensorDeviceClass.LIGHT

    def __init__(self, moteur, lampe: dict) -> None:
        super().__init__(moteur, lampe, "eclairee", f"{lampe['nom']} éclairée")

    @property
    def available(self) -> bool:
        lampe = self.lampe
        return bool(lampe and self.moteur._valeur_lux(lampe.get("capteur")) is not None)

    @property
    def is_on(self) -> bool | None:
        lampe = self.lampe
        if not lampe:
            return None
        lux = self.moteur._valeur_lux(lampe.get("capteur"))
        return None if lux is None else lux >= float(lampe.get("seuil", 50))

    @property
    def extra_state_attributes(self) -> dict:
        lampe = self.lampe or {}
        return {"capteur": lampe.get("capteur"), "seuil_lx": lampe.get("seuil")}
