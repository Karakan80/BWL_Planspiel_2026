"""
ui/components/balance_sheet.py – Aktiva/Passiva-Tabelle

Verwendung:
    from src.ui.components.balance_sheet import render_bilanz
    render_bilanz(team)
"""
from __future__ import annotations

import streamlit as st

from src.models.team import Team


def render_bilanz(team: Team) -> None:
    """
    Rendert Aktiva und Passiva eines Teams nebeneinander in zwei Spalten.

    Bei insolventen Teams wird stattdessen eine Fehlermeldung angezeigt.
    """
    st.markdown(f"**{team.name}**")

    if team.ist_insolvent:
        st.error("INSOLVENT – Team scheidet aus dem Wettbewerb aus.")
        return

    a = team.aktiva
    p = team.passiva

    col_a, col_p = st.columns(2)

    with col_a:
        st.caption("Aktiva (Mio. €)")
        _zeile("Grundstücke",       a.grundstuecke)
        _zeile("Gebäude",           a.gebaeude)
        _zeile("Maschinen",         a.maschinen)
        _zeile("BGA",               a.bga)
        _zeile("Rohmaterial",       a.rohmaterial)
        _zeile("Unfertige Erz.",    a.unfertige_erzeugnisse)
        _zeile("Fertigwaren",       a.fertigwaren)
        _zeile("Forderungen",       a.forderungen)
        kasse_farbe = "red" if a.kasse < 0 else "normal"
        _zeile("Kasse / Bank",      a.kasse, farbe=kasse_farbe)
        st.divider()
        _zeile("**Bilanzsumme**",   a.summe, fett=True)

    with col_p:
        st.caption("Passiva (Mio. €)")
        _zeile("Grundkapital",      p.grundkapital)
        _zeile("Gewinnrücklage",    p.gewinnruecklage)
        _zeile("**Eigenkapital**",  p.eigenkapital, fett=True)
        st.divider()
        _zeile("Langfrist. FK",     p.langfristiges_fk)
        st.divider()
        _zeile("**Bilanzsumme**",   p.summe, fett=True)


# ── Hilfsfunktion ─────────────────────────────────────────────────────────────


def _zeile(
    label: str,
    wert: float,
    fett: bool = False,
    farbe: str = "normal",
) -> None:
    """Rendert eine einzelne Bilanzzeile (Label + rechtsbündiger Wert)."""
    c1, c2 = st.columns([3, 1])

    label_md = f"**{label}**" if fett else label
    wert_str = f"{wert:.2f}"

    c1.markdown(label_md)
    if farbe == "red":
        c2.markdown(f":red[{wert_str}]")
    else:
        c2.markdown(f"**{wert_str}**" if fett else wert_str)
