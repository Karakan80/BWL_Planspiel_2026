"""
engine/events.py – Ereigniskarten-Engine

Ziehen, Anwenden und Beschreiben der 10 Ereigniskarten.
Die Kartendefinitionen liegen in models/market.EREIGNISKARTEN.

Nutzung im Spielfluss:
    ereignis = ziehe_ereignis()           # 1× pro Quartal, vor Entscheidungsabgabe
    wende_an(ereignis, markt)             # Marktparameter sofort anpassen
    texte = beschreibe_effekte(ereignis)  # Für Spieler-Anzeige
"""
from __future__ import annotations

import random
from typing import Optional

from src.models.market import EREIGNISKARTEN, Ereignis, EreignisTyp, MarktZustand


def ziehe_ereignis(seed: Optional[int] = None) -> Ereignis:
    """
    Zieht zufällig eine der 10 Ereigniskarten (gleichwahrscheinlich).

    Args:
        seed: Optionaler RNG-Seed für reproduzierbare Spiele (Tests, Replay).
    """
    rng = random.Random(seed)
    return rng.choice(EREIGNISKARTEN)


def get_ereignis(typ: EreignisTyp) -> Ereignis:
    """
    Gibt die vordefinierte Karte für einen bestimmten EreignisTyp zurück.
    Nützlich für gezielte Szenario-Tests.

    Raises:
        ValueError: wenn kein Eintrag für ``typ`` existiert.
    """
    for karte in EREIGNISKARTEN:
        if karte.typ == typ:
            return karte
    raise ValueError(f"Keine Ereigniskarte für Typ {typ!r}")


def wende_an(ereignis: Ereignis, markt: MarktZustand) -> None:
    """
    Wendet das Ereignis auf den MarktZustand an (Marktvolumen, Preise, Zinsen …).
    Delegiert an ``MarktZustand.anwende_ereignis()``.
    """
    markt.anwende_ereignis(ereignis)


def beschreibe_effekte(ereignis: Ereignis) -> list[str]:
    """
    Gibt eine menschenlesbare Liste der Ereignisauswirkungen zurück.
    Nur tatsächlich abweichende Effekte (Faktor ≠ 1.0 oder Delta ≠ 0) erscheinen.

    Beispiel-Output für ROHSTOFFKRISE:
        ["Materialpreis +25%"]

    Beispiel-Output für QUALITAETSSKANDAL:
        ["Scoring aller Teams −20 % (Qualitätsinvestoren ausgenommen)"]

    Returns:
        Nicht-leere Liste; enthält „Keine Auswirkungen" bei RUHIGE_RUNDE.
    """
    effekte: list[str] = []

    if ereignis.materialpreis_faktor != 1.0:
        pct = (ereignis.materialpreis_faktor - 1.0) * 100
        effekte.append(f"Materialpreis {pct:+.0f} %")

    if ereignis.marktvolumen_faktor != 1.0:
        pct = (ereignis.marktvolumen_faktor - 1.0) * 100
        effekte.append(f"Marktvolumen {pct:+.0f} %")

    if ereignis.produktionskosten_faktor != 1.0:
        pct = (ereignis.produktionskosten_faktor - 1.0) * 100
        effekte.append(f"Produktionskosten {pct:+.0f} %")

    if ereignis.investitionskosten_faktor != 1.0:
        pct = (ereignis.investitionskosten_faktor - 1.0) * 100
        effekte.append(f"Investitionskosten {pct:+.0f} %")

    if ereignis.zinssatz_delta != 0.0:
        pct = ereignis.zinssatz_delta * 100
        effekte.append(f"Zinssatz {pct:+.1f} Prozentpunkte")

    if ereignis.score_faktor_allgemein != 1.0:
        pct = (ereignis.score_faktor_allgemein - 1.0) * 100
        effekte.append(
            f"Scoring aller Teams {pct:+.0f} % (Qualitätsinvestoren ausgenommen)"
        )

    return effekte if effekte else ["Keine Auswirkungen"]
