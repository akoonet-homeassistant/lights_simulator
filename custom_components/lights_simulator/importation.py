"""Reprise des réglages d'un simulateur fait d'entrées (helpers) « Simulateur présence »."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import BORNE_FIXE, BORNE_SOLEIL, JOURS, MODE_ARRET, MODE_AUTO, MODE_FORCE, lampe_par_defaut

PREFIXE = "simulateur_presence"


def anciens_reglages_presents(hass: HomeAssistant) -> bool:
    """Les entrées d'un simulateur « fait main » existent-elles ?"""
    return hass.states.get(f"input_select.{PREFIXE}_mode") is not None


def _etat(hass: HomeAssistant, entity_id: str) -> str | None:
    etat = hass.states.get(entity_id)
    return None if etat is None or etat.state in ("unknown", "unavailable") else etat.state


def _nombre(hass: HomeAssistant, entity_id: str, defaut: int) -> int:
    try:
        return int(float(_etat(hass, entity_id) or defaut))
    except ValueError:
        return defaut


def _heure(hass: HomeAssistant, entity_id: str, defaut: str) -> str:
    valeur = _etat(hass, entity_id)
    return valeur[:5] if valeur and len(valeur) >= 5 else defaut


def _jours(hass: HomeAssistant, prefixe: str, defaut: list[int]) -> list[int]:
    etats = [_etat(hass, f"input_boolean.{PREFIXE}_{prefixe}_{j}") for j in JOURS]
    if all(e is None for e in etats):
        return defaut
    return [i for i, e in enumerate(etats) if e == "on"]


def mode_ancien(hass: HomeAssistant) -> str:
    """Mode de l'ancien simulateur."""
    valeur = _etat(hass, f"input_select.{PREFIXE}_mode") or ""
    if valeur.startswith("Arr"):
        return MODE_ARRET
    if valeur.startswith("Forc"):
        return MODE_FORCE
    return MODE_AUTO


def importer(hass: HomeAssistant, reglages: dict) -> dict:
    """Complète des réglages avec ceux de l'ancien simulateur (plages, jours, rythme, lampes)."""
    p = PREFIXE
    soir = reglages["soir"]
    nuit = _etat(hass, f"input_boolean.{p}_attendre_nuit") != "off"
    soir["debut_mode"] = BORNE_SOLEIL if nuit else BORNE_FIXE
    soir["decalage_coucher"] = _nombre(hass, f"input_number.{p}_decalage_coucher", soir["decalage_coucher"])
    soir["heure_debut"] = _heure(hass, f"input_datetime.{p}_debut", soir["heure_debut"])
    soir["fin"] = _heure(hass, f"input_datetime.{p}_fin", soir["fin"])
    soir["variation"] = _nombre(hass, f"input_number.{p}_variation_fin", soir["variation"])
    soir["jours"] = _jours(hass, "soir", soir["jours"])

    matin = reglages["matin"]
    matin["actif"] = _etat(hass, f"input_boolean.{p}_matin") == "on"
    matin["debut"] = _heure(hass, f"input_datetime.{p}_matin_debut", matin["debut"])
    matin["fin_mode"] = BORNE_FIXE if _etat(hass, f"input_select.{p}_matin_fin_mode") == "Heure fixe" else BORNE_SOLEIL
    matin["decalage_lever"] = _nombre(hass, f"input_number.{p}_decalage_lever", matin["decalage_lever"])
    matin["heure_fin"] = _heure(hass, f"input_datetime.{p}_matin_fin", matin["heure_fin"])
    matin["jours"] = _jours(hass, "matin", matin["jours"])

    rythme = reglages["rythme"]
    for cle, entite in (
        ("allumage_min", "allumage_min"), ("allumage_max", "allumage_max"),
        ("pause_min", "pause_min"), ("pause_max", "pause_max"), ("simultanees", "simultanees"),
    ):
        rythme[cle] = _nombre(hass, f"input_number.{p}_{entite}", rythme[cle])

    # Lampes : chaque poids « sim_presence_poids_<x> » va à la lampe dont l'entité contient <x>.
    suffixes = [
        e.entity_id.removeprefix("input_number.sim_presence_poids_")
        for e in hass.states.async_all("input_number")
        if e.entity_id.startswith("input_number.sim_presence_poids_")
    ]
    for lampe in reglages["lampes"]:
        objet = lampe["entity_id"].split(".", 1)[1]
        suffixe = next((s for s in sorted(suffixes, key=len, reverse=True) if s in objet), None)
        if not suffixe:
            continue
        lampe["poids"] = _nombre(hass, f"input_number.sim_presence_poids_{suffixe}", lampe["poids"])
        coche = hass.states.get(f"input_boolean.sim_presence_{suffixe}")
        if coche is not None:
            lampe["utilisee"] = coche.state == "on"
            nom = str(coche.attributes.get("friendly_name", "")).removeprefix("Sim présence").strip()
            if nom:
                lampe["nom"] = nom[0].upper() + nom[1:]
    return reglages


def lampes_depuis_entites(hass: HomeAssistant, entites: list[str]) -> list[dict]:
    """Crée la liste des lampes à partir des entités lumière choisies."""
    lampes, ids = [], set()
    for entity_id in entites:
        etat = hass.states.get(entity_id)
        nom = str(etat.attributes.get("friendly_name")) if etat else entity_id.split(".", 1)[1]
        base = slugify(nom) or slugify(entity_id.split(".", 1)[1])
        lampe_id, n = base, 2
        while lampe_id in ids:
            lampe_id, n = f"{base}_{n}", n + 1
        ids.add(lampe_id)
        lampes.append(lampe_par_defaut(lampe_id, entity_id, nom))
    return lampes
