import pytest

from src.models.round import InvestitionsTyp, TeamEntscheidung
from src.services.game_service import GameService, SpielPhase


def _entscheidung(team_id: str, quartal: int, qualitaet: float = 0.0) -> TeamEntscheidung:
    kwargs = {
        "team_id": team_id,
        "jahr": 1,
        "quartal": quartal,
        "verkaufspreis": 10.0,
        "produktionsmenge_lose": 0,
        "marketingbudget": 0.0,
    }
    if qualitaet > 0:
        kwargs["investition_typ"] = InvestitionsTyp.QUALITAET
        kwargs["investition_betrag"] = qualitaet
    return TeamEntscheidung(**kwargs)


def _reiche_neutrale_entscheidungen_ein(game: GameService) -> None:
    z = game.zustand
    for tid in z.teams:
        game.reiche_entscheidung_ein(
            TeamEntscheidung(
                team_id=tid,
                jahr=z.aktuelles_jahr,
                quartal=z.aktuelles_quartal,
                verkaufspreis=10.0,
                produktionsmenge_lose=0,
                marketingbudget=0.0,
            )
        )


def test_quartal_gestartet_und_entscheidungen_werden_sauber_zurueckgesetzt():
    game = GameService.neues_spiel("Test", ["A", "B"], max_jahre=1)

    game.starte_quartal(ereignis_seed=1)
    assert game.zustand.quartal_gestartet is True

    _reiche_neutrale_entscheidungen_ein(game)
    assert game.alle_entscheidungen_eingereicht()

    game.verarbeite_quartal()

    assert game.zustand.quartal_gestartet is False
    assert game.zustand.aktuelle_entscheidungen == {}


def test_quartal_starten_zieht_ereignis_nicht_zweimal():
    game = GameService.neues_spiel("Test", ["A", "B"], max_jahre=1)

    erstes = game.starte_quartal(ereignis_seed=1)
    zweites = game.starte_quartal(ereignis_seed=2)

    assert zweites == erstes
    assert game.zustand.letztes_ereignis == erstes
    assert len(game.zustand.ereignis_historie) == 1


def test_gemeinkosten_basis_sinkt_ab_jahr_2_auf_5_mio_pro_quartal():
    game = GameService.neues_spiel("Test", ["A", "B"], max_jahre=2)

    for _ in range(4):
        game.starte_quartal(ereignis_seed=1)
        _reiche_neutrale_entscheidungen_ein(game)
        game.verarbeite_quartal()

    assert game.zustand.phase == SpielPhase.ENTSCHEIDUNG
    assert game.zustand.aktuelles_jahr == 2
    assert game.zustand.aktuelles_quartal == 1
    assert {t.gemeinkosten_pro_quartal for t in game.zustand.teams.values()} == {5.0}


def test_qualitaetsinvestition_wirkt_im_score_erst_ab_folgequartal():
    game = GameService.neues_spiel("Test", ["A", "B"], max_jahre=1)
    game.zustand.quartal_gestartet = True

    game.reiche_entscheidung_ein(_entscheidung("a", quartal=1, qualitaet=10.0))
    game.reiche_entscheidung_ein(_entscheidung("b", quartal=1))
    q1 = game.verarbeite_quartal()

    assert q1["a"].score_qualitaets_faktor == pytest.approx(1.0)
    assert game.zustand.teams["a"].qualitaetsinvestition_gesamt == pytest.approx(10.0)

    game.starte_quartal(ereignis_seed=1)
    game.reiche_entscheidung_ein(_entscheidung("a", quartal=2))
    game.reiche_entscheidung_ein(_entscheidung("b", quartal=2))
    q2 = game.verarbeite_quartal()

    assert q2["a"].score_qualitaets_faktor == pytest.approx(2.0)
