import pytest

from src.engine.production import verarbeite_quartal
from src.models.market import MarktZustand
from src.models.round import InvestitionsTyp, TeamEntscheidung
from src.models.team import Team


def _entscheidung(
    quartal: int,
    investition_betrag: float = 0.0,
) -> TeamEntscheidung:
    kwargs = {
        "team_id": "team_a",
        "jahr": 1,
        "quartal": quartal,
        "verkaufspreis": 10.0,
        "produktionsmenge_lose": 2,
        "marketingbudget": 0.0,
    }
    if investition_betrag > 0:
        kwargs["investition_typ"] = InvestitionsTyp.AUTOMATISIERUNG
        kwargs["investition_betrag"] = investition_betrag
    return TeamEntscheidung(**kwargs)


def test_automatisierung_senkt_fertigungskosten_ab_folgequartal():
    team = Team(id="team_a", name="Team A")
    markt_q1 = MarktZustand(jahr=1, quartal=1)
    markt_q2 = MarktZustand(jahr=1, quartal=2)

    q1 = verarbeite_quartal(
        team=team,
        entscheidung=_entscheidung(quartal=1, investition_betrag=5.0),
        markt=markt_q1,
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )

    q2 = verarbeite_quartal(
        team=team,
        entscheidung=_entscheidung(quartal=2),
        markt=markt_q2,
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )

    # Die Investition wird nach der laufenden Produktion gebucht:
    # Q1 bleibt bei 2 Lose * 3 Mio. Fertigung + 2 Lose * 1 Mio. Montage.
    assert q1.cashflow.auszahlungen_fertigung_stufe1 == pytest.approx(6.0)
    assert q1.cashflow.auszahlungen_montage_stufe2 == pytest.approx(2.0)

    # 5 Mio. Automatisierung senken Fertigung/Montage ab Q2 um 10 %.
    assert q2.cashflow.auszahlungen_fertigung_stufe1 == pytest.approx(5.4)
    assert q2.cashflow.auszahlungen_montage_stufe2 == pytest.approx(1.8)
    assert (
        q2.cashflow.auszahlungen_fertigung_stufe1
        + q2.cashflow.auszahlungen_montage_stufe2
    ) == pytest.approx(7.2)


def test_automatisiertes_team_hat_niedrigere_produktionsauszahlungen():
    normales_team = Team(id="team_a", name="Normal")
    automatisiertes_team = Team(id="team_a", name="Automatisiert")
    automatisiertes_team.automatisierungsinvestition_gesamt = 5.0

    markt = MarktZustand(jahr=1, quartal=1)

    normal = verarbeite_quartal(
        team=normales_team,
        entscheidung=_entscheidung(quartal=1),
        markt=markt,
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )
    automatisiert = verarbeite_quartal(
        team=automatisiertes_team,
        entscheidung=_entscheidung(quartal=1),
        markt=MarktZustand(jahr=1, quartal=1),
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )

    normale_fertigung_montage = (
        normal.cashflow.auszahlungen_fertigung_stufe1
        + normal.cashflow.auszahlungen_montage_stufe2
    )
    automatisierte_fertigung_montage = (
        automatisiert.cashflow.auszahlungen_fertigung_stufe1
        + automatisiert.cashflow.auszahlungen_montage_stufe2
    )

    assert normale_fertigung_montage == pytest.approx(8.0)
    assert automatisierte_fertigung_montage == pytest.approx(7.2)
    assert automatisierte_fertigung_montage < normale_fertigung_montage
