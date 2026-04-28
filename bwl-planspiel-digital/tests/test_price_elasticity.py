import pytest

from src.engine.demand import verteile_nachfrage
from src.models.market import MarktZustand
from src.models.round import TeamEntscheidung
from src.models.team import Team


def _teams(anzahl: int = 4) -> list[Team]:
    return [Team(id=f"team_{i}", name=f"Team {i}") for i in range(anzahl)]


def _entscheidungen(teams: list[Team], preis: float) -> list[TeamEntscheidung]:
    return [
        TeamEntscheidung(
            team_id=team.id,
            jahr=1,
            quartal=1,
            verkaufspreis=preis,
            produktionsmenge_lose=2,
            marketingbudget=0.0,
        )
        for team in teams
    ]


def test_basispreis_haelt_basisnachfrage():
    teams = _teams()
    markt = MarktZustand(jahr=1, quartal=1)

    nachfrage = verteile_nachfrage(markt, _entscheidungen(teams, 10.0), teams)

    assert sum(nachfrage.values()) == 40
    assert markt.preis_elastizitaets_faktor == pytest.approx(1.0)
    assert markt.durchschnittspreis_markt == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("teamanzahl", "erwartete_nachfrage", "teamfaktor"),
    [
        (2, 20, 0.5),
        (4, 40, 1.0),
        (6, 60, 1.5),
    ],
)
def test_basisnachfrage_skaliert_mit_aktiver_teamanzahl(
    teamanzahl: int,
    erwartete_nachfrage: int,
    teamfaktor: float,
):
    teams = _teams(teamanzahl)
    markt = MarktZustand(jahr=1, quartal=1)

    nachfrage = verteile_nachfrage(markt, _entscheidungen(teams, 10.0), teams)

    assert sum(nachfrage.values()) == erwartete_nachfrage
    assert markt.aktive_teamanzahl == teamanzahl
    assert markt.teamanzahl_faktor == pytest.approx(teamfaktor)
    assert markt.marktvolumen_vor_preis_lose == pytest.approx(erwartete_nachfrage)


def test_preis_30_senkt_gesamtnachfrage_deutlich():
    teams = _teams()
    markt = MarktZustand(jahr=1, quartal=1)

    nachfrage = verteile_nachfrage(markt, _entscheidungen(teams, 30.0), teams)

    assert sum(nachfrage.values()) == 3
    assert sum(nachfrage.values()) < len(teams) * 2
    assert markt.preis_elastizitaets_faktor == pytest.approx(0.08, abs=0.0001)
    assert markt.aktuelles_marktvolumen_lose == pytest.approx(3.2, abs=0.0001)


def test_extremer_hochpreis_anbieter_bekommt_nicht_automatisch_genug_nachfrage():
    teams = [
        Team(id="high", name="High"),
        Team(id="balanced", name="Balanced"),
        Team(id="value", name="Value"),
        Team(id="adaptive", name="Adaptive"),
    ]
    entscheidungen = [
        TeamEntscheidung(
            team_id="high",
            jahr=1,
            quartal=1,
            verkaufspreis=30.0,
            produktionsmenge_lose=2,
            marketingbudget=0.0,
        ),
        TeamEntscheidung(
            team_id="balanced",
            jahr=1,
            quartal=1,
            verkaufspreis=12.0,
            produktionsmenge_lose=2,
            marketingbudget=2.0,
        ),
        TeamEntscheidung(
            team_id="value",
            jahr=1,
            quartal=1,
            verkaufspreis=10.0,
            produktionsmenge_lose=2,
            marketingbudget=1.0,
        ),
        TeamEntscheidung(
            team_id="adaptive",
            jahr=1,
            quartal=1,
            verkaufspreis=16.0,
            produktionsmenge_lose=2,
            marketingbudget=0.0,
        ),
    ]

    nachfrage = verteile_nachfrage(MarktZustand(jahr=1, quartal=1), entscheidungen, teams)

    assert nachfrage["high"] <= 1


def test_niedriger_preis_kann_marktvolumen_erhoehen_aber_ist_gekappt():
    teams = _teams()
    markt = MarktZustand(jahr=1, quartal=1)

    nachfrage = verteile_nachfrage(markt, _entscheidungen(teams, 7.5), teams)

    assert sum(nachfrage.values()) == 50
    assert markt.preis_elastizitaets_faktor == pytest.approx(1.25)
