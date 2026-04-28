"""
engine/market_share.py – Marktanteil-Berechnung

Scoring-Formel (nachvollziehbar, nach Konzept):

    marketing_term  = (1 + marketingbudget / MARKETING_NORMALISIERUNG) ^ 0.4
    quality_factor  = 1 + qualitaetsinvestition_gesamt / QUALITAET_SKALIERUNG
    gk_term         = 1 + gemeinkosten_delta × Gemeinkosten-Wirkung
    preis_ratio     = verkaufspreis / BASIS_PREIS

    score(team)     = marketing_term × quality_factor × gk_term / preis_ratio^2.6
    marktanteil     = score(team) / sum(all_scores)
    lose(team)      = aktuelles_marktvolumen × marktanteil  (Largest-Remainder-Rundung)

Eigenschaften:
  - marketing = 0 → marketing_term = 1 (kein Ausschluss vom Markt)
  - Gemeinkosten sparen senkt den Score; Zusatzbudget für Service/F&E/Vertrieb erhöht ihn
  - Preis unter BASIS_PREIS → preis_ratio < 1 → höherer Score (günstigerer Preis attraktiver)
  - Qualitätsskandal: Non-Investoren erhalten score_faktor 0.8 (−20 %)
"""
from __future__ import annotations

import math

from src.models.market import EreignisTyp, MarktZustand, TeamScore
from src.models.round import TeamEntscheidung
from src.models.team import Team

# ─── Scoring-Konstanten ──────────────────────────────────────────────────────

MARKETING_EXPONENT: float = 0.4

#: Normalisierungsdivisor für Marketing (Mio. €).
#: Bei 10 M€ verdoppelt sich der Marketing-Term: (1+10/10)^0.4 = 2^0.4 ≈ 1.32
MARKETING_NORMALISIERUNG: float = 10.0

#: Referenzpreis (Mio. €).  preis_ratio = 1 → score neutral bezüglich Preis.
BASIS_PREIS: float = 10.0

#: Preis wirkt überproportional auf die Attraktivität, damit Extrempreise nicht dominant sind.
PREIS_SCORE_EXPONENT: float = 2.6

#: 10 M€ kumulierte Qualitätsinvestition → quality_factor = 2.0
QUALITAET_SKALIERUNG: float = 10.0

#: Mindestinvestition für Skandal-Schutz (Mio. €)
QUALITAET_INVESTOR_SCHWELLE: float = 5.0

#: Zusatzbudget hilft moderat; Sparprogramme schaden stärker, weil Service/F&E/Vertrieb leiden.
#: Bei UI-Grenzen −3/+5 ergibt das 0,85–1,15.
GEMEINKOSTEN_ZUSATZ_SCORE_PRO_MIO: float = 0.03
GEMEINKOSTEN_SPAR_SCORE_PRO_MIO: float = 0.05
GEMEINKOSTEN_SCORE_MIN: float = 0.70
GEMEINKOSTEN_SCORE_MAX: float = 1.30


# ─── Öffentliche Hilfsfunktionen ─────────────────────────────────────────────


def berechne_quality_factor(team: Team) -> float:
    """quality_factor = 1.0 + kumulierte_Qualitätsinvestition / 10."""
    return 1.0 + team.qualitaetsinvestition_gesamt / QUALITAET_SKALIERUNG


def ist_qualitaetsinvestor(team: Team) -> bool:
    """True wenn das Team ausreichend in Qualität investiert hat (Skandal-Schutz)."""
    return team.qualitaetsinvestition_gesamt >= QUALITAET_INVESTOR_SCHWELLE


def berechne_marketing_term(marketingbudget: float) -> float:
    """(1 + marketing / MARKETING_NORMALISIERUNG) ^ 0.4 – verwendbar für UI-Anzeige."""
    return math.pow(1.0 + marketingbudget / MARKETING_NORMALISIERUNG, MARKETING_EXPONENT)


def berechne_preis_ratio(verkaufspreis: float) -> float:
    """verkaufspreis / BASIS_PREIS – verwendbar für UI-Anzeige."""
    return verkaufspreis / BASIS_PREIS


