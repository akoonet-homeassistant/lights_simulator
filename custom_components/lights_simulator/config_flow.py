"""Assistant d'installation de Lights Simulator."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import DECL_ALARME, DECL_LES_DEUX, DECL_PERSONNES, DECLENCHEURS, DOMAIN, NOM_APPAREIL, reglages_par_defaut
from .importation import anciens_reglages_presents, importer, lampes_depuis_entites, mode_ancien


class LightsSimulatorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Une seule instance : déclencheur, lampes, reprise éventuelle de l'ancien simulateur."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Première et unique étape."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        erreurs: dict[str, str] = {}
        ancien = anciens_reglages_presents(self.hass)
        if user_input is not None:
            declencheur = user_input["declencheur"]
            alarme = user_input.get("alarme")
            personnes = user_input.get("personnes") or []
            if declencheur in (DECL_ALARME, DECL_LES_DEUX) and not alarme:
                erreurs["alarme"] = "alarme_requise"
            if declencheur in (DECL_PERSONNES, DECL_LES_DEUX) and not personnes:
                erreurs["personnes"] = "personnes_requises"
            if not user_input.get("lampes"):
                erreurs["lampes"] = "lampes_requises"
            if not erreurs:
                reglages = reglages_par_defaut()
                reglages.update(declencheur=declencheur, alarme=alarme, personnes=personnes)
                reglages["lampes"] = lampes_depuis_entites(self.hass, user_input["lampes"])
                donnees: dict[str, Any] = {}
                if ancien and user_input.get("importer"):
                    reglages = importer(self.hass, reglages)
                    donnees["mode_initial"] = mode_ancien(self.hass)
                return self.async_create_entry(title=NOM_APPAREIL, data=donnees, options=reglages)

        champs: dict[Any, Any] = {
            vol.Required("declencheur", default=DECL_ALARME): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DECLENCHEURS, translation_key="declencheur",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional("alarme"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="alarm_control_panel")
            ),
            vol.Optional("personnes"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person", multiple=True)
            ),
            vol.Required("lampes"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="light", multiple=True)
            ),
        }
        if ancien:
            champs[vol.Optional("importer", default=True)] = selector.BooleanSelector()
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(vol.Schema(champs), user_input or {}),
            errors=erreurs,
        )
