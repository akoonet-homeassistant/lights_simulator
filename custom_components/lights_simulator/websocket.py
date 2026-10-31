"""Commandes websocket utilisées par le panneau et la carte."""

from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import BORNES, DECLENCHEURS, DOMAIN, MODES, SI_ECLAIREE, lampe_par_defaut, reglages_par_defaut
from .engine import Moteur

SECTIONS_SIMPLES = {"soir", "matin", "rythme"}
CLES_GENERALES = {"declencheur", "alarme", "etats_absence", "personnes", "delai_vide", "barre_laterale"}
CLES_LAMPE_RECHARGE = ("entity_id", "nom", "capteur")
EFFACABLES = {"alarme", "lux_capteur"}  # réglages qu'on peut vider (None)
MINIMUMS = {
    "simultanees": 1, "allumage_min": 1, "allumage_max": 1, "pause_min": 1, "pause_max": 1,
    "confirmation_s": 1, "ecart_min": 0, "delai_vide": 0, "lux_duree": 0, "variation": 0,
    "lux_seuil": 0,
}


def _valeurs_propres(section: str, valeurs: dict) -> dict:
    """Vérifie et convertit les valeurs envoyées par le panneau, d'après les réglages par défaut.

    Un champ numérique ou horaire vidé (None) est ignoré : l'ancienne valeur est gardée.
    """
    defauts = reglages_par_defaut()
    modele = {k: defauts[k] for k in CLES_GENERALES} if section == "general" else defauts[section]
    propres: dict = {}
    for cle, val in valeurs.items():
        if cle not in modele:
            raise vol.Invalid(f"Réglage inconnu : {cle}")
        defaut = modele[cle]
        if val is None:
            if cle in EFFACABLES:
                propres[cle] = None
            continue
        if cle == "declencheur" and val not in DECLENCHEURS:
            raise vol.Invalid("Déclencheur invalide")
        if cle in ("debut_mode", "fin_mode") and val not in BORNES:
            raise vol.Invalid(f"{cle} invalide")
        if isinstance(defaut, bool):
            propres[cle] = bool(val)
        elif isinstance(defaut, int):
            propres[cle] = max(MINIMUMS.get(cle, -10_000), int(vol.Coerce(float)(val)))
        elif isinstance(defaut, float):
            propres[cle] = vol.Coerce(float)(val)
        elif isinstance(defaut, list):
            if not isinstance(val, list):
                raise vol.Invalid(f"{cle} doit être une liste")
            propres[cle] = sorted({int(v) for v in val if 0 <= int(v) <= 6}) if cle == "jours" else [str(v) for v in val]
        else:
            propres[cle] = str(val)
    return propres


def _moteur(hass: HomeAssistant) -> Moteur | None:
    moteurs = hass.data.get(DOMAIN) or {}
    return next(iter(moteurs.values()), None)


def _sans_moteur(connection, msg) -> None:
    connection.send_error(msg["id"], "non_configure", "Lights Simulator n'est pas configuré")


def _resume_sauvegardes(moteur: Moteur) -> list[dict]:
    return [
        {"id": s["id"], "nom": s["nom"], "date": s["date"], "version": s.get("version"),
         "lampes": len(s["reglages"].get("lampes", []))}
        for s in moteur.sauvegardes
    ]


def _etat_complet(hass: HomeAssistant, moteur: Moteur) -> dict:
    registre = er.async_get(hass)
    entites = []
    for entree in er.async_entries_for_config_entry(registre, moteur.entry.entry_id):
        etat = hass.states.get(entree.entity_id)
        entites.append({
            "entity_id": entree.entity_id,
            "nom": entree.name or entree.original_name,
            "etat": etat.state if etat else None,
        })
    return {
        "reglages": moteur.reglages,
        "instantane": moteur.instantane(),
        "sauvegardes": _resume_sauvegardes(moteur),
        "entites": sorted(entites, key=lambda e: e["entity_id"]),
    }


@callback
def async_enregistrer(hass: HomeAssistant) -> None:
    """Enregistre les commandes (une fois par démarrage)."""
    for commande in (
        ws_etat, ws_mode, ws_reglages, ws_lampe_enregistrer, ws_lampe_supprimer, ws_lampe_tester,
        ws_sauvegarde_creer, ws_sauvegarde_supprimer, ws_sauvegarde_restaurer, ws_exporter, ws_importer,
    ):
        websocket_api.async_register_command(hass, commande)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/etat"})
