"""
ui/pages/decision.py – Entscheidungsformulare für alle Teams

Ablauf:
  1. "Quartal starten" → starte_quartal() → Ereigniskarte ziehen
  2. Ereigniskarte anzeigen
  3. Für jedes aktive Team: Entscheidungsformular in st.expander
  4. Wenn alle Teams eingereicht haben → "Quartal auswerten"
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from src.models.round import InvestitionsTyp, MaterialEinkaufsTyp, TeamEntscheidung
from src.models.team import Team
from src.services import state_service
from src.services.game_service import GameService, SpielPhase


def render(game: GameService) -> None:
    z = game.zustand

    if z.phase == SpielPhase.ABGESCHLOSSEN:
        st.success("🏆 Das Spiel ist beendet!")
        if st.button("📈 Zum Dashboard", type="primary"):
            st.session_state.seite = "dashboard"
            st.rerun()
        return

    st.title(f"📝 Entscheidung – Jahr {z.aktuelles_jahr} / Q{z.aktuelles_quartal}")

    # ── Schritt 1: Quartal starten ─────────────────────────────────────────
    if not st.session_state.get("quartal_gestartet", False):
        st.info(
            "Klicke auf **Quartal starten**, um die Ereigniskarte zu ziehen "
            "und die Entscheidungsphase zu öffnen."
        )
        if st.button("🎲 Quartal starten", type="primary", use_container_width=True):
            game.starte_quartal()
            st.session_state.quartal_gestartet = True
            state_service.auto_save(z)
            st.rerun()
        return

    # ── Ereigniskarte ──────────────────────────────────────────────────────
    _render_ereigniskarte(game)
    st.divider()

    # ── Team-Formulare ─────────────────────────────────────────────────────
    aktive_teams = [t for t in z.teams.values() if not t.ist_insolvent]
    eingereichte = set(z.aktuelle_entscheidungen.keys())

    fortschritt = len(eingereichte)
    gesamt = len(aktive_teams)
    st.progress(fortschritt / gesamt if gesamt else 1.0,
                text=f"{fortschritt} / {gesamt} Teams haben eingereicht")

    for team in aktive_teams:
        tid = team.id
        fertig = tid in eingereichte
        icon = "✅" if fertig else "⏳"

        with st.expander(f"{icon} {team.name}", expanded=not fertig):
            if fertig:
                _render_zusammenfassung(z.aktuelle_entscheidungen[tid])
            else:
                _render_team_form(game, team)

    st.divider()

    # ── Quartal auswerten ──────────────────────────────────────────────────
    alle_fertig = game.alle_entscheidungen_eingereicht()
    if alle_fertig:
        if st.button(
            "⚙️ Quartal auswerten",
            type="primary",
            use_container_width=True,
        ):
            try:
                ergebnisse = game.verarbeite_quartal()
                st.session_state.letztes_ergebnisse = ergebnisse
                st.session_state.quartal_gestartet = False
                state_service.auto_save(game.zustand)
                st.session_state.seite = "ergebnisse"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    else:
        st.button(
            "⚙️ Quartal auswerten",
            disabled=True,
            use_container_width=True,
            help="Alle aktiven Teams müssen zuerst eine Entscheidung einreichen.",
        )


# ── Ereigniskarte ─────────────────────────────────────────────────────────────


def _render_ereigniskarte(game: GameService) -> None:
    e = game.zustand.letztes_ereignis
    if e is None:
        return

    from src.engine.events import beschreibe_effekte

    with st.container(border=True):
        st.markdown(f"### 🎴 Ereigniskarte: {e.titel}")
        st.markdown(e.beschreibung)
        effekte = beschreibe_effekte(e)
        for eff in effekte:
            st.markdown(f"- {eff}")


# ── Eingereichte Entscheidung (Lesemodus) ─────────────────────────────────────


def _render_zusammenfassung(ent: TeamEntscheidung) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Verkaufspreis", f"{ent.verkaufspreis:.1f} Mio. €")
    col2.metric("Produktion", f"{ent.produktionsmenge_lose} Lose")
    col3.metric("Marketing", f"{ent.marketingbudget:.1f} Mio. €")

    details: list[str] = [f"Einkauf: {ent.material_einkauf.value}"]
    if ent.kredit_aufnahme > 0:
        details.append(f"Kredit: +{ent.kredit_aufnahme:.1f}")
    if ent.tilgung > 0:
        details.append(f"Tilgung: −{ent.tilgung:.1f}")
    if ent.investition_typ:
        details.append(f"Invest.: {ent.investition_typ.value} ({ent.investition_betrag:.1f} Mio.€)")
    st.caption(" | ".join(details))


# ── Entscheidungsformular ─────────────────────────────────────────────────────


def _render_team_form(game: GameService, team: Team) -> None:
    z = game.zustand
    tid = team.id

    with st.form(key=f"form_{tid}_{z.aktuelles_jahr}_{z.aktuelles_quartal}"):
        col_prod, col_fin = st.columns(2)

        # ── Produktion & Markt ─────────────────────────────────────────────
        with col_prod:
            st.markdown("**Produktion & Markt**")

            verkaufspreis = st.number_input(
                "Verkaufspreis (Mio. €/Los)",
                min_value=7.1,
                max_value=30.0,
                value=10.0,
                step=0.5,
                key=f"preis_{tid}",
            )
            prod_menge = st.number_input(
                "Produktionsmenge (Lose)",
                min_value=0,
                max_value=team.kapazitaet_lose_pro_quartal,
                value=min(2, team.kapazitaet_lose_pro_quartal),
                step=1,
                key=f"prod_{tid}",
            )
            marketing = st.number_input(
                "Marketingbudget (Mio. €)",
                min_value=0.0,
                max_value=20.0,
                value=1.0,
                step=0.5,
                key=f"mkt_{tid}",
            )
            einkauf_label = st.selectbox(
                "Materialeinkauf",
                options=["Spot (Marktpreis)", "Jahresvertrag (−10 % stabil)"],
                key=f"einkauf_{tid}",
            )
            einkauf = (
                MaterialEinkaufsTyp.LANGFRIST
                if "Jahresvertrag" in einkauf_label
                else MaterialEinkaufsTyp.SPOT
            )

        # ── Finanzierung & Investition ─────────────────────────────────────
        with col_fin:
            st.markdown("**Finanzierung & Investition**")

            kredit = st.number_input(
                "Kredit aufnehmen (Mio. €)",
                min_value=0.0,
                max_value=200.0,
                value=0.0,
                step=1.0,
                key=f"kredit_{tid}",
            )
            max_tilgung = max(0.0, float(team.passiva.langfristiges_fk))
            tilgung = st.number_input(
                "Tilgung (Mio. €)",
                min_value=0.0,
                max_value=max_tilgung,
                value=0.0,
                step=1.0,
                key=f"tilgung_{tid}",
            )

            st.markdown("**Investition**")
            inv_opt = st.selectbox(
                "Investitionstyp",
                options=[
                    "Keine",
                    "Maschine (+1 Kapazität)",
                    "Automatisierung",
                    "Qualitätsinvestition",
                ],
                key=f"invtyp_{tid}",
            )

            inv_typ: Optional[InvestitionsTyp] = None
            inv_betrag = 0.0

            if inv_opt != "Keine":
                inv_betrag = st.number_input(
                    "Investitionsbetrag (Mio. €)",
                    min_value=0.1,
                    max_value=100.0,
                    value=5.0,
                    step=0.5,
                    key=f"invbet_{tid}",
                )
                inv_typ = {
                    "Maschine (+1 Kapazität)": InvestitionsTyp.MASCHINE,
                    "Automatisierung": InvestitionsTyp.AUTOMATISIERUNG,
                    "Qualitätsinvestition": InvestitionsTyp.QUALITAET,
                }[inv_opt]

        # ── Team-Info-Zeile ────────────────────────────────────────────────
        st.caption(
            f"Kasse: {team.aktiva.kasse:.2f} Mio. €  |  "
            f"FK: {team.passiva.langfristiges_fk:.2f} Mio. €  |  "
            f"Kapazität: {team.kapazitaet_lose_pro_quartal} Lose/Q"
        )

        submitted = st.form_submit_button(
            "✅ Entscheidung einreichen",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        _reiche_ein(game, tid, z, verkaufspreis, int(prod_menge),
                    marketing, einkauf, kredit, tilgung, inv_typ, inv_betrag)


def _reiche_ein(
    game: GameService,
    tid: str,
    z,
    verkaufspreis: float,
    prod_menge: int,
    marketing: float,
    einkauf: MaterialEinkaufsTyp,
    kredit: float,
    tilgung: float,
    inv_typ: Optional[InvestitionsTyp],
    inv_betrag: float,
) -> None:
    try:
        entscheidung = TeamEntscheidung(
            team_id=tid,
            jahr=z.aktuelles_jahr,
            quartal=z.aktuelles_quartal,
            verkaufspreis=verkaufspreis,
            produktionsmenge_lose=prod_menge,
            marketingbudget=marketing,
            material_einkauf=einkauf,
            investition_typ=inv_typ,
            investition_betrag=inv_betrag,
            kredit_aufnahme=kredit,
            tilgung=tilgung,
        )
        game.reiche_entscheidung_ein(entscheidung)
        state_service.auto_save(game.zustand)
        st.rerun()
    except (ValueError, Exception) as exc:
        st.error(f"Fehler beim Einreichen: {exc}")
