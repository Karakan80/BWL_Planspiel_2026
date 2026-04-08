from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class MaterialEinkaufsTyp(str, Enum):
    """Einkaufsstrategie für Rohmaterial."""

    SPOT = "spot"           # Preis = aktueller Marktpreis (günstig, aber volatil)
    LANGFRIST = "langfrist" # Preis = Marktpreis × 1.1 (stabil, aber teurer)


class InvestitionsTyp(str, Enum):
    MASCHINE = "maschine"             # Erhöht Kapazität (+1 Los/Q)
    AUTOMATISIERUNG = "automatisierung"  # Senkt variable Stückkosten
    QUALITAET = "qualitaet"           # Erhöht quality_factor im Scoring


class TeamEntscheidung(BaseModel):
    """Entscheidungen eines Teams für ein Quartal (Eingabe vor Berechnung)."""

    team_id: str
    jahr: int
    quartal: int  # 1–4

    # Pflichtfelder
    verkaufspreis: float = Field(gt=0, description="Verkaufspreis pro Los (Mio. EUR)")
    produktionsmenge_lose: int = Field(ge=0, description="Bestellte Produktionslose")
    marketingbudget: float = Field(ge=0.0, description="Marketingausgaben (Mio. EUR)")

    # Optionale Felder
    material_einkauf: MaterialEinkaufsTyp = MaterialEinkaufsTyp.SPOT
    investition_typ: Optional[InvestitionsTyp] = None
    investition_betrag: float = Field(default=0.0, ge=0.0)
    kredit_aufnahme: float = Field(default=0.0, ge=0.0, description="Neuer Kredit (Mio. EUR)")
    tilgung: float = Field(default=0.0, ge=0.0, description="Freiwillige Tilgung (Mio. EUR)")

    @model_validator(mode="after")
    def investition_konsistent(self) -> "TeamEntscheidung":
        if self.investition_typ is not None and self.investition_betrag <= 0:
            raise ValueError("investition_betrag muss > 0 sein wenn investition_typ gesetzt ist.")
        if self.investition_typ is None and self.investition_betrag > 0:
            raise ValueError("investition_typ muss gesetzt sein wenn investition_betrag > 0.")
        return self


class GuV(BaseModel):
    """Gewinn- und Verlustrechnung für ein Quartal oder Geschäftsjahr (Mio. EUR)."""

    umsatz: float = 0.0
    herstellungskosten: float = 0.0      # Materialkosten + Fertigungskosten
    rohertrag: float = 0.0               # Umsatz - HK
    gemeinkosten: float = 0.0
    ebit: float = 0.0                    # Rohertrag - Gemeinkosten - AfA
    abschreibungen: float = 0.0          # Nur GuV-wirksam, nicht cashwirksam
    zinsen: float = 0.0
    ebt: float = 0.0                     # EBIT - Zinsen
    steuern: float = 0.0                 # 33% auf positiven EBT, sonst 0
    nettogewinn: float = 0.0             # EBT - Steuern


class Cashflow(BaseModel):
    """Zahlungswirksame Bewegungen eines Quartals (Mio. EUR).

    Abschreibungen sind NICHT enthalten (nur GuV-wirksam).
    Forderungen werden 1 Quartal verzögert kassiert.
    """

    einzahlungen_forderungen: float = 0.0    # Einzug Forderungen aus Vorquartal
    auszahlungen_material: float = 0.0       # Schritte 1: Material bezahlt
    auszahlungen_fertigung_stufe1: float = 0.0   # Schritt 3
    auszahlungen_montage_stufe2: float = 0.0     # Schritt 4
    auszahlungen_gemeinkosten: float = 0.0   # Schritt 10
    auszahlungen_investition: float = 0.0
    auszahlungen_marketing: float = 0.0
    auszahlungen_zinsen: float = 0.0         # Jahresabschluss
    auszahlungen_steuern: float = 0.0        # Jahresabschluss
    auszahlungen_tilgung: float = 0.0
    einzahlungen_kredit: float = 0.0

    @property
    def netto(self) -> float:
        einzahlungen = self.einzahlungen_forderungen + self.einzahlungen_kredit
        auszahlungen = (
            self.auszahlungen_material
            + self.auszahlungen_fertigung_stufe1
            + self.auszahlungen_montage_stufe2
            + self.auszahlungen_gemeinkosten
            + self.auszahlungen_investition
            + self.auszahlungen_marketing
            + self.auszahlungen_zinsen
            + self.auszahlungen_steuern
            + self.auszahlungen_tilgung
        )
        return einzahlungen - auszahlungen


class Kennzahlen(BaseModel):
    """Betriebswirtschaftliche Kennzahlen (werden am Jahresende berechnet)."""

    ros: Optional[float] = None    # Return on Sales  = EBIT / Umsatz × 100
    roe: Optional[float] = None    # Return on Equity = Nettogewinn / EK × 100
    roi: Optional[float] = None    # Return on Investment = EBIT / Gesamtkapital × 100
    ku: Optional[float] = None     # Kapitalumschlag = Umsatz / Gesamtkapital
    bep: Optional[float] = None    # Break-even-Punkt = Fixkosten / (Preis - var. Stückkosten)
    liquiditaet_1: Optional[float] = None   # Kasse / kurzfrist. Verbindlichkeiten
    liquiditaet_2: Optional[float] = None   # (Kasse + Forderungen) / kurzfrist. Verbindl.

    # Hilfsgrößen für BEP
    fixkosten: Optional[float] = None
    variable_stueckkosten: Optional[float] = None


class QuartalErgebnis(BaseModel):
    """Berechnetes Ergebnis eines Teams nach Quartalsverarbeitung."""

    team_id: str
    jahr: int
    quartal: int

    entscheidung: TeamEntscheidung
    guv: GuV = Field(default_factory=GuV)
    cashflow: Cashflow = Field(default_factory=Cashflow)

    # Marktdaten dieses Quartals
    marktanteil: float = 0.0          # 0.0–1.0
    verkaufte_lose: int = 0
    score: float = 0.0                # Rohscore vor Normierung

    # Jahresabschluss-Kennzahlen (nur Q4 befüllt)
    kennzahlen: Optional[Kennzahlen] = None

    # Bilanzwerte nach Quartalsabschluss (Snapshot)
    kasse_nach_quartal: float = 0.0
    forderungen_nach_quartal: float = 0.0
    eigenkapital_nach_quartal: float = 0.0
    fremdkapital_nach_quartal: float = 0.0
