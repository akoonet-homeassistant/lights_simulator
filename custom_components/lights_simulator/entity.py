"""Base commune des entités de Lights Simulator."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NOM_APPAREIL, PANEL_URL, SIGNAL_MAJ, VERSION
from .engine import Moteur


class EntiteSimulateur(Entity):
    """Entité rattachée à l'appareil « Lights Simulator », mise à jour par le moteur."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, moteur: Moteur, cle: str, nom: str) -> None:
        self.moteur = moteur
        self._attr_unique_id = f"{moteur.entry.entry_id}_{cle}"
        self._attr_name = nom
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, moteur.entry.entry_id)},
            name=NOM_APPAREIL,
            manufacturer="akoonet",
            model="Simulation de présence",
            sw_version=VERSION,
            # Lien « Ouvrir » sur la fiche de l'appareil : mène au panneau même s'il est masqué
            configuration_url=f"homeassistant://{PANEL_URL}",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_MAJ.format(self.moteur.entry.entry_id), self.async_write_ha_state
            )
        )


class EntiteLampe(EntiteSimulateur):
    """Entité propre à une lampe."""

    def __init__(self, moteur: Moteur, lampe: dict, cle: str, nom: str) -> None:
        super().__init__(moteur, f"lampe_{lampe['id']}_{cle}", nom)
        self.lampe_id = lampe["id"]

    @property
    def lampe(self) -> dict | None:
        return self.moteur.lampe(self.lampe_id)

    async def maj_lampe(self, **valeurs) -> None:
        """Modifie un réglage de la lampe (sans rechargement)."""
        reglages = self.moteur.reglages
        for lampe in reglages["lampes"]:
            if lampe["id"] == self.lampe_id:
                lampe.update(valeurs)
        await self.moteur.async_maj_reglages(reglages)