def berechne_gemeinkosten_term(gemeinkosten_delta: float) -> float:
    """Score-Faktor aus Gemeinkosten-Anpassung: +1 Mio. → +3 %, −1 Mio. → −5 %."""
    if gemeinkosten_delta >= 0:
        term = 1.0 + gemeinkosten_delta * GEMEINKOSTEN_ZUSATZ_SCORE_PRO_MIO
    else:
        term = 1.0 + gemeinkosten_delta * GEMEINKOSTEN_SPAR_SCORE_PRO_MIO
    return max(GEMEINKOSTEN_SCORE_MIN, min(GEMEINKOSTEN_SCORE_MAX, term))


def berechne_rohscore(
    entscheidung: TeamEntscheidung,
    team: Team,
    score_faktor: float = 1.0,
) -> float:
    """
    Berechnet den Rohscore eines Teams.

    score = (1 + marketing / 10)^0.4 × quality_factor
            × gemeinkosten_term / (preis / 10)^2.6 × score_faktor

    Args:
        score_faktor: Externer Multiplikator (z.B. 0.8 bei Qualitätsskandal).
    """
    m_term = berechne_marketing_term(entscheidung.marketingbudget)
    quality = berechne_quality_factor(team)
    gk_term = berechne_gemeinkosten_term(entscheidung.gemeinkosten_delta)
    preis_r = berechne_preis_ratio(entscheidung.verkaufspreis)
    return m_term * quality * gk_term / (preis_r ** PREIS_SCORE_EXPONENT) * score_faktor


def berechne_team_scores(
    entscheidungen: list[TeamEntscheidung],
    teams_by_id: dict[str, Team],
    markt: MarktZustand,
) -> dict[str, TeamScore]:
    """
    Berechnet Rohscores aller aktiven Teams und normiert sie zu Marktanteilen.

    Sonderfälle:
    - Insolvent: übersprungen (kein Score, kein Marktanteil).
    - QUALITAETSSKANDAL: Non-Investoren erhalten score_faktor 0.8.
    - Gesamtscore = 0: Gleichverteilung als Fallback.

    Returns:
        ``{team_id: TeamScore}`` – ``zuteilbare_lose`` wird von demand nachträglich gesetzt.
    """
    ereignis = markt.aktives_ereignis
    ist_skandal = ereignis is not None and ereignis.typ == EreignisTyp.QUALITAETSSKANDAL

    # ── Rohscores ────────────────────────────────────────────────────────────
    rohscores: dict[str, float] = {}
    score_faktoren: dict[str, tuple[float, float, float, float, float]] = {}
    for ent in entscheidungen:
        team = teams_by_id.get(ent.team_id)
        if team is None or team.ist_insolvent:
            continue

        faktor = 1.0
        if ist_skandal:
            faktor = (
                ereignis.score_faktor_qualitaet
                if ist_qualitaetsinvestor(team)
                else ereignis.score_faktor_allgemein
            )

        marketing_term = berechne_marketing_term(ent.marketingbudget)
        quality_factor = berechne_quality_factor(team)
        gemeinkosten_factor = berechne_gemeinkosten_term(ent.gemeinkosten_delta)
        price_factor = berechne_preis_ratio(ent.verkaufspreis)

        rohscores[ent.team_id] = (
            marketing_term
            * quality_factor
            * gemeinkosten_factor
            / (price_factor ** PREIS_SCORE_EXPONENT)
            * faktor
        )
        score_faktoren[ent.team_id] = (
            marketing_term,
            quality_factor,
            gemeinkosten_factor,
            price_factor,
            faktor,
        )

    # ── Normierung → Marktanteile ─────────────────────────────────────────────
    gesamt = sum(rohscores.values())
    n = len(rohscores)

    result: dict[str, TeamScore] = {}
    for ent in entscheidungen:
        tid = ent.team_id
        if tid not in rohscores:
            continue

        anteil = rohscores[tid] / gesamt if gesamt > 0 else (1.0 / n if n > 0 else 0.0)
        marketing_term, quality_factor, gemeinkosten_factor, price_factor, faktor = score_faktoren[tid]

        result[tid] = TeamScore(
            team_id=tid,
            marketing=ent.marketingbudget,
            marketing_term=marketing_term,
            quality_factor=quality_factor,
            gemeinkosten_factor=gemeinkosten_factor,
            price_factor=price_factor,
            ereignis_factor=faktor,
            rohscore=round(rohscores[tid], 6),
            marktanteil=round(anteil, 6),
            zuteilbare_lose=0,
        )

    return result
