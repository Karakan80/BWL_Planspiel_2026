"""
ui/pages/setup.py – Spieleinrichtung

Inhalt:
  - Tab "Neues Spiel": Spielname, Teamanzahl, Teamnamen, Spiellänge → Spiel starten
  - Tab "Laden": Bestehenden Spielstand laden oder löschen
"""
from __future__ import annotations

import streamlit as st

from src.config import APP_NAME, DEFAULT_JAHRE, MAX_JAHRE, MAX_TEAMS, MIN_JAHRE, MIN_TEAMS
from src.services import state_service
from src.services.game_service import GameService, SpielPhase


def render() -> None:
    st.title(f"🏭 {APP_NAME} – Spieleinrichtung")

    tab_neu, tab_laden = st.tabs(["✨ Neues Spiel", "📂 Gespeichertes Spiel laden"])

    with tab_neu:
        _render_neues_spiel()

    with tab_laden:
        _render_laden()


# ── Neues Spiel ───────────────────────────────────────────────────────────────


def _render_neues_spiel() -> None:
    st.subheader("Neues Spiel erstellen")

    # Slider AUSSERHALB des Formulars → reagiert sofort auf Änderungen
    if "setup_anzahl_teams" not in st.session_state:
        st.session_state["setup_anzahl_teams"] = 4

    anzahl_teams: int = st.slider(
        "Anzahl Teams",
        MIN_TEAMS,
        MAX_TEAMS,
        key="setup_anzahl_teams",
    )

    with st.form("neues_spiel_form"):
        spielname = st.text_input("Spielname", value="BWL Planspiel 2026")
        max_jahre = st.slider("Spiellänge (Jahre)", MIN_JAHRE, MAX_JAHRE, DEFAULT_JAHRE)

        st.markdown(f"**Teamnamen** ({anzahl_teams} Teams):")
        team_namen: list[str] = []
        cols = st.columns(2)
        for i in range(anzahl_teams):
            with cols[i % 2]:
                name = st.text_input(
                    f"Team {i + 1}",
                    value=f"Team {chr(65 + i)}",
                    key=f"setup_team_{i}",
                )
                team_namen.append(name)

        submitted = st.form_submit_button(
            "🚀 Spiel starten", type="primary", use_container_width=True
        )

    if submitted:
        _starte_spiel(spielname.strip(), team_namen, max_jahre)


def _starte_spiel(
    spielname: str,
    team_namen_raw: list[str],
    max_jahre: int,
) -> None:
    team_namen = [n.strip() for n in team_namen_raw if n.strip()]

    if len(team_namen) < MIN_TEAMS:
        st.error(f"Mindestens {MIN_TEAMS} Teams erforderlich.")
        return
    if len(set(team_namen)) != len(team_namen):
        st.error("Teamnamen müssen eindeutig sein.")
        return
    if not spielname:
        st.error("Bitte einen Spielnamen eingeben.")
        return

    try:
        game = GameService.neues_spiel(spielname, team_namen, max_jahre)
        st.session_state.game = game
        st.session_state.seite = "entscheidung"
        st.session_state.quartal_gestartet = False
        st.session_state.letztes_ergebnisse = None
        state_service.auto_save(game.zustand)
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))


# ── Laden ─────────────────────────────────────────────────────────────────────


def _render_laden() -> None:
    st.subheader("Gespeichertes Spiel laden")

    if not state_service.existiert():
        st.info("Kein gespeicherter Spielstand vorhanden.")
    else:
        _render_spielstand_vorschau()

    backups = state_service.liste_backups()
    if backups:
        st.divider()
        st.subheader("Backups")
        for bp in backups[:8]:
            st.caption(f"📁 {bp.name}")


def _render_spielstand_vorschau() -> None:
    try:
        zustand = state_service.lade()
    except Exception as exc:
        st.error(f"Spielstand konnte nicht gelesen werden: {exc}")
        return

    with st.container(border=True):
        st.markdown(f"### {zustand.name}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Jahr / Quartal", f"J{zustand.aktuelles_jahr} / Q{zustand.aktuelles_quartal}")
        col2.metric("Phase", zustand.phase.value.title())
        col3.metric("Teams", len(zustand.teams))
        st.caption("Teams: " + ", ".join(t.name for t in zustand.teams.values()))

    col_laden, col_loeschen = st.columns(2)

    with col_laden:
        if st.button("▶️ Spielstand laden", type="primary", use_container_width=True):
            game = GameService.lade(zustand)
            st.session_state.game = game
            st.session_state.letztes_ergebnisse = None
            # Phase → Seite ableiten
            if zustand.phase == SpielPhase.ABGESCHLOSSEN:
                st.session_state.seite = "dashboard"
            else:
                st.session_state.seite = "entscheidung"
            st.session_state.quartal_gestartet = False
            st.rerun()

    with col_loeschen:
        if st.button("🗑️ Spielstand löschen", use_container_width=True):
            state_service.loesche()
            st.success("Spielstand gelöscht.")
            st.rerun()