@callback
def ws_etat(hass: HomeAssistant, connection, msg: dict) -> None:
    """Réglages, état courant, sauvegardes et entités."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    connection.send_result(msg["id"], _etat_complet(hass, moteur))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/mode", vol.Required("mode"): vol.In(MODES)})
@websocket_api.async_response
async def ws_mode(hass: HomeAssistant, connection, msg: dict) -> None:
    """Change le mode (accessible à tous les utilisateurs, comme le sélecteur)."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    await moteur.async_changer_mode(msg["mode"])
    connection.send_result(msg["id"], _etat_complet(hass, moteur))


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/reglages",
    vol.Required("section"): vol.In(sorted(SECTIONS_SIMPLES | {"general"})),
    vol.Required("valeurs"): dict,
})
@websocket_api.async_response
async def ws_reglages(hass: HomeAssistant, connection, msg: dict) -> None:
    """Modifie une partie des réglages (général, soir, matin, rythme)."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    reglages = moteur.reglages
    try:
        valeurs = _valeurs_propres(msg["section"], msg["valeurs"])
    except (vol.Invalid, ValueError, TypeError) as err:
        connection.send_error(msg["id"], "invalide", str(err))
        return
    if msg["section"] == "general":
        reglages.update(valeurs)
    else:
        reglages[msg["section"]].update(valeurs)
    await moteur.async_maj_reglages(reglages)
    connection.send_result(msg["id"], _etat_complet(hass, moteur))


SCHEMA_LAMPE = vol.Schema({
    vol.Optional("id"): str,
    vol.Required("entity_id"): str,
    vol.Required("nom"): str,
    vol.Optional("utilisee", default=True): bool,
    vol.Optional("poids", default=3): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
    vol.Optional("capteur"): vol.Any(None, str),
    vol.Optional("seuil", default=50): vol.Coerce(float),
    vol.Optional("si_eclairee", default="autre"): vol.In(SI_ECLAIREE),
    vol.Optional("action_eclairee"): vol.Any(None, str),
    vol.Optional("eteindre_si_eclairee", default=False): bool,
    vol.Optional("action_allumage"): vol.Any(None, str),
    vol.Optional("action_extinction"): vol.Any(None, str),
    vol.Optional("garder_retour", default=False): bool,
}, extra=vol.REMOVE_EXTRA)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/lampe_enregistrer", vol.Required("lampe"): dict})
@websocket_api.async_response
async def ws_lampe_enregistrer(hass: HomeAssistant, connection, msg: dict) -> None:
    """Ajoute ou modifie une lampe."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    try:
        lampe = SCHEMA_LAMPE({k: v for k, v in msg["lampe"].items() if v is not None or k in ("capteur", "action_eclairee", "action_allumage", "action_extinction")})
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalide", str(err))
        return
    if not lampe["entity_id"].startswith("light."):
        connection.send_error(msg["id"], "invalide", "L'entité doit être une lumière (light.*)")
        return
    reglages = moteur.reglages
    lampes = reglages["lampes"]
    existante = next((l for l in lampes if l["id"] == lampe.get("id")), None)
    if any(l["entity_id"] == lampe["entity_id"] and l is not existante for l in lampes):
        connection.send_error(msg["id"], "doublon", "Cette lumière est déjà dans la liste")
        return
    if existante is None:
        base = slugify(lampe["nom"]) or "lampe"
        ids, lampe_id, n = {l["id"] for l in lampes}, base, 2
        while lampe_id in ids:
            lampe_id, n = f"{base}_{n}", n + 1
        nouvelle = lampe_par_defaut(lampe_id, lampe["entity_id"], lampe["nom"])
        nouvelle.update({k: v for k, v in lampe.items() if k != "id"})
        lampes.append(nouvelle)
        recharger = True
    else:
        recharger = any(existante.get(k) != lampe.get(k) for k in CLES_LAMPE_RECHARGE)
        existante.update({k: v for k, v in lampe.items() if k != "id"})
    await moteur.async_maj_reglages(reglages, recharger=recharger)
    connection.send_result(msg["id"], {"recharge": recharger})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/lampe_supprimer", vol.Required("lampe_id"): str})
