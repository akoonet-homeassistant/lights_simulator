"""Moteur de Lights Simulator : décide quand allumer et éteindre les lampes."""

from __future__ import annotations

import asyncio
import copy
import logging
import random
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    BORNE_LUX,
    DECL_ALARME,
    DECL_LES_DEUX,
    DECL_PERSONNES,
    DOMAIN,
    FORMAT_SAUVEGARDE,
    JOURNAL_MAX,
    JOURS_LONGS,
    MODE_ARRET,
    MODE_AUTO,
    MODE_FORCE,
    SAUVEGARDES_MAX,
    SI_ECLAIREE_ACTION,
    SI_ECLAIREE_AUTRE,
    SIGNAL_MAJ,
    VERSION,
    lampe_par_defaut,
    reglages_par_defaut,
)

_LOGGER = logging.getLogger(__name__)

INDISPONIBLE = ("unknown", "unavailable", "", None)
INTERVALLE = timedelta(seconds=30)


def fusion(defaut: Any, valeur: Any) -> Any:
    """Complète des réglages avec les valeurs par défaut (récursif sur les dict)."""
    if isinstance(defaut, dict) and isinstance(valeur, dict):
        res = copy.deepcopy(defaut)
        for cle, val in valeur.items():
            res[cle] = fusion(defaut.get(cle), val) if cle in defaut else copy.deepcopy(val)
        return res
    if valeur is None:
        return copy.deepcopy(defaut)
    return copy.deepcopy(valeur)


