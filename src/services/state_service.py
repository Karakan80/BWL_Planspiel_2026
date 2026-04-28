"""
services/state_service.py – Spielstand-Persistenz

Lädt und speichert SpielZustand als JSON.
Pydantic's model_dump_json / model_validate_json serialisieren alle
verschachtelten Modelle, Enums und optionalen Felder vollständig.

Standard-Pfade (relativ zu bwl-planspiel-digital/):
    Autosave:  data/game_state.json
    Backups:   data/game_state_{id8}_{timestamp}.json
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.services.game_service import SpielZustand

# Projekt-Root = bwl-planspiel-digital/ (zwei Ebenen über diesem Modul)
_ROOT: Path = Path(__file__).parent.parent.parent
DATA_DIR: Path = _ROOT / "data"
SPIELSTAND_PFAD: Path = DATA_DIR / "game_state.json"


def speichere(zustand: SpielZustand, pfad: Optional[Path] = None) -> None:
    """
    Speichert den vollständigen SpielZustand als formatiertes JSON.
    Erstellt ``data/`` falls das Verzeichnis noch nicht existiert.
    """
    ziel = pfad or SPIELSTAND_PFAD
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(zustand.model_dump_json(indent=2), encoding="utf-8")


def lade(pfad: Optional[Path] = None) -> SpielZustand:
    """
    Lädt SpielZustand aus JSON und rekonstruiert alle Pydantic-Modelle.

    Raises:
        FileNotFoundError: Kein Spielstand unter ``pfad``.
    """
    quelle = pfad or SPIELSTAND_PFAD
    if not quelle.exists():
        raise FileNotFoundError(f"Kein Spielstand gefunden: {quelle}")
    rohdaten = json.loads(quelle.read_text(encoding="utf-8"))
    _migriere_spielstand_rohdaten(rohdaten)
    return SpielZustand.model_validate(rohdaten)


def existiert(pfad: Optional[Path] = None) -> bool:
    """True wenn eine Spielstand-Datei vorhanden ist."""
    return (pfad or SPIELSTAND_PFAD).exists()


def loesche(pfad: Optional[Path] = None) -> None:
    """Löscht die Spielstand-Datei (kein Fehler wenn nicht vorhanden)."""
    ziel = pfad or SPIELSTAND_PFAD
    if ziel.exists():
        ziel.unlink()


def backup(zustand: SpielZustand, verzeichnis: Optional[Path] = None) -> Path:
    """
    Speichert eine benannte Sicherungskopie des Spielstands.

    Dateiname: ``game_state_{spiel_id[:8]}_{YYYYMMDD_HHMMSS}.json``

    Returns:
        Pfad der gespeicherten Backup-Datei.
    """
    zielverz = verzeichnis or DATA_DIR
    zielverz.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pfad = zielverz / f"game_state_{zustand.spiel_id[:8]}_{ts}.json"
    pfad.write_text(zustand.model_dump_json(indent=2), encoding="utf-8")
    return pfad


def auto_save(zustand: SpielZustand) -> None:
    """
    Sofort-Speichern nach jeder Spielaktion (überschreibt ``game_state.json``).

    Wird von der UI nach jedem ``GameService``-Aufruf aufgerufen, damit bei
    einem Browser-Absturz oder Neustart kein Spielfortschritt verloren geht.
    """
    speichere(zustand)


def liste_backups(verzeichnis: Optional[Path] = None) -> list[Path]:
    """
    Gibt alle Backup-Dateien im Verzeichnis zurück, neueste zuerst.
    """
    verz = verzeichnis or DATA_DIR
    if not verz.exists():
        return []
    dateien = sorted(
        verz.glob("game_state_????????_????????.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return dateien


def _migriere_spielstand_rohdaten(rohdaten: dict) -> None:
    """Ergänzt neue Felder in älteren JSON-Spielständen."""
    for team in rohdaten.get("teams", {}).values():
        if "fertigwaren_lose" not in team:
            fertigwaren_wert = team.get("aktiva", {}).get("fertigwaren", 0.0)
            team["fertigwaren_lose"] = max(0, int(round(fertigwaren_wert / 7.0)))
