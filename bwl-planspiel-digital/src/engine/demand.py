"""
engine/demand.py – Gesamtnachfrage & Zuteilung

Verbindet Marktvolumen (aus MarktZustand) mit der Score-basierten
Verteilung (market_share) zu konkreten Loszahlen je Team.

Ablauf pro Quartal:
    1. Scores und Marktanteile berechnen  (→ market_share.berechne_team_scores)
    2. MarktZustand.team_scores befüllen
    3. Nachfrage in ganze Lose aufteilen
       (Restzuteilung: Teams mit höchsten Nachkommaanteilen zuerst)
"""
from __future__ import annotations

from src.engine.market_share import berechne_team_scores
from src.models.market import MarktZustand
from src.models.round import TeamEntscheidung
from src.models.team import Team


def verteile_nachfrage(
    markt: MarktZustand,
    entscheidungen: list[TeamEntscheidung],
    teams: list[Team],
) -> dict[str, int]:
    """
    Berechnet die Losverteilung für alle Teams eines Quartals.

    Mutiert ``markt.team_scores`` mit den berechneten Scores.

    Args:
        markt:         Marktparameter mit Gesamtvolumen und Ereigniseffekten.
        entscheidungen: Alle Teamentscheidungen des Quartals.
        teams:         Teamzustände (für quality_factor, Insolvenznach check).

    Returns:
        ``{team_id: anzahl_lose_int}`` – summiert auf das gerundete Gesamtvolumen.
    """
    teams_by_id: dict[str, Team] = {t.id: t for t in teams}

    # Scores + Marktanteile berechnen und in MarktZustand schreiben
    score_dict = berechne_team_scores(entscheidungen, teams_by_id, markt)
    markt.team_scores = score_dict

    # Gesamtnachfrage (bereits durch Ereignis angepasst)
    gesamt_lose: float = markt.aktuelles_marktvolumen_lose

    # Float-Zuteilung je Team
    zuteilung_float: dict[str, float] = {
        tid: gesamt_lose * ts.marktanteil
        for tid, ts in score_dict.items()
    }

    ergebnis = _runde_mit_rest(zuteilung_float)

    # Zuteilung in TeamScore-Objekten nachführen
    for tid, lose in ergebnis.items():
        if tid in score_dict:
            score_dict[tid].zuteilbare_lose = lose

    return ergebnis


# ─── Private Hilfsfunktionen ─────────────────────────────────────────────────


def _runde_mit_rest(zuteilung: dict[str, float]) -> dict[str, int]:
    """
    Wandelt float-Loszuteilungen verlustfrei in ganze Zahlen um.

    Algorithmus:
        1. Alle Werte abrunden (floor).
        2. Fehlende Lose (Gesamt − Summe der floor-Werte) an Teams mit den
           größten Nachkommaanteilen verteilen (Largest-Remainder-Methode).

    Beispiel: 40 Lose, Anteile 0.375 / 0.350 / 0.275
        floor: 15 / 14 / 11 = 40 → kein Rest ✓
    Beispiel: 40 Lose, Anteile 0.41 / 0.35 / 0.24
        floor: 16 / 14 / 9 = 39 → 1 Rest → geht an Team mit Nachkomma 0.4 → 17
    """
    if not zuteilung:
        return {}

    ziel = round(sum(zuteilung.values()))
    floor_values: dict[str, int] = {tid: int(v) for tid, v in zuteilung.items()}
    rest = ziel - sum(floor_values.values())

    # Nach Nachkommateil absteigend sortieren
    nachkomma = sorted(
        zuteilung.keys(),
        key=lambda t: zuteilung[t] - int(zuteilung[t]),
        reverse=True,
    )
    for i in range(max(0, rest)):
        if i < len(nachkomma):
            floor_values[nachkomma[i]] += 1

    return floor_values
