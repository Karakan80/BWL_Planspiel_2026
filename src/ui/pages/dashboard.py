"""
ui/pages/dashboard.py – Auswertungs-Dashboard

4 Tabs:
  1. Übersicht    – Ranking-Chart, Gewinnentwicklung (Linechart), Marktanteile (Stacked Bar)
  2. GuV & KPIs   – GuV-Vergleich, Kennzahlen-Tabelle, EBIT-Balkendiagramm
  3. Bilanzen     – Bilanzvergleich-Tabelle + Einzelbilanzen je Team
  4. Cashflow     – Waterfall-Chart für Team/Jahr/Quartal (wählbar)
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import TEAM_FARBEN
from src.services import scoring_service
from src.services.game_service import GameService
from src.ui.components import balance_sheet, ranking_chart


def render(game: GameService) -> None:
    st.title("📈 Auswertungs-Dashboard")

    z = game.zustand
    if not z.quartal_ergebnisse and not z.jahres_guv:
        st.info("Noch keine Spielrunden abgeschlossen. Bitte zuerst Quartale spielen.")
        return

    tab1, tab2, tab3, tab4 = st.tabs(
        ["🏆 Übersicht", "📋 GuV & KPIs", "📊 Bilanzen", "💧 Cashflow"]
    )

    with tab1:
        _render_uebersicht(game)
    with tab2:
        _render_guv_kpis(game)
    with tab3:
        _render_bilanzen(game)
    with tab4:
        _render_cashflow(game)


# ── Tab 1: Übersicht ──────────────────────────────────────────────────────────


def _render_uebersicht(game: GameService) -> None:
    z = game.zustand

    # Ranking
    st.subheader("Aktuelles Ranking")
    ranking_chart.render_ranking(scoring_service.erstelle_ranking(z))

    st.divider()

    # Gewinnentwicklung
    st.subheader("Gewinnentwicklung (Netto) aller Teams")
    daten = scoring_service.get_gewinnentwicklung(z)

    if daten["jahre"]:
        fig = go.Figure()
        for i, (team_name, werte) in enumerate(daten["serien"].items()):
            fig.add_trace(
                go.Scatter(
                    x=daten["jahre"],
                    y=werte,
                    mode="lines+markers",
                    name=team_name,
                    line=dict(color=TEAM_FARBEN[i % len(TEAM_FARBEN)], width=2),
                    marker=dict(size=8),
                )
            )
        fig.update_layout(
            xaxis_title="Jahr",
            yaxis_title="Nettogewinn (Mio. €)",
            legend_title="Teams",
            height=380,
            xaxis=dict(tickmode="linear", dtick=1),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Noch keine abgeschlossenen Geschäftsjahre.")

    st.divider()

    # Marktanteil-Verlauf
    st.subheader("Marktanteil-Verlauf (alle Quartale)")
    ma_daten = scoring_service.get_marktanteile_verlauf(z)

    if ma_daten["etiketten"]:
        fig2 = go.Figure()
        for i, (team_name, werte) in enumerate(ma_daten["serien"].items()):
            fig2.add_trace(
                go.Bar(
                    x=ma_daten["etiketten"],
                    y=[v * 100 for v in werte],
                    name=team_name,
                    marker_color=TEAM_FARBEN[i % len(TEAM_FARBEN)],
                )
            )
        fig2.update_layout(
            barmode="stack",
            xaxis_title="Quartal",
            yaxis_title="Marktanteil (%)",
            legend_title="Teams",
            height=360,
            yaxis=dict(range=[0, 100]),
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Noch keine Quartalsdaten vorhanden.")


# ── Tab 2: GuV & KPIs ─────────────────────────────────────────────────────────


def _render_guv_kpis(game: GameService) -> None:
    z = game.zustand

    jahre = sorted(
        {int(j) for guv in z.jahres_guv.values() for j in guv.keys()}
    )
    if not jahre:
        st.info("Noch keine Jahresabschlüsse vorhanden.")
        return

    ausgewaehltes_jahr = st.selectbox(
        "Jahr auswählen", jahre, index=len(jahre) - 1, key="dash_guv_jahr"
    )

    # GuV-Vergleich als DataFrame
    st.subheader(f"GuV-Vergleich Jahr {ausgewaehltes_jahr}")
    guv_data = scoring_service.get_guv_vergleich(z, ausgewaehltes_jahr)

    if guv_data:
        positionen = [
            ("umsatz",            "Umsatz"),
            ("herstellungskosten","Herstellungskosten"),
            ("rohertrag",         "Rohertrag"),
            ("gemeinkosten",      "Gemeinkosten"),
            ("abschreibungen",    "Abschreibungen"),
            ("ebit",              "EBIT"),
            ("zinsen",            "Zinsen"),
            ("ebt",               "EBT"),
            ("steuern",           "Steuern"),
            ("nettogewinn",       "Nettogewinn"),
        ]
        df_dict: dict[str, dict[str, float]] = {}
        for tid, guv in guv_data.items():
            df_dict[z.teams[tid].name] = {lbl: guv.get(key, 0.0) for key, lbl in positionen}

        df = pd.DataFrame(df_dict).T
        st.dataframe(df.style.format("{:.2f}"), use_container_width=True)

        # EBIT-Balkendiagramm
        st.subheader("EBIT-Vergleich")
        team_namen_chart = list(df_dict.keys())
        ebit_werte = [df_dict[n]["EBIT"] for n in team_namen_chart]
        farben = [TEAM_FARBEN[i % len(TEAM_FARBEN)] for i in range(len(team_namen_chart))]
        fig_ebit = go.Figure(
            go.Bar(
                x=team_namen_chart,
                y=ebit_werte,
                marker_color=farben,
                text=[f"{v:.2f}" for v in ebit_werte],
                textposition="outside",
            )
        )
        fig_ebit.update_layout(
            xaxis_title="Team",
            yaxis_title="EBIT (Mio. €)",
            height=360,
        )
        st.plotly_chart(fig_ebit, use_container_width=True)

    # Kennzahlen
    st.subheader(f"Kennzahlen Jahr {ausgewaehltes_jahr}")
    kz_tabelle = scoring_service.get_kennzahlen_tabelle(z, ausgewaehltes_jahr)
    if kz_tabelle:
        df_kz = pd.DataFrame(kz_tabelle).set_index("Team")
        st.dataframe(
            df_kz.style.format("{:.2f}", na_rep="–"),
            use_container_width=True,
        )
    else:
        st.info("Keine Kennzahlen für dieses Jahr vorhanden.")


# ── Tab 3: Bilanzen ───────────────────────────────────────────────────────────


def _render_bilanzen(game: GameService) -> None:
    z = game.zustand

    st.subheader("Bilanzvergleich (aktueller Stand)")
    bv = scoring_service.get_bilanzvergleich(z)
    if bv:
        df = pd.DataFrame(bv).set_index("Team")
        df = df.drop(columns=["Insolvent"], errors="ignore")
        st.dataframe(df.style.format("{:.2f}"), use_container_width=True)

    st.divider()
    st.subheader("Bilanzen je Team")

    anzahl = len(z.teams)
    cols_per_row = min(3, anzahl)
    team_liste = list(z.teams.items())

    for row_start in range(0, anzahl, cols_per_row):
        cols = st.columns(cols_per_row)
        for col, (tid, team) in zip(cols, team_liste[row_start: row_start + cols_per_row]):
            with col:
                with st.container(border=True):
                    balance_sheet.render_bilanz(team)


# ── Tab 4: Cashflow-Waterfall ─────────────────────────────────────────────────


def _render_cashflow(game: GameService) -> None:
    z = game.zustand

    aktive_ids = [tid for tid, t in z.teams.items() if not t.ist_insolvent]
    if not aktive_ids:
        st.info("Keine aktiven Teams vorhanden.")
        return

    # Auswahl-Controls
    col1, col2, col3 = st.columns(3)

    with col1:
        namen_map = {z.teams[tid].name: tid for tid in aktive_ids}
        ausgewaehlter_name = st.selectbox("Team", list(namen_map.keys()), key="cf_team")
        ausgewaehltes_tid = namen_map[ausgewaehlter_name]

    alle_perioden = sorted(
        {(qe.jahr, qe.quartal)
         for qe in z.quartal_ergebnisse
         if qe.team_id == ausgewaehltes_tid},
    )
    if not alle_perioden:
        st.info("Noch keine Quartalsdaten für dieses Team.")
        return

    with col2:
        jahre_vorhanden = sorted({j for j, _ in alle_perioden})
        ausgewaehltes_jahr = st.selectbox(
            "Jahr", jahre_vorhanden, index=len(jahre_vorhanden) - 1, key="cf_jahr"
        )

    with col3:
        quartale_vorhanden = sorted(
            q for j, q in alle_perioden if j == ausgewaehltes_jahr
        )
        ausgewaehltes_quartal = st.selectbox(
            "Quartal",
            quartale_vorhanden,
            index=len(quartale_vorhanden) - 1,
            key="cf_quartal",
        )

    # Waterfall-Daten
    wf = scoring_service.get_cashflow_waterfall(
        z, ausgewaehltes_tid, ausgewaehltes_jahr, ausgewaehltes_quartal
    )

    if not wf["positionen"]:
        st.info("Keine Cashflow-Daten für diese Periode.")
        return

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=wf["typen"],
            x=wf["positionen"],
            y=wf["werte"],
            text=[f"{v:+.2f}" for v in wf["werte"]],
            textposition="outside",
            connector={"line": {"color": "#888888"}},
            increasing={"marker": {"color": "#2ca02c"}},
            decreasing={"marker": {"color": "#d62728"}},
            totals={"marker": {"color": "#1f77b4"}},
        )
    )
    fig.update_layout(
        title=(
            f"Cashflow-Waterfall – {ausgewaehlter_name} – "
            f"J{ausgewaehltes_jahr} / Q{ausgewaehltes_quartal}"
        ),
        xaxis_title="Position",
        yaxis_title="Mio. €",
        height=520,
    )
    st.plotly_chart(fig, use_container_width=True)
