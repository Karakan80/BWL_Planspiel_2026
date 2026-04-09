"""
services/scoring_service.py – Auswertung & Kennzahlen-Dashboard

Liefert aufbereitete Daten für:
  - Ranking-Tabelle (nach Eigenkapital)
  - GuV-Vergleich aller Teams
  - Zeitreihen für Plotly-Charts (Gewinnentwicklung, Marktanteile)
  - Kennzahlen-Tabelle
  - Cashflow-Waterfall-Daten

Alle Funktionen sind zustandslos (erhalten SpielZustand als Argument).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.models.round import Kennzahlen
from src.services.game_service import SpielZustand


# ─── Datenklassen ────────────────────────────────────────────────────────────


@dataclass
class TeamRangEintrag:
    """Einzelner Eintrag in der Rangliste."""

    rang: int
    team_id: str
    team_name: str
    eigenkapital: float           # Primäres Ranking-Kriterium
    nettogewinn_gesamt: float     # Summe aller Jahres-Nettogewinne
    letzter_ros: Optional[float]
    letzter_roe: Optional[float]
    letzter_roi: Optional[float]
    ist_insolvent: bool


# ─── Ranking ─────────────────────────────────────────────────────────────────


def erstelle_ranking(zustand: SpielZustand) -> list[TeamRangEintrag]:
    """
    Rangliste aller Teams nach Eigenkapital (höchstes EK = Rang 1).

    Sortierung:
        1. Solvente Teams vor insolventen.
        2. Eigenkapital absteigend.
        3. Team-ID alphabetisch als Tie-breaker.

    Returns:
        Liste von ``TeamRangEintrag``, Rang bereits zugewiesen.
    """
    eintraege: list[TeamRangEintrag] = []

    for tid, team in zustand.teams.items():
        netto_gesamt = sum(
            guv.nettogewinn
            for guv in zustand.jahres_guv.get(tid, {}).values()
        )
        kpis = _letzter_kpi(zustand, tid)

        eintraege.append(TeamRangEintrag(
            rang=0,
            team_id=tid,
            team_name=team.name,
            eigenkapital=team.passiva.eigenkapital,
            nettogewinn_gesamt=round(netto_gesamt, 4),
            letzter_ros=kpis.ros if kpis else None,
            letzter_roe=kpis.roe if kpis else None,
            letzter_roi=kpis.roi if kpis else None,
            ist_insolvent=team.ist_insolvent,
        ))

    eintraege.sort(key=lambda e: (e.ist_insolvent, -e.eigenkapital, e.team_id))
    for i, e in enumerate(eintraege, start=1):
        e.rang = i

    return eintraege


# ─── GuV-Vergleich ────────────────────────────────────────────────────────────


def get_guv_vergleich(zustand: SpielZustand, jahr: int) -> dict[str, dict[str, float]]:
    """
    Vergleichstabelle der Jahres-GuVs aller Teams für ein Jahr.

    Returns:
        ``{team_id: {"umsatz": ..., "ebit": ..., "nettogewinn": ..., ...}}``
        Nur Teams mit einem Jahresabschluss für ``jahr`` erscheinen.
    """
    jahr_key = str(jahr)
    ergebnis: dict[str, dict[str, float]] = {}

    for tid in zustand.teams:
        guv = zustand.jahres_guv.get(tid, {}).get(jahr_key)
        if guv is None:
            continue
        ergebnis[tid] = {
            "umsatz": guv.umsatz,
            "herstellungskosten": guv.herstellungskosten,
            "rohertrag": guv.rohertrag,
            "gemeinkosten": guv.gemeinkosten,
            "abschreibungen": guv.abschreibungen,
            "ebit": guv.ebit,
            "zinsen": guv.zinsen,
            "ebt": guv.ebt,
            "steuern": guv.steuern,
            "nettogewinn": guv.nettogewinn,
        }

    return ergebnis


# ─── Zeitreihen für Charts ────────────────────────────────────────────────────


def get_gewinnentwicklung(zustand: SpielZustand) -> dict[str, Any]:
    """
    Zeitreihendaten für den Linechart „Gewinnentwicklung aller Teams".

    Returns::

        {
            "jahre": [1, 2, 3],
            "serien": {
                "Team Alpha": [0.0, 2.1, 6.3],
                "Team Beta":  [0.0, 1.5, 4.8],
            }
        }
    """
    jahre = _abgeschlossene_jahre(zustand)
    serien: dict[str, list[float]] = {}

    for tid, team in zustand.teams.items():
        werte: list[float] = []
        for j in jahre:
            guv = zustand.jahres_guv.get(tid, {}).get(str(j))
            werte.append(round(guv.nettogewinn, 4) if guv else 0.0)
        serien[team.name] = werte

    return {"jahre": jahre, "serien": serien}


def get_marktanteile_verlauf(zustand: SpielZustand) -> dict[str, Any]:
    """
    Zeitreihendaten der Marktanteile je Team über alle gespielten Quartale.

    Returns::

        {
            "etiketten": ["J1Q1", "J1Q2", ..., "J3Q4"],
            "serien": {
                "Team Alpha": [0.33, 0.41, ...],
                ...
            }
        }
    """
    # Perioden in Spielreihenfolge ermitteln
    perioden: list[tuple[int, int]] = []
    for qe in sorted(zustand.quartal_ergebnisse, key=lambda q: (q.jahr, q.quartal)):
        p = (qe.jahr, qe.quartal)
        if p not in perioden:
            perioden.append(p)

    etiketten = [f"J{j}Q{q}" for j, q in perioden]
    serien: dict[str, list[float]] = {t.name: [] for t in zustand.teams.values()}

    for jahr, quartal in perioden:
        periode_map: dict[str, float] = {
            qe.team_id: qe.marktanteil
            for qe in zustand.quartal_ergebnisse
            if qe.jahr == jahr and qe.quartal == quartal
        }
        for tid, team in zustand.teams.items():
            serien[team.name].append(round(periode_map.get(tid, 0.0), 4))

    return {"etiketten": etiketten, "serien": serien}


# ─── Tabellen ─────────────────────────────────────────────────────────────────


def get_kennzahlen_tabelle(zustand: SpielZustand, jahr: int) -> list[dict[str, Any]]:
    """
    Kennzahlen-Tabelle aller Teams für ein Jahr (geeignet für ``st.dataframe``).

    Returns:
        Liste von Zeilendicts, eine Zeile pro Team, nach ROS absteigend sortiert.
    """
    jahr_key = str(jahr)
    zeilen: list[dict[str, Any]] = []

    for tid, team in zustand.teams.items():
        kpis = zustand.jahres_kennzahlen.get(tid, {}).get(jahr_key)
        zeilen.append({
            "Team": team.name,
            "ROS (%)": kpis.ros if kpis else None,
            "ROE (%)": kpis.roe if kpis else None,
            "ROI (%)": kpis.roi if kpis else None,
            "KU": kpis.ku if kpis else None,
            "BEP (Lose)": kpis.bep if kpis else None,
            "Liq. I": kpis.liquiditaet_1 if kpis else None,
            "Liq. II": kpis.liquiditaet_2 if kpis else None,
        })

    zeilen.sort(key=lambda z: (z["ROS (%)"] is None, -(z["ROS (%)"] or 0.0)))
    return zeilen


def get_bilanzvergleich(zustand: SpielZustand) -> list[dict[str, Any]]:
    """
    Aktueller Bilanzschnappschuss aller Teams (für Vergleichstabelle).

    Returns:
        Eine Zeile pro Team mit wesentlichen Bilanzpositionen (Mio. EUR).
    """
    zeilen: list[dict[str, Any]] = []
    for tid, team in zustand.teams.items():
        a = team.aktiva
        p = team.passiva
        zeilen.append({
            "Team": team.name,
            "Kasse": a.kasse,
            "Forderungen": a.forderungen,
            "Fertigwaren": a.fertigwaren,
            "Anlagevermögen": a.grundstuecke + a.gebaeude + a.maschinen + a.bga,
            "Bilanzsumme": a.summe,
            "Eigenkapital": p.eigenkapital,
            "Fremdkapital": p.langfristiges_fk,
            "Insolvent": team.ist_insolvent,
        })
    zeilen.sort(key=lambda z: (z["Insolvent"], -z["Eigenkapital"]))
    return zeilen


# ─── Cashflow-Waterfall ───────────────────────────────────────────────────────


def get_cashflow_waterfall(
    zustand: SpielZustand,
    team_id: str,
    jahr: int,
    quartal: int,
) -> dict[str, Any]:
    """
    Cashflow-Waterfall-Daten für ein einzelnes Quartal (Plotly Waterfall-Chart).

    Jede cashwirksame Position erscheint als eigener Balken.
    Positionen mit Wert 0 werden ausgeblendet.

    Returns::

        {
            "positionen": ["Forderungen-Einzug", "Material", ...],
            "werte":      [25.0, -6.0, ...],          # positiv = Einzahlung
            "typen":      ["relative", "relative", ...]
        }
    """
    qe = next(
        (q for q in zustand.quartal_ergebnisse
         if q.team_id == team_id and q.jahr == jahr and q.quartal == quartal),
        None,
    )
    if qe is None:
        return {"positionen": [], "werte": [], "typen": []}

    cf = qe.cashflow
    roh: list[tuple[str, float]] = [
        ("Forderungen (Vorquartal)", cf.einzahlungen_forderungen),
        ("Kredit",                   cf.einzahlungen_kredit),
        ("Material",                -cf.auszahlungen_material),
        ("Fertigung Stufe 1",       -cf.auszahlungen_fertigung_stufe1),
        ("Montage Stufe 2",         -cf.auszahlungen_montage_stufe2),
        ("Gemeinkosten",            -cf.auszahlungen_gemeinkosten),
        ("Marketing",               -cf.auszahlungen_marketing),
        ("Investition",             -cf.auszahlungen_investition),
        ("Zinsen (Jahresabschl.)",  -cf.auszahlungen_zinsen),
        ("Steuern (Jahresabschl.)", -cf.auszahlungen_steuern),
        ("Tilgung",                 -cf.auszahlungen_tilgung),
    ]
    # Nullpositionen herausfiltern
    gefiltert = [(pos, w) for pos, w in roh if w != 0.0]
    if not gefiltert:
        return {"positionen": [], "werte": [], "typen": []}

    positionen, werte = zip(*gefiltert)
    return {
        "positionen": list(positionen),
        "werte": [round(w, 4) for w in werte],
        "typen": ["relative"] * len(werte),
    }


# ─── Private Hilfsfunktionen ─────────────────────────────────────────────────


def _letzter_kpi(zustand: SpielZustand, team_id: str) -> Optional[Kennzahlen]:
    """Kennzahlen des letzten abgeschlossenen Jahres für ein Team."""
    kpis_dict = zustand.jahres_kennzahlen.get(team_id, {})
    if not kpis_dict:
        return None
    letztes = max(kpis_dict.keys(), key=int)
    return kpis_dict[letztes]


def _abgeschlossene_jahre(zustand: SpielZustand) -> list[int]:
    """Aufsteigend sortierte Liste aller Jahre mit mindestens einem Jahresabschluss."""
    jahre: set[int] = set()
    for jg in zustand.jahres_guv.values():
        jahre.update(int(j) for j in jg.keys())
    return sorted(jahre)
