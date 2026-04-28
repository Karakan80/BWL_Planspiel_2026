"""
engine/demand.py – Gesamtnachfrage & Zuteilung

Verbindet Marktvolumen (aus MarktZustand) mit der Score-basierten
Verteilung (market_share) zu konkreten Loszahlen je Team.

Ablauf pro Quartal:
    1. Scores und Marktanteile berechnen  (→ market_share.berechne_team_scores)
    2. MarktZustand.team_scores befüllen
    3. Gesamtnachfrage an aktive Teamanzahl anpassen
    4. Gesamtnachfrage anhand des Marktpreises anpassen
    5. Nachfrage in ganze Lose aufteilen
       (Restzuteilung: Teams mit höchsten Nachkommaanteilen zuerst)
"""
from __future__ import annotations

from src.engine.market_share import BASIS_PREIS, berechne_team_scores
from src.models.market import MarktZustand, TeamScore
from src.models.round import TeamEntscheidung
from src.models.team import Team


PREIS_ELASTIZITAET: float = 3.0
MIN_PREIS_NACHFRAGE_FAKTOR: float = 0.08
MAX_PREIS_NACHFRAGE_FAKTOR: float = 1.25
REFERENZ_TEAMANZAHL: int = 4


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

    # Gesamtnachfrage: Ereignisvolumen × Teamanzahl-Faktor × Preiselastizität.
    # Dadurch ist "alle setzen Preis 30" nicht mehr automatisch stark.
    _wende_teamanzahl_faktor_an(markt, len(score_dict))
    gesamt_lose: float = _wende_preiselastizitaet_an(
        markt,
        entscheidungen,
        score_dict,
    )

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


def _wende_teamanzahl_faktor_an(markt: MarktZustand, aktive_teamanzahl: int) -> None:
    """
    Skaliert die Gesamtnachfrage auf die Anzahl aktiver Firmen.

    4 Teams sind die Referenz aus dem Planspiel-Prototyp: 4 Teams = 40 Lose,
    2 Teams = 20 Lose, 6 Teams = 60 Lose, jeweils vor Preiselastizität.
    """
    markt.aktive_teamanzahl = aktive_teamanzahl
    if aktive_teamanzahl <= 0:
        markt.teamanzahl_faktor = 0.0
        markt.marktvolumen_vor_preis_lose = 0.0
        markt.aktuelles_marktvolumen_lose = 0.0
        return

    markt.teamanzahl_faktor = round(aktive_teamanzahl / REFERENZ_TEAMANZAHL, 4)
    markt.marktvolumen_vor_preis_lose = round(
        markt.aktuelles_marktvolumen_lose * markt.teamanzahl_faktor,
        4,
    )


def _wende_preiselastizitaet_an(
    markt: MarktZustand,
    entscheidungen: list[TeamEntscheidung],
    score_dict: dict[str, TeamScore],
) -> float:
    """
    Passt das gesamte Marktvolumen an das Preisniveau an.

    Der gewichtete Durchschnittspreis nutzt die Rohscores als Gewichte. Dadurch
    zählt ein extrem teures, unattraktives Angebot weniger stark als ein Angebot,
    das der Markt tatsächlich attraktiv findet.
    """
    entscheidungen_by_id = {ent.team_id: ent for ent in entscheidungen}
    aktive_preise: list[tuple[float, float]] = []
    for tid, score in score_dict.items():
        ent = entscheidungen_by_id.get(tid)
        if ent is None:
            continue
        aktive_preise.append((ent.verkaufspreis, max(0.0, score.rohscore)))

    if not aktive_preise:
        markt.durchschnittspreis_markt = BASIS_PREIS
        markt.preis_elastizitaets_faktor = 1.0
        return 0.0

    gewicht_summe = sum(gewicht for _, gewicht in aktive_preise)
    if gewicht_summe > 0:
        durchschnittspreis = (
            sum(preis * gewicht for preis, gewicht in aktive_preise)
            / gewicht_summe
        )
    else:
        durchschnittspreis = sum(preis for preis, _ in aktive_preise) / len(aktive_preise)

    preis_ratio = max(0.01, durchschnittspreis / BASIS_PREIS)
    faktor = (1.0 / preis_ratio) ** PREIS_ELASTIZITAET
    faktor = max(MIN_PREIS_NACHFRAGE_FAKTOR, min(MAX_PREIS_NACHFRAGE_FAKTOR, faktor))

    markt.durchschnittspreis_markt = round(durchschnittspreis, 4)
    markt.preis_elastizitaets_faktor = round(faktor, 4)
    markt.aktuelles_marktvolumen_lose = round(
        markt.marktvolumen_vor_preis_lose * faktor,
        4,
    )
    return markt.aktuelles_marktvolumen_lose


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
