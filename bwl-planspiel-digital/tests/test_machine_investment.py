import pytest

from src.engine.production import verarbeite_quartal
from src.models.market import MarktZustand
from src.models.round import InvestitionsTyp, MaschinenVariante, TeamEntscheidung
from src.models.team import Team


def _maschinenentscheidung(
    betrag: float,
    variante: MaschinenVariante = MaschinenVariante.STANDARD,
) -> TeamEntscheidung:
    return TeamEntscheidung(
        team_id="team_a",
        jahr=1,
        quartal=1,
        verkaufspreis=10.0,
        produktionsmenge_lose=0,
        marketingbudget=0.0,
        investition_typ=InvestitionsTyp.MASCHINE,
        investition_betrag=betrag,
        maschinen_variante=variante,
    )


def test_maschine_unter_20_mio_ist_nicht_erlaubt():
    with pytest.raises(ValueError, match="mindestens 20 Mio"):
        _maschinenentscheidung(1.0)


def test_maschine_fuer_20_mio_erhoeht_kapazitaet_um_1():
    team = Team(id="team_a", name="Team A")

    verarbeite_quartal(
        team=team,
        entscheidung=_maschinenentscheidung(20.0),
        markt=MarktZustand(jahr=1, quartal=1),
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )

    assert team.kapazitaet_lose_pro_quartal == 3


def test_hochleistungsanlage_fuer_40_mio_erhoeht_kapazitaet_um_2():
    team = Team(id="team_a", name="Team A")

    verarbeite_quartal(
        team=team,
        entscheidung=_maschinenentscheidung(40.0, MaschinenVariante.HOCHLEISTUNG),
        markt=MarktZustand(jahr=1, quartal=1),
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )

    assert team.kapazitaet_lose_pro_quartal == 4


def test_effizienzmaschine_erhoeht_kapazitaet_und_senkt_folgekosten():
    team = Team(id="team_a", name="Team A")

    verarbeite_quartal(
        team=team,
        entscheidung=_maschinenentscheidung(30.0, MaschinenVariante.EFFIZIENZ),
        markt=MarktZustand(jahr=1, quartal=1),
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )
    q2 = verarbeite_quartal(
        team=team,
        entscheidung=TeamEntscheidung(
            team_id="team_a",
            jahr=1,
            quartal=2,
            verkaufspreis=10.0,
            produktionsmenge_lose=2,
            marketingbudget=0.0,
        ),
        markt=MarktZustand(jahr=1, quartal=2),
        verkaufte_lose=0,
        forderungen_vorquartal=0.0,
    )

    assert team.kapazitaet_lose_pro_quartal == 3
    assert team.automatisierungsinvestition_gesamt == 5.0
    assert q2.cashflow.auszahlungen_fertigung_stufe1 == pytest.approx(5.4)
    assert q2.cashflow.auszahlungen_montage_stufe2 == pytest.approx(1.8)