@websocket_api.async_response
async def ws_lampe_supprimer(hass: HomeAssistant, connection, msg: dict) -> None:
    """Retire une lampe (et ses entités)."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    reglages = moteur.reglages
    lampe_id = msg["lampe_id"]
    lampe = next((l for l in reglages["lampes"] if l["id"] == lampe_id), None)
    if lampe is None:
        connection.send_error(msg["id"], "introuvable", "Lampe introuvable")
        return
    reglages["lampes"] = [l for l in reglages["lampes"] if l["id"] != lampe_id]
    registre = er.async_get(hass)
    prefixe = f"{moteur.entry.entry_id}_lampe_"
    for entree in er.async_entries_for_config_entry(registre, moteur.entry.entry_id):
        if entree.unique_id.startswith(prefixe) and entree.unique_id[len(prefixe):].rsplit("_", 1)[0] == lampe_id:
            registre.async_remove(entree.entity_id)
    await moteur.async_maj_reglages(reglages, recharger=True)
    connection.send_result(msg["id"], {"recharge": True})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/lampe_tester", vol.Required("lampe_id"): str})
@websocket_api.async_response
async def ws_lampe_tester(hass: HomeAssistant, connection, msg: dict) -> None:
    """Allume la lampe 2 minutes pour vérifier qu'elle répond."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    await moteur.async_tester_lampe(msg["lampe_id"])
    connection.send_result(msg["id"], _etat_complet(hass, moteur))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/sauvegarde_creer", vol.Optional("nom"): str})
@websocket_api.async_response
async def ws_sauvegarde_creer(hass: HomeAssistant, connection, msg: dict) -> None:
    """Garde une copie de la configuration dans Home Assistant."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    await moteur.async_creer_sauvegarde(msg.get("nom"))
    connection.send_result(msg["id"], _etat_complet(hass, moteur))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/sauvegarde_supprimer", vol.Required("sauvegarde_id"): str})
@websocket_api.async_response
async def ws_sauvegarde_supprimer(hass: HomeAssistant, connection, msg: dict) -> None:
    """Supprime une sauvegarde."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    await moteur.async_supprimer_sauvegarde(msg["sauvegarde_id"])
    connection.send_result(msg["id"], _etat_complet(hass, moteur))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/sauvegarde_restaurer", vol.Required("sauvegarde_id"): str})
@websocket_api.async_response
async def ws_sauvegarde_restaurer(hass: HomeAssistant, connection, msg: dict) -> None:
    """Restaure une sauvegarde (une copie de la configuration actuelle est faite avant)."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    sauvegarde = next((s for s in moteur.sauvegardes if s["id"] == msg["sauvegarde_id"]), None)
    if sauvegarde is None:
        connection.send_error(msg["id"], "introuvable", "Sauvegarde introuvable")
        return
    await moteur.async_restaurer(copy.deepcopy(sauvegarde["reglages"]), f"restauration de « {sauvegarde['nom']} »")
    connection.send_result(msg["id"], {"recharge": True})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/exporter", vol.Optional("sauvegarde_id"): str})
@callback
def ws_exporter(hass: HomeAssistant, connection, msg: dict) -> None:
    """Configuration actuelle (ou d'une sauvegarde) au format fichier."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    donnees = moteur.exporter()
    if msg.get("sauvegarde_id"):
        sauvegarde = next((s for s in moteur.sauvegardes if s["id"] == msg["sauvegarde_id"]), None)
        if sauvegarde is None:
            connection.send_error(msg["id"], "introuvable", "Sauvegarde introuvable")
            return
        donnees.update(date=sauvegarde["date"], nom=sauvegarde["nom"], reglages=sauvegarde["reglages"])
    connection.send_result(msg["id"], donnees)


def valider_fichier(donnees: Any) -> dict:
    """Vérifie un fichier de configuration importé ; retourne ses réglages."""
    if not isinstance(donnees, dict) or donnees.get("integration") != DOMAIN:
        raise vol.Invalid("Ce fichier n'est pas une configuration Lights Simulator")
    reglages = donnees.get("reglages")
    if not isinstance(reglages, dict) or not isinstance(reglages.get("lampes", []), list):
        raise vol.Invalid("Fichier incomplet : réglages absents")
    ids = set()
    for lampe in reglages.get("lampes", []):
        if not isinstance(lampe, dict) or not str(lampe.get("entity_id", "")).startswith("light."):
            raise vol.Invalid("Fichier invalide : une lampe n'a pas d'entité lumière")
        if not lampe.get("id") or lampe["id"] in ids:
            raise vol.Invalid("Fichier invalide : identifiants de lampes manquants ou en double")
        ids.add(lampe["id"])
    return reglages


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/importer", vol.Required("donnees"): dict})
@websocket_api.async_response
async def ws_importer(hass: HomeAssistant, connection, msg: dict) -> None:
    """Remplace la configuration par celle d'un fichier (copie de sécurité faite avant)."""
    moteur = _moteur(hass)
    if moteur is None:
        _sans_moteur(connection, msg)
        return
    try:
        reglages = valider_fichier(msg["donnees"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalide", str(err))
        return
    await moteur.async_restaurer(reglages, "import d'un fichier")
    connection.send_result(msg["id"], {"recharge": True})
