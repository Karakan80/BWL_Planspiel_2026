"""
app.py – Streamlit-Einstiegspunkt für FACTORY 2.0

Starten:
    cd bwl-planspiel-digital
    streamlit run src/app.py

Session-State-Schlüssel:
    game              GameService | None  – aktives Spiel
    seite             str                 – aktuell angezeigte Seite
    quartal_gestartet bool                – ob starte_quartal() schon gerufen wurde
    letztes_ergebnisse dict | None        – Ergebnisse des letzten verarbeite_quartal()
"""
from __future__ import annotations

import streamlit as st

from config import APP_NAME, APP_VERSION
from services import state_service
from services.game_service import GameService, SpielPhase
from ui.pages import dashboard, decision, results, setup


# ── Session-State initialisieren ──────────────────────────────────────────────


def _init_session() -> None:
    defaults = {
        "game": None,
        "seite": "setup",
        "quartal_gestartet": False,
        "letztes_ergebnisse": None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def _auto_lade_spielstand() -> None:
    """Lädt einen vorhandenen Spielstand beim ersten Aufruf der Session."""
    if st.session_state.game is not None:
        return  # bereits geladen
    if not state_service.existiert():
        return

    try:
        zustand = state_service.lade()
        st.session_state.game = GameService.lade(zustand)
        # Startseite abhängig von der gespeicherten Phase
        if zustand.phase == SpielPhase.ABGESCHLOSSEN:
            st.session_state.seite = "dashboard"
        else:
            st.session_state.seite = "entscheidung"
    except Exception:
        pass  # Beschädigte Datei → Setup anzeigen


# ── Sidebar ───────────────────────────────────────────────────────────────────


def _render_sidebar() -> None:
    with st.sidebar:
        st.title(f"🏭 {APP_NAME}")
        st.caption(f"Version {APP_VERSION}")
        st.divider()

        # Einrichtung immer erreichbar
        if st.button("⚙️ Einrichtung", use_container_width=True):
            st.session_state.seite = "setup"
            st.rerun()

        game: GameService | None = st.session_state.game
        if game is None:
            return

        z = game.zustand
        st.divider()
        st.markdown(f"**{z.name}**")
        st.caption(
            f"J{z.aktuelles_jahr} / Q{z.aktuelles_quartal}  ·  "
            f"{z.phase.value.title()}"
        )

        # Entscheidung (nur wenn ENTSCHEIDUNG-Phase)
        in_entscheidung = z.phase == SpielPhase.ENTSCHEIDUNG
        if st.button(
            "📝 Entscheidung",
            use_container_width=True,
            disabled=not in_entscheidung,
        ):
            st.session_state.seite = "entscheidung"
            st.rerun()

        # Ergebnisse (nur wenn Ergebnisse vorliegen)
        hat_ergebnisse = st.session_state.letztes_ergebnisse is not None
        if st.button(
            "📊 Ergebnisse",
            use_container_width=True,
            disabled=not hat_ergebnisse,
        ):
            st.session_state.seite = "ergebnisse"
            st.rerun()

        # Dashboard (nur wenn mindestens ein Quartal gespielt)
        hat_daten = bool(z.quartal_ergebnisse)
        if st.button(
            "📈 Dashboard",
            use_container_width=True,
            disabled=not hat_daten,
        ):
            st.session_state.seite = "dashboard"
            st.rerun()

        st.divider()

        # Team-Übersicht
        st.caption("Teams")
        for team in z.teams.values():
            icon = "💀" if team.ist_insolvent else "✅"
            st.caption(
                f"{icon} {team.name}  "
                f"EK: {team.passiva.eigenkapital:.1f}"
            )

        # Backup-Button
        st.divider()
        if st.button("💾 Backup speichern", use_container_width=True):
            bp = state_service.backup(z)
            st.success(f"Backup: {bp.name}")


# ── Haupt-Routing ─────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _init_session()
    _auto_lade_spielstand()
    _render_sidebar()

    seite: str = st.session_state.seite
    game: GameService | None = st.session_state.game

    if seite == "setup" or game is None:
        setup.render()
    elif seite == "entscheidung":
        decision.render(game)
    elif seite == "ergebnisse":
        results.render(game)
    elif seite == "dashboard":
        dashboard.render(game)
    else:
        setup.render()


if __name__ == "__main__":
    main()