class Moteur:
    """État et logique d'une instance de Lights Simulator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.rng = random.Random()
        self.verrou = asyncio.Lock()
        self._desabonnements: list = []
        self._minuteries: dict[str, Any] = {}

        # État persistant
        self.mode: str = MODE_AUTO
        self.allumees: dict[str, float] = {}
        self.echecs: dict[str, float] = {}
        self.fins: dict[str, float] = {}
        self.lux_soir: dict[str, float] = {}
        self.lux_matin: dict[str, float] = {}
        self.lux_sous_depuis: float | None = None
        self.journal: list[dict] = []
        self.demarree: float | None = None
        self.prochain: float = 0
        self.vide: bool = False
        self.arme_depuis: float | None = None
        self.actif: bool = False
        self.sauvegardes: list[dict] = []

        # État calculé
        self.plage: bool = False
        self.fin_seance: datetime | None = None
        self.type_seance: str | None = None

    # ------------------------------------------------------------------ réglages

    @property
    def reglages(self) -> dict:
        """Réglages complets (options de l'entrée complétées par les défauts, lampes comprises)."""
        reglages = fusion(reglages_par_defaut(), dict(self.entry.options))
        reglages["lampes"] = [
            fusion(lampe_par_defaut(l.get("id", ""), l.get("entity_id", ""), l.get("nom") or l.get("entity_id", "")), l)
            for l in reglages.get("lampes") or []
            if isinstance(l, dict)
        ]
        return reglages

    def lampe(self, lampe_id: str) -> dict | None:
        """Réglages d'une lampe par son identifiant."""
        return next((l for l in self.reglages["lampes"] if l["id"] == lampe_id), None)

    def lampe_par_entite(self, entity_id: str) -> dict | None:
        """Réglages d'une lampe par son entité lumière."""
        return next((l for l in self.reglages["lampes"] if l["entity_id"] == entity_id), None)

    async def async_maj_reglages(self, nouveaux: dict, recharger: bool = False) -> None:
        """Enregistre de nouveaux réglages ; recharge l'intégration si les lampes changent."""
        anciens = self.reglages
        suivies_avant = self._entites_suivies()
        self.hass.config_entries.async_update_entry(self.entry, options=nouveaux)
        recharger = recharger or self._entites_suivies() != suivies_avant
        if (anciens["soir"].get("fin"), anciens["soir"].get("variation")) != (
            nouveaux.get("soir", {}).get("fin"),
            nouveaux.get("soir", {}).get("variation"),
        ):
            self._oublier_fins_futures()
        if recharger:
            await self._sauver_maintenant()
            self.hass.async_create_task(self.hass.config_entries.async_reload(self.entry.entry_id))
            return
        await self.async_evaluer()

    def _oublier_fins_futures(self) -> None:
        """Après un changement de fin ou de variation, retire les tirages pas encore commencés."""
        maintenant = dt_util.now().timestamp()
        en_cours = self.fin_seance.timestamp() if self.fin_seance and self.type_seance == "soir" else None
        self.fins = {j: t for j, t in self.fins.items() if t <= maintenant or t == en_cours}

    # ---------------------------------------------------------------- démarrage

    async def async_demarrer(self) -> None:
        """Charge l'état sauvegardé et branche les écoutes."""
        donnees = await self.store.async_load() or {}
        self.mode = donnees.get("mode", self.entry.data.get("mode_initial", MODE_AUTO))
        self.allumees = donnees.get("allumees", {})
        self.echecs = donnees.get("echecs", {})
        self.fins = donnees.get("fins", {})
        self.lux_soir = donnees.get("lux_soir", {})
        self.lux_matin = donnees.get("lux_matin", {})
        self.lux_sous_depuis = donnees.get("lux_sous_depuis")
        self.journal = donnees.get("journal", [])
        self.demarree = donnees.get("demarree")
        self.prochain = donnees.get("prochain", 0)
        self.vide = donnees.get("vide", False)
        self.arme_depuis = donnees.get("arme_depuis")
        self.actif = donnees.get("actif", False)
        self.sauvegardes = donnees.get("sauvegardes", [])

        for entity_id, fin in list(self.allumees.items()):
            self._programmer_extinction(entity_id, fin)

        self._desabonnements.append(
            async_track_time_interval(self.hass, self._sur_intervalle, INTERVALLE)
        )
        a_suivre = self._entites_suivies()
        if a_suivre:
            self._desabonnements.append(
                async_track_state_change_event(self.hass, a_suivre, self._sur_changement)
            )

        if self.hass.state is CoreState.running:
            self.hass.async_create_task(self.async_evaluer())
        else:
            self._desabonnements.append(
                self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._sur_demarrage_ha)
            )

    async def async_arreter(self) -> None:
        """Débranche les écoutes (déchargement ou redémarrage) sans toucher aux lampes."""
        for desabonner in self._desabonnements:
            desabonner()
        self._desabonnements.clear()
        for annuler in self._minuteries.values():
            annuler()
        self._minuteries.clear()
        await self._sauver_maintenant()

    async def async_supprimer(self) -> None:
        """Suppression de l'intégration : éteint les lampes du simulateur et efface l'état."""
        for entity_id in list(self.allumees):
            await self._appeler("light", "turn_off", {"entity_id": entity_id})
        self.allumees.clear()
        await self.store.async_remove()

    def _entites_suivies(self) -> list[str]:
        r = self.reglages
        ids = [r.get("alarme"), r["soir"].get("lux_capteur"), r["matin"].get("lux_capteur")]
        ids += [l.get("capteur") for l in r["lampes"]]
        ids += list(r.get("personnes") or [])
        return sorted({i for i in ids if i})

    @callback
    def _sur_demarrage_ha(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_evaluer())

    async def _sur_intervalle(self, _now: datetime) -> None:
        await self.async_evaluer()

    @callback
    def _sur_changement(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_evaluer())

    # --------------------------------------------------------------- évaluation

    async def async_evaluer(self) -> None:
        """Recalcule l'état et agit si besoin."""
        async with self.verrou:
            maintenant = dt_util.now()
            self._maj_vide(maintenant)
            self._maj_lux(maintenant)
            self.plage, self.fin_seance, self.type_seance = self._seance(maintenant)
            actif = self.plage and (
                self.mode == MODE_FORCE or (self.mode == MODE_AUTO and self.vide)
            )
            if actif and not self.actif:
                self.demarree = maintenant.timestamp()
                self.prochain = maintenant.timestamp() + 60
                self._noter("Simulation démarrée")
            elif not actif and self.actif:
                await self._arreter_simulation()
            self.actif = actif

            ts = maintenant.timestamp()
            self.echecs = {e: t for e, t in self.echecs.items() if t > ts}

            if actif:
                await self._eteindre_pieces_eclairees()
                if ts >= self.prochain and self.fin_seance is not None:
                    await self._tentative(maintenant)
            self._sauver()
        self._signaler()

    def _alarme_absente(self) -> bool | None:
        """L'alarme est-elle armée en absence ? None si elle ne répond pas."""
        r = self.reglages
        alarme = r.get("alarme")
        etat = self.hass.states.get(alarme) if alarme else None
        if etat is None or etat.state in INDISPONIBLE:
            return None
        return etat.state in (r.get("etats_absence") or [])

    def _personnes_absentes(self) -> bool | None:
        """Toutes les personnes choisies sont-elles absentes ? None si l'une ne répond pas."""
        personnes = self.reglages.get("personnes") or []
        if not personnes:
            return None
        etats = [self.hass.states.get(p) for p in personnes]
        if any(e is None or e.state in INDISPONIBLE for e in etats):
            return None
        return all(e.state != "home" for e in etats)

    def _maj_vide(self, maintenant: datetime) -> None:
        r = self.reglages
        declencheur = r.get("declencheur", DECL_ALARME)
        alarme = self._alarme_absente() if declencheur in (DECL_ALARME, DECL_LES_DEUX) else None
        personnes = self._personnes_absentes() if declencheur in (DECL_PERSONNES, DECL_LES_DEUX) else None
        if declencheur == DECL_LES_DEUX:
            if alarme is None and personnes is None:
                return
            absent = bool(alarme) or bool(personnes)
        else:
            absent = alarme if declencheur == DECL_ALARME else personnes
            if absent is None:
                return  # la source ne répond pas : on garde l'état précédent
        if absent:
            if self.arme_depuis is None:
                self.arme_depuis = maintenant.timestamp()
            delai = int(r.get("delai_vide", 5) or 0) * 60
            self.vide = maintenant.timestamp() - self.arme_depuis >= delai
        else:
            self.arme_depuis = None
            self.vide = False

    def condition_auto(self) -> str:
        """Ce qui déclenche le mode Auto, en clair."""
        return {
            DECL_ALARME: "si alarme armée",
            DECL_PERSONNES: "si tout le monde est absent",
            DECL_LES_DEUX: "si alarme armée ou tout le monde absent",
        }.get(self.reglages.get("declencheur", DECL_ALARME), "si alarme armée")

    def _valeur_lux(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        etat = self.hass.states.get(entity_id)
        if etat is None or etat.state in INDISPONIBLE:
            return None
        try:
            return float(etat.state)
        except ValueError:
            return None

    def _maj_lux(self, maintenant: datetime) -> None:
        r = self.reglages
        tz = dt_util.get_default_time_zone()
        aujourdhui = maintenant.date()
        cle = aujourdhui.isoformat()

        soir = r["soir"]
        if soir.get("debut_mode") == BORNE_LUX:
            v = self._valeur_lux(soir.get("lux_capteur"))
            pas_avant = logic.a_heure(aujourdhui, soir.get("lux_pas_avant"), tz, "16:00")
            fin = self._fin_soir(aujourdhui)
            if v is None or cle in self.lux_soir or not (pas_avant <= maintenant < fin):
                self.lux_sous_depuis = None if v is None or cle in self.lux_soir else self.lux_sous_depuis
            elif v < float(soir.get("lux_seuil", 30)):
                if self.lux_sous_depuis is None:
                    self.lux_sous_depuis = maintenant.timestamp()
                elif maintenant.timestamp() - self.lux_sous_depuis >= int(soir.get("lux_duree", 5)) * 60:
                    self.lux_soir[cle] = maintenant.timestamp()
                    self.lux_sous_depuis = None
            else:
                self.lux_sous_depuis = None

        matin = r["matin"]
        if matin.get("actif") and matin.get("fin_mode") == BORNE_LUX and cle not in self.lux_matin:
            v = self._valeur_lux(matin.get("lux_capteur"))
            debut = logic.debut_matin(matin, aujourdhui, tz)
            if v is not None and maintenant >= debut and v > float(matin.get("lux_seuil", 30)):
                self.lux_matin[cle] = maintenant.timestamp()

        limite = (aujourdhui - timedelta(days=3)).isoformat()
        for registre in (self.lux_soir, self.lux_matin, self.fins):
            for jour in [j for j in registre if j < limite]:
                del registre[jour]

    # ----------------------------------------------------------------- séances

    def soleil(self, evenement: str, jour: date) -> datetime | None:
        """Heure locale exacte du lever ou du coucher pour un jour donné."""
        moment = get_astral_event_date(self.hass, evenement, jour)
        return dt_util.as_local(moment) if moment else None

    def _fin_soir(self, jour: date) -> datetime:
        cle = jour.isoformat()
        if cle not in self.fins:
            soir = self.reglages["soir"]
            fin = logic.tirer_fin_soir(
                jour, soir.get("fin", "23:30"), soir.get("variation", 0),
                dt_util.get_default_time_zone(), self.rng,
            )
            self.fins[cle] = fin.timestamp()
        return dt_util.as_local(dt_util.utc_from_timestamp(self.fins[cle]))

    def debut_soir(self, jour: date) -> tuple[datetime | None, str]:
        """Début de la soirée d'un jour (None si pas encore connu en mode luminosité)."""
        soir = self.reglages["soir"]
        latch = self.lux_soir.get(jour.isoformat())
        dispo = self._valeur_lux(soir.get("lux_capteur")) is not None
        return logic.debut_soir(
            soir, jour, dt_util.get_default_time_zone(),
            self.soleil(SUN_EVENT_SUNSET, jour),
            dt_util.as_local(dt_util.utc_from_timestamp(latch)) if latch else None,
            dispo,
        )

    def fin_matin(self, jour: date) -> tuple[datetime | None, str]:
        """Fin de la plage du matin d'un jour."""
        matin = self.reglages["matin"]
        latch = self.lux_matin.get(jour.isoformat())
        dispo = self._valeur_lux(matin.get("lux_capteur")) is not None
        return logic.fin_matin(
            matin, jour, dt_util.get_default_time_zone(),
            self.soleil(SUN_EVENT_SUNRISE, jour),
            dt_util.as_local(dt_util.utc_from_timestamp(latch)) if latch else None,
            dispo,
        )

    def _seance(self, maintenant: datetime) -> tuple[bool, datetime | None, str | None]:
        r = self.reglages
        aujourdhui = maintenant.date()
        for jour in (aujourdhui, aujourdhui - timedelta(days=1)):
            if not logic.jour_coche(r["soir"].get("jours"), jour):
                continue
            debut, _ = self.debut_soir(jour)
            fin = self._fin_soir(jour)
            if debut is not None and debut <= maintenant < fin:
                return True, fin, "soir"
        matin = r["matin"]
        if matin.get("actif") and logic.jour_coche(matin.get("jours"), aujourdhui):
            debut = logic.debut_matin(matin, aujourdhui, dt_util.get_default_time_zone())
            fin, _ = self.fin_matin(aujourdhui)
            if fin is not None and debut <= maintenant < fin:
                return True, fin, "matin"
        return False, None, None

    # ---------------------------------------------------------------- lampes

    async def _tentative(self, maintenant: datetime) -> None:
        r = self.reglages
        ry = r["rythme"]
        self.prochain = maintenant.timestamp() + logic.tirer_pause(ry["pause_min"], ry["pause_max"], self.rng) * 60
        if len(self.allumees) >= int(ry.get("simultanees", 1)):
            return
        candidats = {
            l["id"]: l for l in r["lampes"]
            if l.get("utilisee") and int(l.get("poids", 0)) > 0
            and l["entity_id"] not in self.allumees
            and l["entity_id"] not in self.echecs
            and (etat := self.hass.states.get(l["entity_id"])) is not None
            and etat.state == "off"
        }
        while candidats:
            choix = logic.tirage_pondere([(i, int(l["poids"])) for i, l in candidats.items()], self.rng)
            if choix is None:
                return
            lampe = candidats.pop(choix)
            lux = self._valeur_lux(lampe.get("capteur"))
            eclairee = lux is not None and lux >= float(lampe.get("seuil", 50))
            if eclairee:
                texte = f"{lampe['nom']} : pièce déjà éclairée ({lux:.0f} lx ≥ {float(lampe.get('seuil', 50)):.0f} lx)"
                if lampe.get("si_eclairee", SI_ECLAIREE_AUTRE) == SI_ECLAIREE_AUTRE:
                    self._noter(texte + ", autre lampe tirée")
                    continue
                if lampe.get("si_eclairee") == SI_ECLAIREE_ACTION:
                    await self._lancer_action(lampe.get("action_eclairee"))
                    self._noter(texte + ", action lancée à la place")
                    return
            duree = logic.tirer_duree(int(lampe["poids"]), ry["allumage_min"], ry["allumage_max"], self.rng)
            duree = logic.plafonner(duree, self.fin_seance, maintenant, self.rng)
            if duree < 5:
                return
            await self._allumer(lampe, duree)
            return

    async def _allumer(self, lampe: dict, duree: int) -> None:
        ry = self.reglages["rythme"]
        entity_id = lampe["entity_id"]
        await self._appeler("light", "turn_on", {"entity_id": entity_id})
        attente = int(ry.get("confirmation_s", 15))
        for _ in range(attente * 2):
            etat = self.hass.states.get(entity_id)
            if etat is not None and etat.state == "on":
                break
            await asyncio.sleep(0.5)
        else:
            ecart = int(ry.get("ecart_min", 30))
            self.echecs[entity_id] = dt_util.now().timestamp() + ecart * 60
            self.prochain = dt_util.now().timestamp() + 60
            self._noter(f"{lampe['nom']} : pas de réponse, lampe écartée {ecart} min")
            return
        fin = dt_util.now().timestamp() + duree * 60
        self.allumees[entity_id] = fin
        self._programmer_extinction(entity_id, fin)
        await self._lancer_action(lampe.get("action_allumage"))
        self._noter(f"{lampe['nom']} : allumée pour {duree} min")

    async def _eteindre(self, entity_id: str, noter: bool = True) -> None:
        self.allumees.pop(entity_id, None)
        if annuler := self._minuteries.pop(entity_id, None):
            annuler()
        lampe = self.lampe_par_entite(entity_id)
        await self._appeler("light", "turn_off", {"entity_id": entity_id})
        if lampe:
            await self._lancer_action(lampe.get("action_extinction"))
        if noter:
            self._noter(f"{lampe['nom'] if lampe else entity_id} : éteinte")

    async def _eteindre_pieces_eclairees(self) -> None:
        for entity_id in list(self.allumees):
            lampe = self.lampe_par_entite(entity_id)
            if not lampe or not lampe.get("eteindre_si_eclairee"):
                continue
            lux = self._valeur_lux(lampe.get("capteur"))
            if lux is not None and lux >= float(lampe.get("seuil", 50)):
                await self._eteindre(entity_id, noter=False)
                self._noter(f"{lampe['nom']} : éteinte plus tôt, pièce éclairée ({lux:.0f} lx)")

    def _programmer_extinction(self, entity_id: str, fin: float) -> None:
        if annuler := self._minuteries.pop(entity_id, None):
            annuler()

        @callback
        def _echeance(_now: datetime) -> None:
            self._minuteries.pop(entity_id, None)
            self.hass.async_create_task(self._fin_lampe(entity_id))

        self._minuteries[entity_id] = async_track_point_in_utc_time(
            self.hass, _echeance, dt_util.utc_from_timestamp(fin)
        )

    async def _fin_lampe(self, entity_id: str) -> None:
        async with self.verrou:
            if entity_id in self.allumees:
                await self._eteindre(entity_id)
                self._sauver()
        self._signaler()

    async def _arreter_simulation(self) -> None:
        retour = self.mode == MODE_AUTO and not self.vide
        nuit = (etat := self.hass.states.get("sun.sun")) is not None and etat.state == "below_horizon"
        gardees = []
        for entity_id in list(self.allumees):
            lampe = self.lampe_par_entite(entity_id)
            if retour and nuit and lampe and lampe.get("garder_retour"):
                self.allumees.pop(entity_id, None)
                if annuler := self._minuteries.pop(entity_id, None):
                    annuler()
                gardees.append(lampe["nom"])
            else:
                await self._eteindre(entity_id, noter=False)
        if retour:
            texte = "Retour : lumières du simulateur éteintes"
            if gardees:
                texte += " sauf " + ", ".join(gardees)
        else:
            texte = "Simulation arrêtée"
        self._noter(texte)

    async def _lancer_action(self, entity_id: str | None) -> None:
        if not entity_id:
            return
        domaine = entity_id.split(".", 1)[0]
        service = "trigger" if domaine == "automation" else "turn_on"
        await self._appeler(domaine, service, {"entity_id": entity_id})

    async def _appeler(self, domaine: str, service: str, donnees: dict) -> None:
        try:
            await self.hass.services.async_call(domaine, service, donnees, blocking=True)
        except Exception as err:  # noqa: BLE001 — une lampe en panne ne doit pas bloquer le moteur
            _LOGGER.warning("Lights Simulator : %s.%s %s a échoué : %s", domaine, service, donnees, err)

    # ------------------------------------------------------------ mode, journal

    async def async_changer_mode(self, mode: str) -> None:
        """Change le mode (Arrêt, Auto, Forcé)."""
        self.mode = mode
        await self.async_evaluer()

    async def async_tester_lampe(self, lampe_id: str) -> None:
        """Allume une lampe 2 minutes pour vérifier qu'elle répond (bouton Tester du panneau)."""
        lampe = self.lampe(lampe_id)
        if not lampe:
            return
        async with self.verrou:
            await self._allumer(lampe, 2)
            self._sauver()
        self._signaler()

    def _noter(self, texte: str) -> None:
        self.journal.insert(0, {"t": dt_util.now().isoformat(), "texte": texte})
        del self.journal[JOURNAL_MAX:]

    # ------------------------------------------------------------- sauvegardes

    def exporter(self) -> dict:
        """Configuration complète, prête à être téléchargée."""
        return {
            "format": FORMAT_SAUVEGARDE,
            "integration": DOMAIN,
            "version": VERSION,
            "date": dt_util.now().isoformat(),
            "reglages": self.reglages,
        }

    async def async_creer_sauvegarde(self, nom: str | None = None) -> dict:
        """Garde une copie des réglages actuels dans Home Assistant."""
        maintenant = dt_util.now()
        sauvegarde = {
            "id": maintenant.strftime("%Y%m%d%H%M%S%f"),
            "nom": (nom or "").strip() or f"Sauvegarde du {maintenant.strftime('%d/%m/%Y %H:%M')}",
            "date": maintenant.isoformat(),
            "version": VERSION,
            "reglages": self.reglages,
        }
        self.sauvegardes.insert(0, sauvegarde)
        del self.sauvegardes[SAUVEGARDES_MAX:]
        await self._sauver_maintenant()
        self._signaler()
        return sauvegarde

    async def async_supprimer_sauvegarde(self, sauvegarde_id: str) -> None:
        """Supprime une sauvegarde."""
        self.sauvegardes = [s for s in self.sauvegardes if s["id"] != sauvegarde_id]
        await self._sauver_maintenant()
        self._signaler()

    async def async_restaurer(self, reglages: dict, origine: str) -> None:
        """Remplace la configuration (sauvegarde ou fichier importé), après une copie de sécurité."""
        await self.async_creer_sauvegarde(f"Avant {origine}")
        propres = fusion(reglages_par_defaut(), reglages)
        # Les entités des lampes qui disparaissent sont retirées.
        gardees = {l["id"] for l in propres.get("lampes", [])}
        registre = er.async_get(self.hass)
        prefixe = f"{self.entry.entry_id}_lampe_"
        for entree in er.async_entries_for_config_entry(registre, self.entry.entry_id):
            if entree.unique_id.startswith(prefixe):
                lampe_id = entree.unique_id[len(prefixe):].rsplit("_", 1)[0]
                if lampe_id not in gardees:
                    registre.async_remove(entree.entity_id)
        self._noter(f"Configuration restaurée ({origine})")
        await self.async_maj_reglages(propres, recharger=True)

    # ------------------------------------------------------------- persistance

    def _donnees(self) -> dict:
        return {
            "mode": self.mode,
            "allumees": self.allumees,
            "echecs": self.echecs,
            "fins": self.fins,
            "lux_soir": self.lux_soir,
            "lux_matin": self.lux_matin,
            "lux_sous_depuis": self.lux_sous_depuis,
            "journal": self.journal,
            "demarree": self.demarree,
            "prochain": self.prochain,
            "vide": self.vide,
            "arme_depuis": self.arme_depuis,
            "actif": self.actif,
            "sauvegardes": self.sauvegardes,
        }

    def _sauver(self) -> None:
        self.store.async_delay_save(self._donnees, 5)

    async def _sauver_maintenant(self) -> None:
        await self.store.async_save(self._donnees())

    def _signaler(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_MAJ.format(self.entry.entry_id))

    # ------------------------------------------------------------ affichage

    def texte_etat(self) -> str:
        """État lisible."""
        if self.mode == MODE_ARRET:
            return "Arrêté"
        if self.actif:
            return "En cours"
        if self.mode == MODE_AUTO and self.plage and not self.vide:
            return "En veille (maison occupée)"
        return "En attente de la plage"

    def texte_demarrage(self) -> str:
        """Heure de démarrage réelle ou prévue."""
        if self.mode == MODE_ARRET:
            return "Simulateur arrêté"
        if self.actif and self.demarree:
            return "Démarrée à " + dt_util.as_local(dt_util.utc_from_timestamp(self.demarree)).strftime("%H:%M")
        if self.plage:
            return "Dès que la maison sera vide"
        prochain = self.prochain_demarrage()
        if prochain is None:
            return "Pas de démarrage prévu"
        moment, matin, texte_lux = prochain
        suffixe = " " + self.condition_auto() if self.mode == MODE_AUTO else ""
        aujourdhui = dt_util.now().date()
        ecart = (moment.date() - aujourdhui).days
        jour = "" if ecart == 0 else ("demain " if ecart == 1 else JOURS_LONGS[moment.weekday()] + " ")
        if texte_lux:
            return f"Prévu {jour}{texte_lux}{suffixe}".replace("  ", " ")
        return f"Prévu {jour}à {moment.strftime('%H:%M')}{' (matin)' if matin else ''}{suffixe}"

    def prochain_demarrage(self) -> tuple[datetime, bool, str | None] | None:
        """Prochain début de séance : (moment, est_le_matin, texte si dépend de la luminosité)."""
        r = self.reglages
        maintenant = dt_util.now()
        tz = dt_util.get_default_time_zone()
        candidats: list[tuple[datetime, bool, str | None]] = []
        for d in range(8):
            jour = maintenant.date() + timedelta(days=d)
            if logic.jour_coche(r["soir"].get("jours"), jour):
                fin = self._fin_soir(jour) if d < 2 else logic.a_heure(jour, r["soir"].get("fin"), tz)
                debut, origine = self.debut_soir(jour)
                if debut is None and origine == BORNE_LUX:
                    pas_avant = logic.a_heure(jour, r["soir"].get("lux_pas_avant"), tz, "16:00")
                    if maintenant < fin:
                        seuil = r["soir"].get("lux_seuil", 30)
                        candidats.append((max(pas_avant, maintenant), False,
                                          f"dès que la luminosité passe sous {seuil} lx (pas avant {pas_avant.strftime('%H:%M')})"))
                        break
                elif debut is not None and debut < fin and maintenant < fin:
                    candidats.append((max(debut, maintenant), False, None))
                    break
        matin = r["matin"]
        if matin.get("actif"):
            for d in range(8):
                jour = maintenant.date() + timedelta(days=d)
                if not logic.jour_coche(matin.get("jours"), jour):
                    continue
                debut = logic.debut_matin(matin, jour, tz)
                fin, _ = self.fin_matin(jour)
                if fin is not None and max(debut, maintenant) < fin:
                    candidats.append((max(debut, maintenant), True, None))
                    break
        return min(candidats, key=lambda c: c[0]) if candidats else None

    def lampes_allumees(self) -> list[dict]:
        """Lampes allumées par le simulateur, avec le temps restant."""
        maintenant = dt_util.now().timestamp()
        res = []
        for entity_id, fin in sorted(self.allumees.items(), key=lambda x: x[1]):
            lampe = self.lampe_par_entite(entity_id)
            res.append({
                "entity_id": entity_id,
                "nom": lampe["nom"] if lampe else entity_id,
                "reste": max(0, int((fin - maintenant + 59) // 60)),
                "fin": dt_util.utc_from_timestamp(fin).isoformat(),
            })
        return res

    def texte_lampes(self) -> str:
        """« Salon · 20 min, Séjour · 41 min » ou « Aucune »."""
        lampes = self.lampes_allumees()
        return ", ".join(f"{l['nom']} · {l['reste']} min" for l in lampes) if lampes else "Aucune"

    def texte_soleil(self, evenement: str) -> str:
        """Heure du lever ou du coucher du jour, et celle du lendemain une fois passée."""
        maintenant = dt_util.now()
        aujourdhui = self.soleil(evenement, maintenant.date())
        demain = self.soleil(evenement, maintenant.date() + timedelta(days=1))
        if aujourdhui is None:
            return "—"
        texte = aujourdhui.strftime("%H:%M")
        if maintenant >= aujourdhui and demain is not None:
            texte += " · demain " + demain.strftime("%H:%M")
        return texte

    def instantane(self) -> dict:
        """Tout ce que le panneau et la carte affichent."""
        maintenant = dt_util.now()
        fin_soir = self._fin_soir_affichee(maintenant)
        return {
            "version": VERSION,
            "mode": self.mode,
            "actif": self.actif,
            "plage": self.plage,
            "vide": self.vide,
            "etat": self.texte_etat(),
            "demarrage": self.texte_demarrage(),
            "fin_ce_soir": fin_soir.strftime("%H:%M") if fin_soir else None,
            "prochain": dt_util.as_local(dt_util.utc_from_timestamp(self.prochain)).strftime("%H:%M")
            if self.actif and self.prochain else None,
            "lever": self.texte_soleil(SUN_EVENT_SUNRISE),
            "coucher": self.texte_soleil(SUN_EVENT_SUNSET),
            "lampes_allumees": self.lampes_allumees(),
            "journal": self.journal,
            "echecs": {e: dt_util.utc_from_timestamp(t).isoformat() for e, t in self.echecs.items()},
        }

    def _fin_soir_affichee(self, maintenant: datetime) -> datetime | None:
        if self.type_seance == "soir" and self.fin_seance:
            return self.fin_seance
        aujourdhui = maintenant.date()
        fin = self._fin_soir(aujourdhui)
        return fin if fin > maintenant else self._fin_soir(aujourdhui + timedelta(days=1))
