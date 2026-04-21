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

from src.models.round import (
    InvestitionsTyp,
    MASCHINEN_PREISE,
    MaschinenVariante,
    MaterialEinkaufsTyp,
    TeamEntscheidung,
)
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
    if not z.quartal_gestartet:
        st.info(
            "Klicke auf **Quartal starten**, um die Ereigniskarte zu ziehen "
            "und die Entscheidungsphase zu öffnen."
        )
        if st.button("🎲 Quartal starten", type="primary", use_container_width=True):
            game.starte_quartal()
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
    if ent.gemeinkosten_delta != 0:
        details.append(f"GK-Anpassung: {ent.gemeinkosten_delta:+.1f}")
    if ent.kredit_aufnahme > 0:
        details.append(f"Kredit: +{ent.kredit_aufnahme:.1f}")
    if ent.tilgung > 0:
        details.append(f"Tilgung: −{ent.tilgung:.1f}")
    if ent.investition_typ:
        if ent.investition_typ == InvestitionsTyp.MASCHINE:
            details.append(
                f"Invest.: {ent.maschinen_beschreibung} ({ent.investition_betrag:.1f} Mio.€)"
            )
        else:
            details.append(f"Invest.: {ent.investition_typ.value} ({ent.investition_betrag:.1f} Mio.€)")
    st.caption(" | ".join(details))


# ── Entscheidungsformular ─────────────────────────────────────────────────────


