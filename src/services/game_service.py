"""
services/game_service.py – Zentrale Spielsteuerung

SpielZustand: vollständig serialisierbarer Spielzustand (Pydantic-Model).
GameService:  koordiniert alle Engine-Module und verwaltet den Spielfluss.

Multiplayer-Ablauf je Quartal:
    1. game.starte_quartal()            → Ereigniskarte ziehen, Phase = ENTSCHEIDUNG
    2. game.reiche_entscheidung_ein()   → je Team, beliebige Reihenfolge
    3. game.alle_entscheidungen_eingereicht() → guard für den Game-Master
    4. game.verarbeite_quartal()        → alle Engine-Schritte, Phase → ENTSCHEIDUNG|ABGESCHLOSSEN
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.engine.demand import verteile_nachfrage
from src.engine.events import beschreibe_effekte, wende_an, ziehe_ereignis
from src.engine.finance import buche_jahresabschluss
from src.engine.production import verarbeite_quartal as _engine_verarbeite_quartal
from src.models.market import Ereignis, EreignisTyp, MarktZustand
from src.models.round import GuV, Kennzahlen, QuartalErgebnis, TeamEntscheidung
from src.models.team import Team


class SpielPhase(str, Enum):
    EINRICHTUNG = "einrichtung"      # Konfiguration noch nicht abgeschlossen
    ENTSCHEIDUNG = "entscheidung"    # Teams geben Entscheidungen ein
    AUSWERTUNG = "auswertung"        # Quartal wird gerade verarbeitet
    ABGESCHLOSSEN = "abgeschlossen"  # Alle Jahre gespielt


class SpielZustand(BaseModel):
    """Vollständiger, JSON-serialisierbarer Spielstand."""

    spiel_id: str
    name: str
    erstellt_am: str  # ISO-8601

    teams: dict[str, Team]          # team_id → Team
    aktuelles_jahr: int = 1
    aktuelles_quartal: int = 1
    max_jahre: int = 3
    phase: SpielPhase = SpielPhase.EINRICHTUNG
    quartal_gestartet: bool = False

    # Zinssatz: startet bei 10 %, wird durch ZINSERHOEHUNG-Ereignis dauerhaft erhöht
    basis_zinssatz: float = 0.10

    # Offene Entscheidungen des laufenden Quartals (team_id → Entscheidung)
    aktuelle_entscheidungen: dict[str, TeamEntscheidung] = Field(default_factory=dict)

    # FK-Stand zu Jahresbeginn (vor allen Tilgungen) – für korrekte Zinsberechnung
    fk_jahresbeginn: dict[str, float] = Field(default_factory=dict)

    # Forderungen aus dem Vorquartal → Schritt 9 (Einzug)
    forderungen_vorquartal: dict[str, float] = Field(default_factory=dict)

    # Vollständige Ergebnis- und Abschlusshistorie
    quartal_ergebnisse: list[QuartalErgebnis] = Field(default_factory=list)
    jahres_guv: dict[str, dict[str, GuV]] = Field(default_factory=dict)        # [team_id][str(jahr)]
    jahres_kennzahlen: dict[str, dict[str, Kennzahlen]] = Field(default_factory=dict)

    # Ereignis-Protokoll
    letztes_ereignis: Optional[Ereignis] = None
    ereignis_historie: list[Ereignis] = Field(default_factory=list)


class GameService:
    """
    Spielsteuerung: bindet alle Engine-Module an einen gemeinsamen SpielZustand.

    Jede schreibende Methode mutiert ``self.zustand`` in-place.
    Die aufrufende UI-Schicht ist für Persistenz (state_service.speichere) verantwortlich.
    """

    def __init__(self, zustand: SpielZustand) -> None:
        self._z = zustand

    # ── Factory-Methoden ────────────────────────────────────────────────────

    @classmethod
    def neues_spiel(
        cls,
        name: str,
        team_namen: list[str],
        max_jahre: int = 3,
    ) -> "GameService":
        """
        Erstellt ein neues Spiel mit 2–6 Teams, jedes mit Original-Startbilanz.

        Args:
            name:        Anzeigename des Spiels.
            team_namen:  Liste eindeutiger Teamnamen (2–6 Einträge).
            max_jahre:   Spiellänge in Jahren (Standard: 3).
        """
        if not (2 <= len(team_namen) <= 6):
            raise ValueError(f"Erwartet 2–6 Teams, erhalten: {len(team_namen)}.")
        if len(set(team_namen)) != len(team_namen):
            raise ValueError("Teamnamen müssen eindeutig sein.")

        teams: dict[str, Team] = {}
        for tname in team_namen:
            tid = tname.strip().lower().replace(" ", "_")
            teams[tid] = Team(id=tid, name=tname.strip())

        zustand = SpielZustand(
            spiel_id=str(uuid.uuid4()),
            name=name,
            erstellt_am=datetime.now().isoformat(),
            teams=teams,
            max_jahre=max_jahre,
            phase=SpielPhase.ENTSCHEIDUNG,
            # Startbilanz-Forderungen für den ersten Schritt-9-Einzug
            forderungen_vorquartal={tid: t.aktiva.forderungen for tid, t in teams.items()},
            # FK-Stand Jahr 0 für das erste Jahresabschluss-Zinsberechnung
            fk_jahresbeginn={tid: t.passiva.langfristiges_fk for tid, t in teams.items()},
        )
        return cls(zustand)

    @classmethod
    def lade(cls, zustand: SpielZustand) -> "GameService":
        """Erstellt GameService aus einem deserialisierten SpielZustand."""
        return cls(zustand)

    # ── Eigenschaften ────────────────────────────────────────────────────────

    @property
    def zustand(self) -> SpielZustand:
        return self._z

    @property
    def aktive_teams(self) -> list[Team]:
        """Alle nicht-insolventen Teams."""
        return [t for t in self._z.teams.values() if not t.ist_insolvent]

    @property
    def ist_beendet(self) -> bool:
        return self._z.phase == SpielPhase.ABGESCHLOSSEN

    # ── Quartal-Lebenszyklus ─────────────────────────────────────────────────

    def starte_quartal(self, ereignis_seed: Optional[int] = None) -> Ereignis:
        """
        Bereitet ein neues Quartal vor.

        Aktionen:
        - Q1: FK aller Teams für Jahresabschluss-Zinsberechnung sichern.
        - Ereigniskarte ziehen (optional mit fixem Seed für Tests/Replay).
        - ZINSERHOEHUNG-Ereignis: ``basis_zinssatz`` dauerhaft erhöhen.
        - Phase → ENTSCHEIDUNG, offene Entscheidungen löschen.

        Returns:
            Gezogene Ereigniskarte (zur Anzeige an alle Teams).
        """
        z = self._z
        if z.phase == SpielPhase.ABGESCHLOSSEN:
            raise RuntimeError("Das Spiel ist bereits abgeschlossen.")
        if z.quartal_gestartet and z.letztes_ereignis is not None:
            return z.letztes_ereignis

        self._aktualisiere_basis_gemeinkosten()

        # Jahresbeginn: FK-Stand für Zinsberechnung einfrieren
        if z.aktuelles_quartal == 1:
            z.fk_jahresbeginn = {
                tid: t.passiva.langfristiges_fk
                for tid, t in z.teams.items()
                if not t.ist_insolvent
            }

        ereignis = ziehe_ereignis(seed=ereignis_seed)

        # Zinserhöhung wirkt dauerhaft auf alle zukünftigen Jahresabschlüsse
        if ereignis.typ == EreignisTyp.ZINSERHOEHUNG:
            z.basis_zinssatz = round(z.basis_zinssatz + ereignis.zinssatz_delta, 4)

        z.letztes_ereignis = ereignis
        z.ereignis_historie.append(ereignis)
        z.aktuelle_entscheidungen = {}
        z.phase = SpielPhase.ENTSCHEIDUNG
        z.quartal_gestartet = True
        return ereignis

    def reiche_entscheidung_ein(self, entscheidung: TeamEntscheidung) -> None:
        """
        Nimmt die Entscheidung eines Teams für das aktuelle Quartal entgegen.

        Raises:
            ValueError: Unbekanntes Team, Insolvenz, falsche Phase oder Periode.
        """
        z = self._z
        tid = entscheidung.team_id

        if tid not in z.teams:
            raise ValueError(f"Unbekanntes Team: {tid!r}")
        if z.teams[tid].ist_insolvent:
            raise ValueError(f"Team {tid!r} ist insolvent.")
        if z.phase != SpielPhase.ENTSCHEIDUNG:
            raise ValueError("Entscheidungen nur in der ENTSCHEIDUNG-Phase möglich.")
        if entscheidung.jahr != z.aktuelles_jahr or entscheidung.quartal != z.aktuelles_quartal:
            raise ValueError(
                f"Entscheidung für {entscheidung.jahr}/Q{entscheidung.quartal} "
                f"≠ aktuell {z.aktuelles_jahr}/Q{z.aktuelles_quartal}."
            )

        z.aktuelle_entscheidungen[tid] = entscheidung

    def alle_entscheidungen_eingereicht(self) -> bool:
        """True wenn alle aktiven Teams eine Entscheidung abgegeben haben."""
        aktive = {tid for tid, t in self._z.teams.items() if not t.ist_insolvent}
        return aktive == set(self._z.aktuelle_entscheidungen.keys())

    def verarbeite_quartal(self) -> dict[str, QuartalErgebnis]:
        """
        Verarbeitet das laufende Quartal für alle Teams.

        Ablauf:
            1. MarktZustand erzeugen + letztes Ereignis anwenden.
            2. Nachfrageverteilung berechnen (alle Teams simultan → kein Timing-Vorteil).
            3. Produktion (10 Quartalschritte) je Team.
            4. Forderungen für das nächste Quartal vormerken.
            5. Bei Q4: Jahresabschluss (Zinsen, AfA, Steuern, Kennzahlen) für alle Teams.
            6. Spielzähler vorrücken.

        Returns:
            ``{team_id: QuartalErgebnis}``

        Raises:
            RuntimeError: Nicht alle Entscheidungen liegen vor.
        """
        z = self._z

        if not self.alle_entscheidungen_eingereicht():
            fehlende = (
                {tid for tid, t in z.teams.items() if not t.ist_insolvent}
                - set(z.aktuelle_entscheidungen.keys())
            )
            raise RuntimeError(f"Fehlende Entscheidungen von: {fehlende}")

        z.phase = SpielPhase.AUSWERTUNG

        # 1. Markt aufbauen
        markt = MarktZustand(
            jahr=z.aktuelles_jahr,
            quartal=z.aktuelles_quartal,
            basis_zinssatz=z.basis_zinssatz,
            aktueller_zinssatz=z.basis_zinssatz,
        )
        if z.letztes_ereignis:
            wende_an(z.letztes_ereignis, markt)

        # 2. Nachfrageverteilung (alle Teams gleichzeitig)
        aktive = [t for t in z.teams.values() if not t.ist_insolvent]
        nachfrage = verteile_nachfrage(
            markt,
            list(z.aktuelle_entscheidungen.values()),
            aktive,
        )

        # 3. Produktion je Team
        ergebnisse: dict[str, QuartalErgebnis] = {}
        for tid, entscheidung in z.aktuelle_entscheidungen.items():
            qe = _engine_verarbeite_quartal(
                team=z.teams[tid],
                entscheidung=entscheidung,
                markt=markt,
                verkaufte_lose=nachfrage.get(tid, 0),
                forderungen_vorquartal=z.forderungen_vorquartal.get(tid, 0.0),
                fk_jahresbeginn=z.fk_jahresbeginn.get(tid, 0.0),
                zinssatz=z.basis_zinssatz,
            )
            ergebnisse[tid] = qe
            z.quartal_ergebnisse.append(qe)

        # 4. Forderungen für nächstes Quartal sichern
        z.forderungen_vorquartal = {
            tid: qe.forderungen_nach_quartal for tid, qe in ergebnisse.items()
        }

        # 5. Jahresabschluss bei Q4
        if z.aktuelles_quartal == 4:
            self._buche_jahresabschluss_alle()

        # Entscheidungen gehören nur zum gerade ausgewerteten Quartal.
        z.aktuelle_entscheidungen = {}

        # 6. Spielzähler vorrücken
        self._vorruecken()
        z.quartal_gestartet = False
        return ergebnisse

    # ── Abfrage-Methoden ────────────────────────────────────────────────────

    def get_quartal_ergebnisse(self, jahr: int, quartal: int) -> dict[str, QuartalErgebnis]:
        """Alle Teamergebnisse eines bestimmten Quartals."""
        return {
            qe.team_id: qe
            for qe in self._z.quartal_ergebnisse
            if qe.jahr == jahr and qe.quartal == quartal
        }

    def get_jahres_ergebnisse(self, team_id: str, jahr: int) -> list[QuartalErgebnis]:
        """4 QuartalErgebnisse eines Teams für ein Jahr, sortiert Q1→Q4."""
        return sorted(
            (qe for qe in self._z.quartal_ergebnisse
             if qe.team_id == team_id and qe.jahr == jahr),
            key=lambda qe: qe.quartal,
        )

    def get_ereignis_beschreibung(self) -> str:
        """Kurzbeschreibung des zuletzt gezogenen Ereignisses für die UI."""
        e = self._z.letztes_ereignis
        if e is None:
            return "Kein Ereignis gezogen."
        return f"{e.titel} – {', '.join(beschreibe_effekte(e))}"

    # ── Private Hilfsmethoden ────────────────────────────────────────────────

    def _buche_jahresabschluss_alle(self) -> None:
        """
        Führt den Jahresabschluss für alle aktiven Teams durch (wird bei Q4 aufgerufen).

        Aktualisiert:
        - Team-Bilanz (Kasse, Buchwerte, Gewinnrücklage)
        - jahres_guv / jahres_kennzahlen in SpielZustand
        - Q4-QuartalErgebnis.kennzahlen + Cashflow (Zinsen, Steuern)
        """
        z = self._z

        for tid, team in z.teams.items():
            if team.ist_insolvent:
                continue

            jahres_qe = self.get_jahres_ergebnisse(tid, z.aktuelles_jahr)
            fk_start = z.fk_jahresbeginn.get(tid, team.passiva.langfristiges_fk)

            jahres_guv_obj, kpis = buche_jahresabschluss(
                team=team,
                quartal_ergebnisse=jahres_qe,
                fk_jahresbeginn=fk_start,
                zinssatz=z.basis_zinssatz,
            )

            # Jahresabschluss in Historien ablegen
            jahr_key = str(z.aktuelles_jahr)
            z.jahres_guv.setdefault(tid, {})[jahr_key] = jahres_guv_obj
            z.jahres_kennzahlen.setdefault(tid, {})[jahr_key] = kpis

            # Kennzahlen + Jahresabschluss-Cashflow in Q4-Ergebnis einschreiben
            if jahres_qe:
                q4 = jahres_qe[-1]
                q4.kennzahlen = kpis
                q4.cashflow.auszahlungen_zinsen = jahres_guv_obj.zinsen
                q4.cashflow.auszahlungen_steuern = jahres_guv_obj.steuern
                q4.kasse_nach_quartal = team.aktiva.kasse
                q4.forderungen_nach_quartal = team.aktiva.forderungen
                q4.eigenkapital_nach_quartal = team.passiva.eigenkapital
                q4.fremdkapital_nach_quartal = team.passiva.langfristiges_fk

    def _vorruecken(self) -> None:
        """Rückt Jahres-/Quartalszähler vor und setzt die neue Phase."""
        z = self._z
        if z.aktuelles_quartal < 4:
            z.aktuelles_quartal += 1
            z.phase = SpielPhase.ENTSCHEIDUNG
        elif z.aktuelles_jahr < z.max_jahre:
            z.aktuelles_jahr += 1
            z.aktuelles_quartal = 1
            z.phase = SpielPhase.ENTSCHEIDUNG
        else:
            z.phase = SpielPhase.ABGESCHLOSSEN
        self._aktualisiere_basis_gemeinkosten()

    def _aktualisiere_basis_gemeinkosten(self) -> None:
        """Setzt die regulären Gemeinkosten nach Jahr: J1 = 6 Mio./Q, ab J2 = 5 Mio./Q."""
        basis = 6.0 if self._z.aktuelles_jahr == 1 else 5.0
        for team in self._z.teams.values():
            team.gemeinkosten_pro_quartal = basis
