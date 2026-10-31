"""Capteurs : état, démarrage, fin, lampes allumées, journal, soleil."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import EntiteSimulateur


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, ajouter: AddEntitiesCallback) -> None:
    m = hass.data[DOMAIN][entry.entry_id]
    ajouter([
        Texte(m, "etat", "État", "mdi:home-lightbulb-outline", lambda m: m.texte_etat()),
        Texte(m, "demarrage", "Démarrage", "mdi:clock-start", lambda m: m.texte_demarrage()),
        FinCeSoir(m),
        LampesAllumees(m),
        DerniereAction(m),
        Texte(m, "lever_du_soleil", "Lever du soleil", "mdi:weather-sunset-up",
              lambda m: m.texte_soleil(SUN_EVENT_SUNRISE)),
        Texte(m, "coucher_du_soleil", "Coucher du soleil", "mdi:weather-sunset-down",
              lambda m: m.texte_soleil(SUN_EVENT_SUNSET)),
    ])


class Texte(EntiteSimulateur, SensorEntity):
    """Capteur texte calculé par le moteur."""

    def __init__(self, moteur, cle, nom, icone, lecture) -> None:
        super().__init__(moteur, cle, nom)
        self._attr_icon = icone
        self._lecture = lecture

    @property
    def native_value(self) -> str:
        return str(self._lecture(self.moteur))[:255]


class FinCeSoir(EntiteSimulateur, SensorEntity):
    """Fin tirée au hasard pour la soirée."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-end"

    def __init__(self, moteur) -> None:
        super().__init__(moteur, "fin_ce_soir", "Fin ce soir")

    @property
    def native_value(self) -> datetime | None:
        return self.moteur._fin_soir_affichee(dt_util.now())


class LampesAllumees(EntiteSimulateur, SensorEntity):
    """Lampes allumées par le simulateur et temps restant (pour un badge)."""

    _attr_icon = "mdi:lightbulb-group"

    def __init__(self, moteur) -> None:
        super().__init__(moteur, "lampes_allumees", "Lampes allumées")

    @property
    def native_value(self) -> str:
        return self.moteur.texte_lampes()[:255]

    @property
    def extra_state_attributes(self) -> dict:
        return {"lampes": self.moteur.lampes_allumees(), "nombre": len(self.moteur.allumees)}


class DerniereAction(EntiteSimulateur, SensorEntity):
    """Dernière ligne du journal (les 10 dernières en attribut)."""

    _attr_icon = "mdi:text-box-outline"

    def __init__(self, moteur) -> None:
        super().__init__(moteur, "derniere_action", "Dernière action")

    @property
    def native_value(self) -> str | None:
        if not self.moteur.journal:
            return None
        ligne = self.moteur.journal[0]
        heure = dt_util.as_local(dt_util.parse_datetime(ligne["t"])).strftime("%H:%M")
        return f"{heure} · {ligne['texte']}"[:255]

    @property
    def extra_state_attributes(self) -> dict:
        return {"journal": self.moteur.journal[:10]}