def _render_team_form(game: GameService, team: Team) -> None:
    z = game.zustand
    tid = team.id
    zins_pro_10_mio = 10.0 * z.basis_zinssatz
    zinssatz_pct = z.basis_zinssatz * 100

    with st.container():
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
                help=(
                    "Umsatz = Preis x verkaufte Lose. Über 10 Mio. sinkt die Gesamtnachfrage stark; "
                    "30 Mio. funktioniert nur bei sehr wenig Konkurrenz/Nachfrage."
                ),
                key=f"preis_{tid}",
            )
            prod_menge = st.number_input(
                "Produktionsmenge (Lose)",
                min_value=0,
                max_value=team.kapazitaet_lose_pro_quartal,
                value=min(2, team.kapazitaet_lose_pro_quartal),
                step=1,
                help=(
                    "1 Los kostet ca. 7 Mio. Herstellung: 3 Material + 3 Fertigung "
                    "+ 1 Montage. Verkauf bringt erst Geld, wenn Nachfrage da ist."
                ),
                key=f"prod_{tid}",
            )
            marketing = st.number_input(
                "Marketingbudget (Mio. €)",
                min_value=0.0,
                max_value=20.0,
                value=1.0,
                step=0.5,
                help=(
                    "Kostet sofort. 1 Mio. bringt ca. +4 % Score, 5 Mio. ca. +18 % Score."
                ),
                key=f"mkt_{tid}",
            )
            einkauf_label = st.selectbox(
                "Materialeinkauf",
                options=["Spot (Marktpreis)", "Jahresvertrag (fix −10 %)"],
                help=(
                    "Spot = aktueller Marktpreis, Basis 3,0 Mio./Los. Jahresvertrag = fix "
                    "2,7 Mio./Los. Bei Wirtschaftskrise ist Spot z.B. 2,55."
                ),
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

            gemeinkosten_delta = st.number_input(
                "Service-/F&E-Zusatzbudget (Mio. €)",
                min_value=0.0,
                max_value=5.0,
                value=0.0,
                step=0.5,
                help=(
                    f"Basis aktuell {team.gemeinkosten_pro_quartal:.1f} Mio./Q. "
                    "+1 kostet 1 Mio. und gibt +3 % Score."
                ),
                key=f"gkdelta_{tid}",
            )

            kredit = st.number_input(
                "Kredit aufnehmen (Mio. €)",
                min_value=0.0,
                max_value=200.0,
                value=0.0,
                step=1.0,
                help=(
                    f"+10 Mio. Kredit = +10 Mio. Kasse und +10 Mio. FK. "
                    f"Bei {zinssatz_pct:.0f} % Zins kostet das ab nächstem Jahr "
                    f"ca. {zins_pro_10_mio:.1f} Mio./Jahr."
                ),
                key=f"kredit_{tid}",
            )
            max_tilgung = max(0.0, float(team.passiva.langfristiges_fk))
            tilgung = st.number_input(
                "Tilgung (Mio. €)",
                min_value=0.0,
                max_value=max_tilgung,
                value=0.0,
                step=1.0,
                help=(
                    f"10 Mio. Tilgung = -10 Mio. Kasse und -10 Mio. FK. "
                    f"Spart ab nächstem Jahr bei {zinssatz_pct:.0f} % ca. "
                    f"{zins_pro_10_mio:.1f} Mio. Zins/Jahr."
                ),
                key=f"tilgung_{tid}",
            )

            st.markdown("**Investition**")
            inv_opt = st.selectbox(
                "Investitionstyp",
                options=[
                    "Keine",
                    "Maschine auswählen",
                    "Automatisierung",
                    "Qualitätsinvestition",
                ],
                help=(
                    "Wirkung ab Folgequartal. Maschine: 20/30/40 Mio. Auto: 1 Mio. "
                    "= -2 % Fertigung/Montage. Qualität: 5 Mio. = Faktor 1,5."
                ),
                key=f"invtyp_{tid}",
            )

            inv_typ: Optional[InvestitionsTyp] = None
            inv_betrag = 0.0
            maschinen_variante = MaschinenVariante.STANDARD

            maschinen_optionen = {
                "Standardmaschine - 20 Mio. € - +1 Kapazität": MaschinenVariante.STANDARD,
                "Effizienzmaschine - 30 Mio. € - +1 Kapazität, -10 % Fertigung/Montage":
                    MaschinenVariante.EFFIZIENZ,
                "Hochleistungsanlage - 40 Mio. € - +2 Kapazität": MaschinenVariante.HOCHLEISTUNG,
            }

            if inv_opt == "Maschine auswählen":
                inv_typ = InvestitionsTyp.MASCHINE
                maschine_label = st.selectbox(
                    "Maschinenmodell",
                    options=list(maschinen_optionen.keys()),
                    help=(
                        "20 Mio. = +1 Los/Q. 30 Mio. = +1 Los/Q und spart ca. "
                        "0,4 Mio./Los. 40 Mio. = +2 Lose/Q. Wirkung ab Folgequartal."
                    ),
                    key=f"maschine_{tid}",
                )
                maschinen_variante = maschinen_optionen[maschine_label]
                inv_betrag = MASCHINEN_PREISE[maschinen_variante]
                st.caption(f"Preis: {inv_betrag:.1f} Mio. €")
            elif inv_opt in ("Automatisierung", "Qualitätsinvestition"):
                inv_typ = {
                    "Automatisierung": InvestitionsTyp.AUTOMATISIERUNG,
                    "Qualitätsinvestition": InvestitionsTyp.QUALITAET,
                }[inv_opt]
                investition_help = (
                    "1 Mio. = -2 % auf Fertigung/Montage; max. -30 %. "
                    "5 Mio. spart ab Folgequartal ca. 0,4 Mio./Los."
                    if inv_opt == "Automatisierung"
                    else "5 Mio. = Faktor 1,5; 10 Mio. = Faktor 2,0 im Score. "
                    "Ab Folgequartal, ab 5 Mio. Schutz beim Qualitätsskandal."
                )
                inv_betrag = st.number_input(
                    "Investitionsbetrag (Mio. €)",
                    min_value=0.1,
                    max_value=100.0,
                    value=5.0,
                    step=0.5,
                    help=investition_help,
                    key=f"invbet_{tid}",
                )

        # ── Team-Info-Zeile ────────────────────────────────────────────────
        st.caption(
            f"Kasse: {team.aktiva.kasse:.2f} Mio. €  |  "
            f"FK: {team.passiva.langfristiges_fk:.2f} Mio. €  |  "
            f"Kapazität: {team.kapazitaet_lose_pro_quartal} Lose/Q"
        )

        submitted = st.button(
            "✅ Entscheidung einreichen",
            type="primary",
            use_container_width=True,
            help="Speichert die Entscheidung dieses Teams für das aktuelle Quartal.",
            key=f"submit_{tid}_{z.aktuelles_jahr}_{z.aktuelles_quartal}",
        )

    if submitted:
        _reiche_ein(game, tid, z, verkaufspreis, int(prod_menge),
                    marketing, gemeinkosten_delta, einkauf, kredit, tilgung,
                    inv_typ, inv_betrag, maschinen_variante)


def _reiche_ein(
    game: GameService,
    tid: str,
    z,
    verkaufspreis: float,
    prod_menge: int,
    marketing: float,
    gemeinkosten_delta: float,
    einkauf: MaterialEinkaufsTyp,
    kredit: float,
    tilgung: float,
    inv_typ: Optional[InvestitionsTyp],
    inv_betrag: float,
    maschinen_variante: MaschinenVariante,
) -> None:
    try:
        entscheidung = TeamEntscheidung(
            team_id=tid,
            jahr=z.aktuelles_jahr,
            quartal=z.aktuelles_quartal,
            verkaufspreis=verkaufspreis,
            produktionsmenge_lose=prod_menge,
            marketingbudget=marketing,
            gemeinkosten_delta=gemeinkosten_delta,
            material_einkauf=einkauf,
            investition_typ=inv_typ,
            investition_betrag=inv_betrag,
            maschinen_variante=maschinen_variante,
            kredit_aufnahme=kredit,
            tilgung=tilgung,
        )
        game.reiche_entscheidung_ein(entscheidung)
        state_service.auto_save(game.zustand)
        st.rerun()
    except (ValueError, Exception) as exc:
        st.error(f"Fehler beim Einreichen: {exc}")
