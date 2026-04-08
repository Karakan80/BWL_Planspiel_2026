from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EreignisTyp(str, Enum):
    """Ereigniskarten (eine pro Runde, zufällig gezogen)."""

    ROHSTOFFKRISE = "rohstoffkrise"          # Materialpreis +25%
    NACHFRAGEBOOM = "nachfrageboom"          # Marktvolumen +30%
    WIRTSCHAFTSKRISE = "wirtschaftskrise"    # Nachfrage -25%
    TECHNOLOGIESPRUNG = "technologiesprung"  # Investitionskosten -20%
    STREIK = "streik"                        # Produktionskosten +15%
    NEUE_KONKURRENZ = "neue_konkurrenz"      # Marktvolumen -10%
    EXPORTCHANCE = "exportchance"            # Marktvolumen +20%
    ZINSERHOEHUNG = "zinserhoehung"          # Zinssatz +2 Prozentpunkte
    QUALITAETSSKANDAL = "qualitaetsskandal"  # Score aller Teams -20% (außer Qualitätsinvestoren)
    RUHIGE_RUNDE = "ruhige_runde"            # Kein Effekt


class Ereignis(BaseModel):
    """Ereigniskarte mit konkreten Multiplikatoren.

    Multiplikatoren werden auf Basiswerte des MarktZustand angewendet.
    Ein Faktor von 1.0 bedeutet keine Änderung.
    """

    typ: EreignisTyp
    titel: str
    beschreibung: str

    # Effekte (multiplikativ auf Basiswerte)
    materialpreis_faktor: float = 1.0
    marktvolumen_faktor: float = 1.0
    produktionskosten_faktor: float = 1.0   # Multiplikator auf Fertigungskosten
    investitionskosten_faktor: float = 1.0  # Multiplikator auf Investitionsauszahlungen

    # Additiver Effekt auf Zinssatz (Prozentpunkte, z.B. 0.02 für +2%)
    zinssatz_delta: float = 0.0

    # Score-Anpassung: gilt für alle Teams außer Qualitätsinvestoren wenn Skandal
    score_faktor_allgemein: float = 1.0
    score_faktor_qualitaet: float = 1.0     # Qualitätsinvestoren sind ausgenommen


# Vordefinierte Ereigniskarten (entsprechen dem Konzept)
EREIGNISKARTEN: list[Ereignis] = [
    Ereignis(
        typ=EreignisTyp.ROHSTOFFKRISE,
        titel="Rohstoffkrise",
        beschreibung="Materialengpässe treiben Rohstoffpreise in die Höhe.",
        materialpreis_faktor=1.25,
    ),
    Ereignis(
        typ=EreignisTyp.NACHFRAGEBOOM,
        titel="Nachfrageboom",
        beschreibung="Starke Konjunktur erhöht die Gesamtnachfrage.",
        marktvolumen_faktor=1.30,
    ),
    Ereignis(
        typ=EreignisTyp.WIRTSCHAFTSKRISE,
        titel="Wirtschaftskrise",
        beschreibung="Rezession dämpft die Nachfrage erheblich.",
        marktvolumen_faktor=0.75,
    ),
    Ereignis(
        typ=EreignisTyp.TECHNOLOGIESPRUNG,
        titel="Technologiesprung",
        beschreibung="Neue Technologien machen Investitionen günstiger.",
        investitionskosten_faktor=0.80,
    ),
    Ereignis(
        typ=EreignisTyp.STREIK,
        titel="Streik",
        beschreibung="Arbeitsniederlegungen erhöhen die Produktionskosten.",
        produktionskosten_faktor=1.15,
    ),
    Ereignis(
        typ=EreignisTyp.NEUE_KONKURRENZ,
        titel="Neue Konkurrenz",
        beschreibung="Neuer Wettbewerber betritt den Markt.",
        marktvolumen_faktor=0.90,
    ),
    Ereignis(
        typ=EreignisTyp.EXPORTCHANCE,
        titel="Exportchance",
        beschreibung="Internationale Nachfrage öffnet neue Absatzmärkte.",
        marktvolumen_faktor=1.20,
    ),
    Ereignis(
        typ=EreignisTyp.ZINSERHOEHUNG,
        titel="Zinserhöhung",
        beschreibung="Zentralbank erhöht den Leitzins.",
        zinssatz_delta=0.02,
    ),
    Ereignis(
        typ=EreignisTyp.QUALITAETSSKANDAL,
        titel="Qualitätsskandal",
        beschreibung="Branchenweiter Skandal schadet dem Image – außer Qualitätsführern.",
        score_faktor_allgemein=0.80,
        score_faktor_qualitaet=1.0,  # Qualitätsinvestoren bleiben unberührt
    ),
    Ereignis(
        typ=EreignisTyp.RUHIGE_RUNDE,
        titel="Ruhige Runde",
        beschreibung="Keine besonderen Ereignisse in diesem Quartal.",
    ),
]


