"""Calculs du simulateur, sans dépendance à Home Assistant (testables seuls)."""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, tzinfo

from .const import BORNE_FIXE, BORNE_LUX, BORNE_SOLEIL


def parse_heure(valeur: str | None, defaut: str = "00:00") -> time:
    """Convertit « HH:MM » ou « HH:MM:SS » en heure."""
    try:
        return time.fromisoformat((valeur or defaut)[:8])
    except ValueError:
        return time.fromisoformat(defaut)


def a_heure(jour: date, heure: str | None, tz: tzinfo, defaut: str = "00:00") -> datetime:
    """Date + heure locale."""
    return datetime.combine(jour, parse_heure(heure, defaut), tzinfo=tz)


def jour_coche(jours: list[int], jour: date) -> bool:
    """Le jour de la semaine est-il coché ?"""
    return jour.weekday() in (jours or [])


def jour_de_fin(fin: str | None) -> int:
    """0 si la fin du soir tombe le même jour, 1 si elle passe minuit (avant midi)."""
    return 1 if parse_heure(fin, "23:30") < time(12, 0) else 0


def tirer_fin_soir(jour: date, fin: str, variation: int, tz: tzinfo, rng: random.Random) -> datetime:
    """Heure de fin de la soirée du jour donné : fin moyenne ± variation, tirée au hasard."""
    base = a_heure(jour + timedelta(days=jour_de_fin(fin)), fin, tz, "23:30")
    v = max(0, int(variation or 0))
    return base + timedelta(minutes=rng.randint(-v, v))


def debut_soir(
    cfg: dict,
    jour: date,
    tz: tzinfo,
    coucher: datetime | None,
    lux_debut: datetime | None,
    lux_disponible: bool,
) -> tuple[datetime | None, str]:
    """Début de la soirée du jour.

    Retourne (heure, origine). En mode luminosité l'heure n'est connue qu'une fois
    le seuil franchi (None avant) ; si le capteur ne répond pas, repli sur le soleil.
    """
    mode = cfg.get("debut_mode", BORNE_SOLEIL)
    soleil = (
        coucher + timedelta(minutes=int(cfg.get("decalage_coucher", 0) or 0))
        if coucher is not None
        else None
    )
    if mode == BORNE_FIXE:
        return a_heure(jour, cfg.get("heure_debut"), tz, "17:30"), BORNE_FIXE
    if mode == BORNE_LUX:
        if lux_debut is not None:
            return lux_debut, BORNE_LUX  # déjà démarrée : une panne du capteur ne l'arrête pas
        if not lux_disponible:
            return soleil, BORNE_SOLEIL
        return None, BORNE_LUX
    return soleil, BORNE_SOLEIL


def fin_matin(
    cfg: dict,
    jour: date,
    tz: tzinfo,
    lever: datetime | None,
    lux_fin: datetime | None,
    lux_disponible: bool,
) -> tuple[datetime | None, str]:
    """Fin de la plage du matin du jour (retourne (heure, origine))."""
    mode = cfg.get("fin_mode", BORNE_SOLEIL)
    soleil = (
        lever + timedelta(minutes=int(cfg.get("decalage_lever", 0) or 0))
        if lever is not None
        else None
    )
    if mode == BORNE_FIXE:
        return a_heure(jour, cfg.get("heure_fin"), tz, "07:45"), BORNE_FIXE
    if mode == BORNE_LUX:
        limite = a_heure(jour, cfg.get("lux_au_plus_tard"), tz, "08:30")
        if lux_fin is not None:
            return min(lux_fin, limite), BORNE_LUX
        if not lux_disponible:
            return (min(soleil, limite) if soleil else limite), BORNE_SOLEIL
        return limite, BORNE_LUX
    return soleil, BORNE_SOLEIL


def debut_matin(cfg: dict, jour: date, tz: tzinfo) -> datetime:
    """Début de la plage du matin (toujours une heure fixe)."""
    return a_heure(jour, cfg.get("debut"), tz, "06:45")


def tirage_pondere(candidats: list[tuple[str, int]], rng: random.Random) -> str | None:
    """Tire un identifiant selon son poids (poids 0 = jamais)."""
    urne = [cid for cid, poids in candidats for _ in range(max(0, int(poids)))]
    return rng.choice(urne) if urne else None


def bornes_duree(poids: int, amin: int, amax: int) -> tuple[int, int]:
    """Bornes de durée selon le poids : moitié haute si ≥ 4, basse si ≤ 2, complète si 3."""
    bas, haut = sorted((int(amin), int(amax)))
    milieu = (bas + haut) // 2
    lo = milieu if poids >= 4 else bas
    hi = milieu if poids <= 2 else haut
    return lo, hi


def tirer_duree(poids: int, amin: int, amax: int, rng: random.Random) -> int:
    """Durée d'allumage en minutes."""
    lo, hi = bornes_duree(poids, amin, amax)
    return rng.randint(lo, hi)


def tirer_pause(pmin: int, pmax: int, rng: random.Random) -> int:
    """Pause en minutes avant la tentative suivante."""
    bas, haut = sorted((int(pmin), int(pmax)))
    return rng.randint(bas, haut)


def plafonner(duree: int, fin_seance: datetime, maintenant: datetime, rng: random.Random) -> int:
    """Plafonne la durée pour que la lampe s'éteigne 1 à 5 min avant la fin de la séance."""
    restant = int((fin_seance - maintenant).total_seconds() // 60)
    return min(duree, restant - rng.randint(1, 5))
