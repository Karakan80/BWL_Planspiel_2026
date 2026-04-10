"""
ui/components/guv_table.py – GuV-Tabelle (Quartal oder Jahr)

Verwendung:
    from src.ui.components.guv_table import render_guv
    render_guv(qe.guv)
    render_guv(jahres_guv, zeige_abschreibungen=True, titel="Jahres-GuV")
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from src.models.round import GuV


def render_guv(
    guv: GuV,
    zeige_abschreibungen: bool = False,
    titel: Optional[str] = None,
) -> None:
    """
    Rendert eine GuV als kompakte zweispaltige Tabelle (Label | Wert).

    Args:
        guv:                  GuV-Objekt (Quartal oder Jahresabschluss).
        zeige_abschreibungen: Bei True wird die AfA-Zeile zwischen Gemeinkosten
                              und EBIT eingefügt (relevant für Jahres-GuV).
        titel:                Optionaler Überschrift-Text (als ``st.caption``).
    """
    if titel:
        st.caption(titel)

    positionen: list[tuple[str, float, bool]] = [
        # (Bezeichnung, Wert, ist_summenzeile)
        ("Umsatz",              guv.umsatz,              False),
        ("− Herstellungskosten", guv.herstellungskosten,  False),
        ("= Rohertrag",          guv.rohertrag,           True),
        ("− Gemeinkosten",       guv.gemeinkosten,        False),
    ]

    if zeige_abschreibungen:
        positionen.append(("− Abschreibungen", guv.abschreibungen, False))

    positionen += [
        ("= EBIT",       guv.ebit,       True),
        ("− Zinsen",     guv.zinsen,     False),
        ("= EBT",        guv.ebt,        True),
        ("− Steuern",    guv.steuern,    False),
        ("= Nettogewinn", guv.nettogewinn, True),
    ]

    for label, wert, ist_summe in positionen:
        col1, col2 = st.columns([3, 1])
        if ist_summe:
            col1.markdown(f"**{label}**")
            col2.markdown(f"**{wert:+.2f}**")
        else:
            col1.text(label)
            col2.text(f"{wert:.2f}")
