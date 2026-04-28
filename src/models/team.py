from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class Aktiva(BaseModel):
    """Aktivseite der Bilanz (alle Werte in Mio. EUR)."""

    grundstuecke: float = 10.0
    gebaeude: float = 20.0
    maschinen: float = 20.0
    bga: float = 12.0          # Betriebs- und Geschäftsausstattung
    rohmaterial: float = 9.0
    unfertige_erzeugnisse: float = 26.0
    fertigwaren: float = 21.0
    forderungen: float = 25.0  # Forderungen aus Lieferungen (1 Quartal Verzug)
    kasse: float = 24.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summe(self) -> float:
        return (
            self.grundstuecke
            + self.gebaeude
            + self.maschinen
            + self.bga
            + self.rohmaterial
            + self.unfertige_erzeugnisse
            + self.fertigwaren
            + self.forderungen
            + self.kasse
        )


class Passiva(BaseModel):
    """Passivseite der Bilanz (alle Werte in Mio. EUR)."""

    grundkapital: float = 60.0
    gewinnruecklage: float = 7.0
    langfristiges_fk: float = 100.0  # Langfristiges Fremdkapital

    @computed_field  # type: ignore[prop-decorator]
    @property
    def eigenkapital(self) -> float:
        return self.grundkapital + self.gewinnruecklage

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summe(self) -> float:
        return self.eigenkapital + self.langfristiges_fk


class Abschreibungen(BaseModel):
    """Jährliche Abschreibungssätze (Mio. EUR/Jahr).

    Ändern sich durch Investitionen:
    - Maschinen: 5M → 7M ab Jahr 3 (neue Maschine)
    - BGA:       3M → 4M ab Jahr 2 (JIT-Investition)
    """

    gebaeude: float = 1.0
    maschinen: float = 5.0
    bga: float = 3.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gesamt(self) -> float:
        return self.gebaeude + self.maschinen + self.bga


class Team(BaseModel):
    """Persistenter Zustand eines Teams über das gesamte Spiel."""

    id: str
    name: str

    # Bilanz
    aktiva: Aktiva = Field(default_factory=Aktiva)
    passiva: Passiva = Field(default_factory=Passiva)

    # Operative Parameter
    kapazitaet_lose_pro_quartal: int = 2   # Produktionskapazität in Losen
    gemeinkosten_pro_quartal: float = 6.0  # 6M Jahr 1, 5M ab Jahr 2
    abschreibungen: Abschreibungen = Field(default_factory=Abschreibungen)
    fertigwaren_lose: int = 3              # Physische Lose im Fertigwarenlager

    # Investitionsstand (für Scoring relevant)
    qualitaetsinvestition_gesamt: float = 0.0   # Kumulierter Betrag → quality_factor
    automatisierungsinvestition_gesamt: float = 0.0

    # JIT-Umstellung
    jit_aktiv: bool = False  # True nach JIT-Investition (kein Rohmateriallager mehr)

    # Lieferantenkredit (ab Jahr 3 optional)
    lieferantenkredit_aktiv: bool = False  # Zahlungsziel 1 Quartal

    # Lieferantenkredit-Tracking: zurückgestellte Materialkosten des Vorquartals
    material_schulden_vorquartal: float = 0.0

    # Insolvenz-Tracking (Regel: 2 aufeinanderfolgende Quartale Kasse < 0)
    negative_kasse_quartale: int = 0
    ist_insolvent: bool = False
