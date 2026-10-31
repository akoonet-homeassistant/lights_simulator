"""Constantes de Lights Simulator."""

from __future__ import annotations

DOMAIN = "lights_simulator"
VERSION = "2026.11.1"
NOM_APPAREIL = "Lights Simulator"

PANEL_URL = "lights-simulator"
PANEL_TITLE = "Lights Simulator"
PANEL_ICON = "mdi:home-lightbulb"
PANEL_ELEMENT = "lights-simulator-panel"
CARD_ELEMENT = "lights-simulator-card"
STATIC_URL = "/lights_simulator_static"

SAUVEGARDES_MAX = 10
FORMAT_SAUVEGARDE = 1

SIGNAL_MAJ = f"{DOMAIN}_maj_{{}}"

PLATFORMS = ["binary_sensor", "number", "select", "sensor", "switch"]

MODE_ARRET = "arret"
MODE_AUTO = "auto"
MODE_FORCE = "force"
MODES = [MODE_ARRET, MODE_AUTO, MODE_FORCE]
MODE_LIBELLES = {MODE_ARRET: "Arrêt", MODE_AUTO: "Auto", MODE_FORCE: "Forcé"}

BORNE_SOLEIL = "soleil"
BORNE_FIXE = "fixe"
BORNE_LUX = "lux"
BORNES = [BORNE_SOLEIL, BORNE_FIXE, BORNE_LUX]

DECL_ALARME = "alarme"
DECL_PERSONNES = "personnes"
DECL_LES_DEUX = "les_deux"
DECLENCHEURS = [DECL_ALARME, DECL_PERSONNES, DECL_LES_DEUX]

SI_ECLAIREE_AUTRE = "autre"
SI_ECLAIREE_QUAND_MEME = "quand_meme"
SI_ECLAIREE_ACTION = "action"
SI_ECLAIREE = [SI_ECLAIREE_AUTRE, SI_ECLAIREE_QUAND_MEME, SI_ECLAIREE_ACTION]

JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
JOURS_LONGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

JOURNAL_MAX = 30


def reglages_par_defaut() -> dict:
    """Réglages d'une nouvelle installation."""
    return {
        "declencheur": DECL_ALARME,
        "alarme": None,
        "etats_absence": ["armed_away"],
        "personnes": [],
        "delai_vide": 5,
        "soir": {
            "debut_mode": BORNE_SOLEIL,
            "decalage_coucher": 7,
            "heure_debut": "17:30",
            "lux_capteur": None,
            "lux_seuil": 30,
            "lux_duree": 5,
            "lux_pas_avant": "16:00",
            "fin": "23:30",
            "variation": 30,
            "jours": [0, 1, 2, 3, 4, 5, 6],
        },
        "matin": {
            "actif": False,
            "debut": "06:45",
            "fin_mode": BORNE_SOLEIL,
            "decalage_lever": 0,
            "heure_fin": "07:45",
            "lux_capteur": None,
            "lux_seuil": 30,
            "lux_au_plus_tard": "08:30",
            "jours": [0, 1, 2, 3, 4],
        },
        "rythme": {
            "allumage_min": 10,
            "allumage_max": 60,
            "pause_min": 5,
            "pause_max": 20,
            "simultanees": 2,
            "confirmation_s": 15,
            "ecart_min": 30,
        },
        "lampes": [],
    }


def lampe_par_defaut(lampe_id: str, entity_id: str, nom: str) -> dict:
    """Réglages d'une nouvelle lampe."""
    return {
        "id": lampe_id,
        "entity_id": entity_id,
        "nom": nom,
        "utilisee": True,
        "poids": 3,
        "capteur": None,
        "seuil": 50,
        "si_eclairee": SI_ECLAIREE_AUTRE,
        "action_eclairee": None,
        "eteindre_si_eclairee": False,
        "action_allumage": None,
        "action_extinction": None,
        "garder_retour": False,
    }
