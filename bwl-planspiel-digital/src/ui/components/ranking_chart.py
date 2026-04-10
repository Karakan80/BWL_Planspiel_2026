"""
ui/components/ranking_chart.py – Ranking-Balkendiagramm + Ranglisten-Tabelle

Verwendung:
    from src.ui.components.ranking_chart import render_ranking
    render_ranking(scoring_service.erstelle_ranking(zustand))
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import TEAM_FARBEN
from src.services.scoring_service import TeamRangEintrag


def render_ranking(ranking: list[TeamRangEintrag]) -> None:
    """
    Rendert:
    1. Plotly-Balkendiagramm: Eigenkapital je Team (absteigend).
    2. Ranglisten-Tabelle mit Rang, Eigenkapital, ROS/ROE/ROI.
    """
    if not ranking:
        st.info("Noch keine Rankingdaten verfügbar.")
        return

    _render_chart(ranking)
    st.markdown("")
    _render_tabelle(ranking)


# ── private ───────────────────────────────────────────────────────────────────


def _render_chart(ranking: list[TeamRangEintrag]) -> None:
    namen = [e.team_name for e in ranking]
    werte = [e.eigenkapital for e in ranking]
    farben = [
        "#aaaaaa" if e.ist_insolvent else TEAM_FARBEN[i % len(TEAM_FARBEN)]
        for i, e in enumerate(ranking)
    ]

    fig = go.Figure(
        go.Bar(
            x=namen,
            y=werte,
            marker_color=farben,
            text=[f"{v:.1f}" for v in werte],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Ranking – Eigenkapital (Mio. €)",
        xaxis_title="Team",
        yaxis_title="Eigenkapital (Mio. €)",
        height=360,
        margin=dict(t=50, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_tabelle(ranking: list[TeamRangEintrag]) -> None:
    def _fmt(v: float | None, suffix: str = "") -> str:
        return f"{v:.1f}{suffix}" if v is not None else "–"

    zeilen = [
        {
            "Rang": f"{'💀 ' if e.ist_insolvent else ''}{e.rang}",
            "Team": e.team_name,
            "Eigenkapital": f"{e.eigenkapital:.2f} Mio. €",
            "Nettogewinn ∑": f"{e.nettogewinn_gesamt:.2f} Mio. €",
            "ROS": _fmt(e.letzter_ros, " %"),
            "ROE": _fmt(e.letzter_roe, " %"),
            "ROI": _fmt(e.letzter_roi, " %"),
        }
        for e in ranking
    ]
    df = pd.DataFrame(zeilen)
    st.dataframe(df, use_container_width=True, hide_index=True)
