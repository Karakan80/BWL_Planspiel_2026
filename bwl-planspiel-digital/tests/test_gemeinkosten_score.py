import pytest

from src.engine.market_share import (
    berechne_gemeinkosten_term,
    berechne_rohscore,
    berechne_team_scores,
)
from src.models.market import MarktZustand
from src.models.round import TeamEntscheidung
from src.models.team import Team


def _entscheidung(team_id: str, gemeinkosten_delta: float) -> TeamEntscheidung:
    return TeamEntscheidung(
        team_id=team_id,
        jahr=1,
        quartal=1,
        verkaufspreis=10.0,
        produktionsmenge_lose=0,
        marketingbudget=0.0,
        gemeinkosten_delta=gemeinkosten_delta,
    )


def test_gemeinkosten_delta_wirkt_auf_markt_score():
    team = Team(id="team_a", name="Team A")

    neutral = berechne_rohscore(_entscheidung("team_a", 0.0), team)
    zusatzbudget = berechne_rohscore(_entscheidung("team_a", 1.0), team)
    sparprogramm = berechne_rohscore(_entscheidung("team_a", -1.0), team)

    assert berechne_gemeinkosten_term(1.0) == pytest.approx(1.03)
    assert berechne_gemeinkosten_term(-1.0) == pytest.approx(0.95)
    assert zusatzbudget == pytest.approx(neutral * 1.03)
    assert sparprogramm == pytest.approx(neutral * 0.95)


def test_zusatzbudget_erhoeht_marktanteil_gegenueber_neutralem_team():
    entscheidungen = [
        _entscheidung("team_a", 5.0),
        _entscheidung("team_b", 0.0),
    ]
    teams = {
        "team_a": Team(id="team_a", name="Zusatzbudget"),
        "team_b": Team(id="team_b", name="Neutral"),
    }

    scores = berechne_team_scores(
        entscheidungen,
        teams,
        MarktZustand(jahr=1, quartal=1),
    )

    assert scores["team_a"].rohscore == pytest.approx(1.15)
    assert scores["team_a"].marktanteil > scores["team_b"].marktanteil
    assert scores["team_a"].marktanteil == pytest.approx(0.534884)