class TeamScore(BaseModel):
    """Scoring-Ergebnis für ein Team in einem Quartal.

    Formel aus Konzept:
        score = marketing^0.4 * quality_factor / price_factor
        market_share = score / sum(all_scores)
        sales = total_market_demand * market_share
    """

    team_id: str
    marketing: float = Field(ge=0.0)
    quality_factor: float = Field(default=1.0, ge=0.0)   # Basiert auf Qualitätsinvestitionen
    price_factor: float = Field(gt=0.0)                   # = Verkaufspreis (normiert)
    rohscore: float = 0.0      # Berechneter Rohscore vor Normierung
    marktanteil: float = 0.0   # 0.0–1.0 nach Normierung
    zuteilbare_lose: int = 0   # Nachfrage in Losen (gerundet)


class MarktZustand(BaseModel):
    """Marktparameter für ein Quartal (geteilt von allen Teams).

    Basiswerte gelten ohne Ereigniseffekte.
    Aktuelle Werte = Basiswerte × Ereignismultiplikatoren.
    """

    jahr: int
    quartal: int  # 1–4

    # Marktvolumen
    basis_marktvolumen_lose: float = 40.0      # Gesamtnachfrage in Losen (Basiswert)
    aktuelles_marktvolumen_lose: float = 40.0  # Nach Ereignisanpassung

    # Materialpreise (Mio. EUR pro Los)
    basis_materialpreis: float = 3.0
    aktueller_materialpreis: float = 3.0
    materialpreis_langfrist_aufschlag: float = 0.10  # +10% für Langfristvertrag

    # Kapitalkosten
    basis_zinssatz: float = 0.10   # 10% p.a.
    aktueller_zinssatz: float = 0.10

    # Fertigungs- und Montagekosten (Multiplikator durch Ereignis)
    fertigungskosten_faktor: float = 1.0
    investitionskosten_faktor: float = 1.0

    # Aktives Ereignis dieser Runde
    aktives_ereignis: Optional[Ereignis] = None

    # Scoring-Ergebnisse je Team (befüllt nach Entscheidungsabgabe)
    team_scores: dict[str, TeamScore] = Field(default_factory=dict)

    def materialpreis_fuer(self, einkaufstyp: str) -> float:
        """Gibt den effektiven Materialpreis pro Los zurück."""
        from src.models.round import MaterialEinkaufsTyp  # lokaler Import vermeidet Zirkelbezug

        if einkaufstyp == MaterialEinkaufsTyp.LANGFRIST:
            return self.aktueller_materialpreis * (1 + self.materialpreis_langfrist_aufschlag)
        return self.aktueller_materialpreis

    def anwende_ereignis(self, ereignis: Ereignis) -> None:
        """Passt aktuelle Marktparameter basierend auf dem Ereignis an."""
        self.aktives_ereignis = ereignis
        self.aktuelles_marktvolumen_lose = (
            self.basis_marktvolumen_lose * ereignis.marktvolumen_faktor
        )
        self.aktueller_materialpreis = (
            self.basis_materialpreis * ereignis.materialpreis_faktor
        )
        self.aktueller_zinssatz = self.basis_zinssatz + ereignis.zinssatz_delta
        self.fertigungskosten_faktor = ereignis.produktionskosten_faktor
        self.investitionskosten_faktor = ereignis.investitionskosten_faktor
