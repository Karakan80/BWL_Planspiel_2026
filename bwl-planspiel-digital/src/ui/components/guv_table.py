"""
ui/components/guv_table.py – GuV-Tabelle (Quartal oder Jahr)

Verwendung:
    from src.ui.components.guv_table import render_guv
    render_guv(qe.guv)
    render_guv(jahres_guv, titel="Jahres-GuV")
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from src.models.round import GuV


def render_guv(guv: GuV, titel: Optional[str] = None) -> None:
    """
    Rendert eine GuV als kompakte zweispaltige Tabelle (Label | Wert).

    Zeigt immer die vollständige GuV inkl. Abschreibungen, Zinsen und Steuern.

    Args:
        guv:   GuV-Objekt (Quartal oder Jahresabschluss).
        titel: Optionaler Überschrift-Text (als ``st.caption``).
    """
    if titel:
        st.caption(titel)

    positionen: list[tuple[str, float, bool]] = [
        # (Bezeichnung, Wert, ist_summenzeile)
        ("Umsatzerlöse",           guv.umsatz,              False),
        ("− Herstellungskosten",   guv.herstellungskosten,  False),
        ("= Bruttoergebnis",       guv.rohertrag,           True),
        ("− Gemeinkosten",         guv.gemeinkosten,        False),
        ("− Abschreibungen",       guv.abschreibungen,      False),
        ("= EBIT",                 guv.ebit,                True),
        ("− Zinsen",               guv.zinsen,              False),
        ("= EBT",                  guv.ebt,                 True),
        ("− Steuern (33,3 %)",     guv.steuern,             False),
        ("= Nettogewinn",          guv.nettogewinn,         True),
    ]

    for label, wert, ist_summe in positionen:
        col1, col2 = st.columns([3, 1])
        if ist_summe:
            col1.markdown(f"**{label}**")
            col2.markdown(f"**{wert:+.2f}**")
        else:
            col1.text(label)
            col2.text(f"{wert:.2f}")
