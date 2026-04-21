import pytest

from src.engine.events import get_ereignis, wende_an
from src.models.market import EreignisTyp, MarktZustand
from src.models.round import MaterialEinkaufsTyp


def test_rohstoffkrise_macht_spot_teurer_aber_jahresvertrag_stabil():
    markt = MarktZustand(jahr=1, quartal=1)
    wende_an(get_ereignis(EreignisTyp.ROHSTOFFKRISE), markt)

    assert markt.materialpreis_fuer(MaterialEinkaufsTyp.SPOT) == pytest.approx(3.75)
    assert markt.materialpreis_fuer(MaterialEinkaufsTyp.LANGFRIST) == pytest.approx(2.7)


def test_wirtschaftskrise_macht_spot_guenstiger_als_jahresvertrag():
    markt = MarktZustand(jahr=1, quartal=1)
    wende_an(get_ereignis(EreignisTyp.WIRTSCHAFTSKRISE), markt)

    assert markt.materialpreis_fuer(MaterialEinkaufsTyp.SPOT) == pytest.approx(2.55)
    assert markt.materialpreis_fuer(MaterialEinkaufsTyp.LANGFRIST) == pytest.approx(2.7)
    assert (
        markt.materialpreis_fuer(MaterialEinkaufsTyp.SPOT)
        < markt.materialpreis_fuer(MaterialEinkaufsTyp.LANGFRIST)
    )
