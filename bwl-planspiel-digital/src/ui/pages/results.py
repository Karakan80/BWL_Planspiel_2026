"""
ui/pages/results.py – Ergebnisanzeige nach einem Quartal

Zeigt:
  - Aktive Ereigniskarte
  - Marktanteile (Tortendiagramm)
  - Quartalsergebnis je Team (Quartal-GuV + Kasse-Snapshot)
  - Bei Q4: Jahresabschluss (Jahres-GuV + Kennzahlen)
  - Aktuelles Ranking
  - Navigation: Nächste Entscheidungsrunde / Dashboard
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.config import TEAM_FARBEN
from src.engine.market_share import (
    BASIS_PREIS,
    MARKETING_NORMALISIERUNG,
    berechne_marketing_term,
    berechne_preis_ratio,
    berechne_quality_factor,
)
from src.models.round import QuartalErgebnis
from src.services import scoring_service
from src.services.game_service import GameService, SpielPhase
from src.ui.components import guv_table, ranking_chart


def render(game: GameService) -> None:
    ergebnisse: dict[str, QuartalErgebnis] | None = st.session_state.get("letztes_ergebnisse")

    if not ergebnisse:
        st.warning("Keine Ergebnisse verfügbar. Bitte zuerst ein Quartal auswerten.")
        return

    z = game.zustand
    first_qe = next(iter(ergebnisse.values()))
    ausg_jahr = first_qe.jahr
    ausg_quartal = first_qe.quartal
    ist_q4 = ausg_quartal == 4

    st.title(f"📊 Ergebnisse – Jahr {ausg_jahr} / Q{ausg_quartal}")

    # ── Ereigniskarte ──────────────────────────────────────────────────────
    _render_ereigniskarte(game)
    st.divider()

    # ── Marktanteile (Tortendiagramm) ──────────────────────────────────────
    st.subheader("Marktanteile dieses Quartals")
    _render_marktanteile_pie(ergebnisse, z)
    st.divider()

    # ── Quartalsergebnisse je Team ─────────────────────────────────────────
    st.subheader("Quartalsergebnisse")
    _render_quartalsergebnisse(ergebnisse, z)

    # ── Jahresabschluss bei Q4 ─────────────────────────────────────────────
    if ist_q4:
        st.divider()
        st.subheader(f"Jahresabschluss Jahr {ausg_jahr}")
        _render_jahresabschluss(game, ausg_jahr)

    st.divider()

    # ── Ranking ────────────────────────────────────────────────────────────
    st.subheader("Aktuelles Ranking")
    ranking_chart.render_ranking(scoring_service.erstelle_ranking(z))

    st.divider()

    # ── Navigation ─────────────────────────────────────────────────────────
    _render_navigation(game)


# ── Ereigniskarte ─────────────────────────────────────────────────────────────


def _render_ereigniskarte(game: GameService) -> None:
    e = game.zustand.letztes_ereignis
    if e is None:
        return

    from src.engine.events import beschreibe_effekte

    with st.container(border=True):
        col1, col2 = st.columns([1, 5])
        col1.markdown("## 🎴")
        with col2:
            st.markdown(f"**{e.titel}**")
            st.markdown(e.beschreibung)
            effekte = beschreibe_effekte(e)
            st.caption(" · ".join(effekte))


# ── Marktanteile ──────────────────────────────────────────────────────────────


def _render_marktanteile_pie(
    ergebnisse: dict[str, QuartalErgebnis],
    z,
) -> None:
    namen = [z.teams[tid].name for tid in ergebnisse]
    anteile = [qe.marktanteil for qe in ergebnisse.values()]
    verkauft = [qe.verkaufte_lose for qe in ergebnisse.values()]

    col_pie, col_tabelle = st.columns([2, 3])

    with col_pie:
        fig = go.Figure(
            go.Pie(
                labels=namen,
                values=anteile,
                textinfo="label+percent",
                hole=0.35,
                marker_colors=TEAM_FARBEN[: len(namen)],
            )
        )
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_tabelle:
        st.markdown("**Marktdetails**")
        for tid, qe in ergebnisse.items():
            name = z.teams[tid].name
            st.markdown(
                f"**{name}** – {qe.marktanteil * 100:.1f} % | "
                f"{qe.verkaufte_lose} Lose | Score: {qe.score:.3f}"
            )

    # ── Score-Zusammensetzung (Formel-Transparenz) ────────────────────────────
    with st.expander("🔍 Score-Berechnung (Formel-Erklärung)", expanded=False):
        st.markdown(
            "**Formel:** `score = (1 + Marketing / "
            f"{MARKETING_NORMALISIERUNG:.0f})^0.4 × Qualitätsfaktor / (Preis / {BASIS_PREIS:.0f})`"
        )
        _render_score_breakdown(ergebnisse, z)


# ── Quartalsergebnisse ────────────────────────────────────────────────────────


def _render_quartalsergebnisse(
    ergebnisse: dict[str, QuartalErgebnis],
    z,
) -> None:
    cols = st.columns(max(1, len(ergebnisse)))
    for col, (tid, qe) in zip(cols, ergebnisse.items()):
        with col:
            st.markdown(f"**{z.teams[tid].name}**")
            guv_table.render_guv(qe.guv)
            st.divider()
            kasse = qe.kasse_nach_quartal
            farbe = "red" if kasse < 0 else "green"
            st.markdown(f"Kasse: :{farbe}[**{kasse:.2f} M€**]")
            st.caption(
                f"Forderungen: {qe.forderungen_nach_quartal:.2f}  |  "
                f"EK: {qe.eigenkapital_nach_quartal:.2f}  |  "
                f"FK: {qe.fremdkapital_nach_quartal:.2f}"
            )


# ── Score-Breakdown ──────────────────────────────────────────────────────────


def _render_score_breakdown(ergebnisse: dict[str, QuartalErgebnis], z) -> None:
    """Zeigt für jedes Team wie sich der Score aus den drei Faktoren zusammensetzt."""
    import pandas as pd

    zeilen = []
    for tid, qe in ergebnisse.items():
        team = z.teams[tid]
        ent = qe.entscheidung
        m_term = berechne_marketing_term(ent.marketingbudget)
        qf = berechne_quality_factor(team)
        pr = berechne_preis_ratio(ent.verkaufspreis)
        score_recomputed = m_term * qf / pr
        zeilen.append({
            "Team": team.name,
            f"Mkt-Term (1+M/{MARKETING_NORMALISIERUNG:.0f})^0.4": round(m_term, 4),
            "Qualitäts-Faktor": round(qf, 4),
            f"Preis-Ratio (P/{BASIS_PREIS:.0f})": round(pr, 4),
            "Score": round(score_recomputed, 4),
            "Marktanteil": f"{qe.marktanteil * 100:.1f} %",
            "Lose zugeteilt": qe.verkaufte_lose,
        })

    df = pd.DataFrame(zeilen).set_index("Team")
    st.dataframe(df, use_container_width=True)

    st.caption(
        "Marketing-Term: höheres Budget → größerer Wert. "
        "Preis-Ratio: niedrigerer Preis → kleinerer Nenner → höherer Score. "
        "Qualitäts-Faktor: steigt mit kumulierten Qualitätsinvestitionen."
    )


# ── Jahresabschluss ───────────────────────────────────────────────────────────


def _render_jahresabschluss(game: GameService, jahr: int) -> None:
    z = game.zustand
    jahr_key = str(jahr)

    for tid, team in z.teams.items():
        guv_j = z.jahres_guv.get(tid, {}).get(jahr_key)
        if guv_j is None:
            continue
        kpis = z.jahres_kennzahlen.get(tid, {}).get(jahr_key)

        with st.expander(f"📋 {team.name}", expanded=True):
            col_guv, col_kpis = st.columns(2)

            with col_guv:
                guv_table.render_guv(guv_j, titel="Jahres-GuV (Mio. €)")

            with col_kpis:
                if kpis:
                    st.caption("Kennzahlen")
                    _render_kennzahlen(kpis)

            if team.ist_insolvent:
                st.error("⚠️ Team ist nach diesem Jahr insolvent.")


def _render_kennzahlen(kpis) -> None:
    def _f(v) -> str:
        return f"{v:.1f}" if v is not None else "–"

    col1, col2 = st.columns(2)
    with col1:
        st.metric("ROS", f"{_f(kpis.ros)} %")
        st.metric("ROE", f"{_f(kpis.roe)} %")
        st.metric("ROI", f"{_f(kpis.roi)} %")
    with col2:
        st.metric("KU", _f(kpis.ku))
        st.metric("BEP (Lose)", _f(kpis.bep))
        if kpis.liquiditaet_1 is not None:
            st.metric("Liq. I", _f(kpis.liquiditaet_1))


# ── Navigation ────────────────────────────────────────────────────────────────


def _render_navigation(game: GameService) -> None:
    z = game.zustand
    col_weiter, col_dash = st.columns(2)

    with col_weiter:
        if z.phase == SpielPhase.ABGESCHLOSSEN:
            st.success("🏆 Das Spiel ist beendet!")
            if st.button(
                "🏆 Zum Abschluss-Dashboard",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.seite = "dashboard"
                st.rerun()
        else:
            if st.button(
                "▶️ Nächstes Quartal",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.seite = "entscheidung"
                st.session_state.quartal_gestartet = False
                st.rerun()

    with col_dash:
        hat_jahresdaten = bool(z.jahres_guv)
        if st.button(
            "📈 Dashboard",
            use_container_width=True,
            disabled=not hat_jahresdaten,
        ):
            st.session_state.seite = "dashboard"
            st.rerun()
