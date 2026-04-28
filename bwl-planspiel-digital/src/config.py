"""
config.py – Projektweite Konstanten und Konfiguration
"""

APP_NAME = "FACTORY 2.0"
APP_VERSION = "1.0.0"

# Spielparameter
MIN_TEAMS = 2
MAX_TEAMS = 6
MIN_JAHRE = 1
MAX_JAHRE = 5
DEFAULT_JAHRE = 3

# Farbpalette für Charts (je Team, bis zu 6)
TEAM_FARBEN = [
    "#1f77b4",  # blau
    "#ff7f0e",  # orange
    "#2ca02c",  # grün
    "#d62728",  # rot
    "#9467bd",  # violett
    "#8c564b",  # braun
]

# Investitionsoptionen (Anzeigetext → InvestitionsTyp-Wert)
INVESTITIONS_OPTIONEN = {
    "Keine": None,
    "Maschine auswählen": "maschine",
    "Automatisierung": "automatisierung",
    "Qualitätsinvestition": "qualitaet",
}

# Einkaufstypen (Anzeigetext → MaterialEinkaufsTyp-Wert)
EINKAUFSTYP_OPTIONEN = {
    "Spot (Marktpreis)": "spot",
    "Jahresvertrag (fix −10 %)": "langfrist",
}
