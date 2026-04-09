"""
engine/market_share.py – Marktanteil-Berechnung

Scoring-Formel (Konzept):
    score(team) = marketing^0.4 * quality_factor / price_factor
    market_share(team) = score(team) / sum(all_scores)

quality_factor steigt mit kumulierten Qualitätsinvestitionen.
Ereignis QUALITAETSSKANDAL: Score nicht-investierender Teams −20 %;
Qualitätsinvestoren bleiben unberührt.
"""
from __future__ import annotations

import math

from src.models.market import EreignisTyp, MarktZustand, TeamScore
from src.models.round import TeamEntscheidung
from src.models.team import Team

# ─── Scoring-Konstanten ──────────────────────────────────────────────────────
MARKETING_EXPONENT: float = 0.4      # Aus Konzeptformel: marketing^0.4
MARKETING_MIN: float = 0.01          # Untergrenze: verhindert score=0 bei marketing=0

QUALITAET_SKALIERUNG: float = 10.0         # 10 M Invest → quality_factor +1.0
QUALITAET_INVESTOR_SCHWELLE: float = 5.0   # Ab 5 M gilt Team als "Qualitätsinvestor"


def berechne_quality_factor(team: Team) -> float:
    """
    Berechnet den quality_factor aus kumulierten Qualitätsinvestitionen.

    Basis: 1.0 (kein Invest).  Jede 10 M Qualitätsinvestition erhöhen den
    Faktor um 1.0, so dass größere Investitionen überproportional belohnt werden.
    """
    return 1.0 + team.qualitaetsinvestition_gesamt / QUALITAET_SKALIERUNG


def ist_qualitaetsinvestor(team: Team) -> bool:
    """True wenn das Team ausreichend in Qualität investiert hat (Skandal-Schutz)."""
    return team.qualitaetsinvestition_gesamt >= QUALITAET_INVESTOR_SCHWELLE


def berechne_rohscore(
    entscheidung: TeamEntscheidung,
    team: Team,
    score_faktor: float = 1.0,
) -> float:
    """
    Berechnet den Rohscore eines Teams nach der Konzeptformel.

    score = max(marketing, MARKETING_MIN)^0.4 * quality_factor / verkaufspreis

    Args:
        score_faktor: Externer Multiplikator (z.B. 0.8 bei Qualitätsskandal).
    """
    marketing_eff = max(entscheidung.marketingbudget, MARKETING_MIN)
    quality = berechne_quality_factor(team)
    raw = math.pow(marketing_eff, MARKETING_EXPONENT) * quality / entscheidung.verkaufspreis
    return raw * score_faktor


def berechne_team_scores(
    entscheidungen: list[TeamEntscheidung],
    teams_by_id: dict[str, Team],
    markt: MarktZustand,
) -> dict[str, TeamScore]:
    """
    Berechnet Rohscores aller Teams und normiert sie zu Marktanteilen.

    Sonderfälle:
    - Insolvent: Team wird übersprungen (kein Score, kein Anteil).
    - QUALITAETSSKANDAL: Non-Investoren erhalten score_faktor 0.8,
      Qualitätsinvestoren bleiben bei 1.0.
    - Gesamtscore = 0 (z.B. alle marketing=0): Gleichverteilung als Fallback.

    Returns:
        ``{team_id: TeamScore}`` mit befüllten rohscore und marktanteil.
        ``zuteilbare_lose`` wird von demand.verteile_nachfrage nachträglich gesetzt.
    """
    ereignis = markt.aktives_ereignis
    ist_skandal = (
        ereignis is not None and ereignis.typ == EreignisTyp.QUALITAETSSKANDAL
    )

    # ── Rohscores berechnen ──────────────────────────────────────────────────
    rohscores: dict[str, float] = {}
    for ent in entscheidungen:
        team = teams_by_id.get(ent.team_id)
        if team is None or team.ist_insolvent:
            continue

        if ist_skandal:
            faktor = (
                ereignis.score_faktor_qualitaet    # 1.0 – unberührt
                if ist_qualitaetsinvestor(team)
                else ereignis.score_faktor_allgemein  # 0.8 – Abzug
            )
        else:
            faktor = 1.0

        rohscores[ent.team_id] = berechne_rohscore(ent, team, faktor)

    # ── Normierung zu Marktanteilen ──────────────────────────────────────────
    gesamt = sum(rohscores.values())
    n = len(rohscores)

    result: dict[str, TeamScore] = {}
    for ent in entscheidungen:
        tid = ent.team_id
        if tid not in rohscores:
            continue

        anteil = rohscores[tid] / gesamt if gesamt > 0 else (1.0 / n if n > 0 else 0.0)

        result[tid] = TeamScore(
            team_id=tid,
            marketing=ent.marketingbudget,
            quality_factor=berechne_quality_factor(teams_by_id[tid]),
            price_factor=ent.verkaufspreis,
            rohscore=round(rohscores[tid], 6),
            marktanteil=round(anteil, 6),
            zuteilbare_lose=0,  # wird von demand.verteile_nachfrage gesetzt
        )

    return result
