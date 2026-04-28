from collections import Counter

from src.models.market import EreignisTyp
from src.models.round import (
    InvestitionsTyp,
    MASCHINEN_PREISE,
    MaschinenVariante,
    MaterialEinkaufsTyp,
    TeamEntscheidung,
)
from src.services.game_service import GameService


STRATEGIEN = ["Fixed16", "Adaptive", "Investor", "High30"]


def _entscheidung(name: str, game: GameService, team_id: str) -> TeamEntscheidung:
    z = game.zustand
    team = z.teams[team_id]
    quartal_index = (z.aktuelles_jahr - 1) * 4 + z.aktuelles_quartal
    ereignis_typ = z.letztes_ereignis.typ if z.letztes_ereignis else None
    einkauf = (
        MaterialEinkaufsTyp.SPOT
        if ereignis_typ == EreignisTyp.WIRTSCHAFTSKRISE
        else MaterialEinkaufsTyp.LANGFRIST
    )

    basis = dict(
        team_id=team_id,
        jahr=z.aktuelles_jahr,
        quartal=z.aktuelles_quartal,
        produktionsmenge_lose=team.kapazitaet_lose_pro_quartal,
        material_einkauf=einkauf,
    )

    if name == "Fixed16":
        return TeamEntscheidung(
            **basis,
            verkaufspreis=16.0,
            marketingbudget=0.0,
            gemeinkosten_delta=0.0,
        )

    if name == "High30":
        return TeamEntscheidung(
            **basis,
            verkaufspreis=30.0,
            marketingbudget=0.0,
            gemeinkosten_delta=0.0,
        )

    if name == "Adaptive":
        preis = 16.0
        marketing = 1.0
        zusatzbudget = 0.0
        if ereignis_typ in (EreignisTyp.NACHFRAGEBOOM, EreignisTyp.EXPORTCHANCE):
            preis = 18.0
            marketing = 0.0
        elif ereignis_typ in (EreignisTyp.WIRTSCHAFTSKRISE, EreignisTyp.NEUE_KONKURRENZ):
            preis = 13.0
            marketing = 2.0
            zusatzbudget = 1.0
        elif ereignis_typ == EreignisTyp.QUALITAETSSKANDAL:
            preis = 14.0
            marketing = 2.0

        kwargs = dict(
            basis,
            verkaufspreis=preis,
            marketingbudget=marketing,
            gemeinkosten_delta=zusatzbudget,
        )
        if (
            ereignis_typ == EreignisTyp.TECHNOLOGIESPRUNG
            and team.kapazitaet_lose_pro_quartal < 4
        ):
            kwargs.update(
                investition_typ=InvestitionsTyp.MASCHINE,
                maschinen_variante=MaschinenVariante.STANDARD,
                investition_betrag=MASCHINEN_PREISE[MaschinenVariante.STANDARD],
            )
        elif quartal_index == 2:
            kwargs.update(
                investition_typ=InvestitionsTyp.QUALITAET,
                investition_betrag=5.0,
            )
        return TeamEntscheidung(**kwargs)

    kwargs = dict(
        basis,
        verkaufspreis=14.0,
        marketingbudget=1.0,
        gemeinkosten_delta=0.0,
    )
    if quartal_index == 1:
        kwargs.update(
            kredit_aufnahme=20.0,
            investition_typ=InvestitionsTyp.MASCHINE,
            maschinen_variante=MaschinenVariante.STANDARD,
            investition_betrag=MASCHINEN_PREISE[MaschinenVariante.STANDARD],
        )
    elif quartal_index == 2:
        kwargs.update(
            investition_typ=InvestitionsTyp.AUTOMATISIERUNG,
            investition_betrag=5.0,
        )
    return TeamEntscheidung(**kwargs)


def test_keine_stumpfe_standardstrategie_gewinnt_immer():
    gewinner: list[str] = []

    for seed in range(20):
        game = GameService.neues_spiel("Balance", STRATEGIEN, max_jahre=3)
        while game.zustand.phase.value != "abgeschlossen":
            quartal_index = (
                (game.zustand.aktuelles_jahr - 1) * 4
                + game.zustand.aktuelles_quartal
            )
            game.starte_quartal(ereignis_seed=seed * 100 + quartal_index)
            for name in STRATEGIEN:
                team_id = name.lower()
                if not game.zustand.teams[team_id].ist_insolvent:
                    game.reiche_entscheidung_ein(_entscheidung(name, game, team_id))
            game.verarbeite_quartal()

        ranking = sorted(
            game.zustand.teams.values(),
            key=lambda t: (t.ist_insolvent, -t.passiva.eigenkapital),
        )
        gewinner.append(ranking[0].name)

    siege = Counter(gewinner)

    assert len(siege) >= 2
    assert siege["High30"] <= 2
    assert siege["Fixed16"] < 10
