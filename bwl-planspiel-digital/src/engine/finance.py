"""
engine/finance.py – Jahresabschluss-Engine

Führt am Ende von Q4 den vollständigen Jahresabschluss durch.
Reihenfolge (Original-Spielmechanik):
    1. Zinsen berechnen und zahlen          (GuV + Cashflow)
    2. Abschreibungen buchen                (nur GuV; reduziert Buchwerte)
    3. EBT = EBIT − Zinsen
    4. Steuern: 33 % auf EBT > 0           (GuV + Cashflow; kein negativer Steuerwert)
    5. Nettogewinn → Gewinnrücklage         (Eigenkapital steigt/sinkt)
    6. Kennzahlen berechnen

Alle Werte in Mio. EUR.
"""
from __future__ import annotations

from src.models.round import GuV, Kennzahlen, QuartalErgebnis
from src.models.team import Team

STEUERSATZ: float = 0.33   # § Jahresabschluss: 33 % auf positiven EBT
HK_PRO_LOS: float = 7.0    # variable Stückkosten für BEP-Berechnung (Original-HK)


def buche_jahresabschluss(
    team: Team,
    quartal_ergebnisse: list[QuartalErgebnis],
    fk_jahresbeginn: float,
    zinssatz: float = 0.10,
) -> tuple[GuV, Kennzahlen]:
    """
    Vollständiger Jahresabschluss nach Original-Spielmechanik.

    ``team`` wird in-place mutiert (Kasse, Buchwerte, Gewinnrücklage).

    Args:
        team:               Teamzustand nach Q4-Verarbeitung.
        quartal_ergebnisse: Exakt 4 QuartalErgebnis-Objekte (Q1–Q4).
        fk_jahresbeginn:    FK-Bestand zu Jahresbeginn (VOR allen Tilgungen des Jahres).
                            Wird für die Zinsberechnung genutzt, da Tilgungen im
                            Original-Spiel die Zinslast des laufenden Jahres nicht mindern.
        zinssatz:           Effektiver Jahreszinssatz (Standard 10 %; kann durch
                            Ereignis ZINSERHOEHUNG erhöht sein).

    Returns:
        ``(jahres_guv, kennzahlen)``
    """
    guv = _summiere_operative_guv(quartal_ergebnisse)

    # 1. Zinsen (cashwirksam)
    guv.zinsen = round(fk_jahresbeginn * zinssatz, 4)
    team.aktiva.kasse -= guv.zinsen

    # 2. Abschreibungen (NICHT cashwirksam; reduziert nur Buchwerte und GuV)
    guv.abschreibungen = team.abschreibungen.gesamt
    guv.ebit = guv.rohertrag - guv.gemeinkosten - guv.abschreibungen
    _reduziere_buchwerte(team)

    # 3. EBT
    guv.ebt = guv.ebit - guv.zinsen

    # 4. Steuern (cashwirksam; mind. 0 – kein negativer Steuerwert)
    guv.steuern = round(max(0.0, guv.ebt) * STEUERSATZ, 4)
    team.aktiva.kasse -= guv.steuern

    # 5. Nettogewinn + Eigenkapital
    guv.nettogewinn = guv.ebt - guv.steuern
    team.passiva.gewinnruecklage += guv.nettogewinn

    # 6. Kennzahlen
    total_lose = sum(qe.verkaufte_lose for qe in quartal_ergebnisse)
    kpis = _berechne_kennzahlen(guv, team, total_lose)

    return guv, kpis


# ─── Private Hilfsfunktionen ─────────────────────────────────────────────────


def _summiere_operative_guv(quartal_ergebnisse: list[QuartalErgebnis]) -> GuV:
    """
    Aggregiert Umsatz, Herstellungskosten und Gemeinkosten aus den 4 Quartalen.

    Marketing-Budget wird als operativer Aufwand in die Gemeinkosten eingerechnet
    (parallel zu Overhead-Gemeinkosten).
    AfA, Zinsen, Steuern und Nettogewinn werden von ``buche_jahresabschluss`` gesetzt.
    """
    guv = GuV()
    for qe in quartal_ergebnisse:
        guv.umsatz += qe.guv.umsatz
        guv.herstellungskosten += qe.guv.herstellungskosten
        guv.gemeinkosten += qe.guv.gemeinkosten + qe.entscheidung.marketingbudget

    guv.rohertrag = guv.umsatz - guv.herstellungskosten
    # EBIT wird erst nach Abschreibungen gesetzt
    return guv


def _reduziere_buchwerte(team: Team) -> None:
    """
    Bucht jährliche Abschreibungen gegen Anlagevermögen.
    Buchwerte können nicht negativ werden; kein Cashflow-Effekt.
    """
    team.aktiva.gebaeude = max(0.0, team.aktiva.gebaeude - team.abschreibungen.gebaeude)
    team.aktiva.maschinen = max(0.0, team.aktiva.maschinen - team.abschreibungen.maschinen)
    team.aktiva.bga = max(0.0, team.aktiva.bga - team.abschreibungen.bga)


def _berechne_kennzahlen(
    guv: GuV,
    team: Team,
    total_lose_verkauft: int,
) -> Kennzahlen:
    """
    Berechnet alle 7 Kennzahlen aus dem Konzept.

    Formeln:
        ROS  = EBIT / Umsatz × 100
        ROE  = Nettogewinn / Eigenkapital × 100
        ROI  = EBIT / Gesamtkapital × 100
        KU   = Umsatz / Gesamtkapital
        BEP  = Fixkosten / (Ø-Preis_pro_Los − variable_Stückkosten)  [Einheit: Lose]
        Liq1 = Kasse / kurzfrist. Verbindlichkeiten
        Liq2 = (Kasse + Forderungen) / kurzfrist. Verbindlichkeiten

    Kennzahlen bleiben ``None`` wenn der Nenner 0 ist (Division durch 0 wird vermieden).
    Liquiditätskennzahlen sind nur definiert wenn Lieferantenkredit aktiv
    (= einzige kurzfristige Verbindlichkeit im Modell).
    """
    kpis = Kennzahlen()
    gesamtkapital = team.aktiva.summe
    ek = team.passiva.eigenkapital

    if guv.umsatz > 0:
        kpis.ros = round(guv.ebit / guv.umsatz * 100, 2)

    if ek > 0:
        kpis.roe = round(guv.nettogewinn / ek * 100, 2)

    if gesamtkapital > 0:
        kpis.roi = round(guv.ebit / gesamtkapital * 100, 2)
        kpis.ku = round(guv.umsatz / gesamtkapital, 4)

    # BEP in Losen: Fixkosten / Deckungsbeitrag pro Los
    # Fixkosten = Gemeinkosten (inkl. Marketing) + AfA
    # Variable Stückkosten = HK_PRO_LOS (Original-Herstellungskosten)
    if total_lose_verkauft > 0 and guv.umsatz > 0:
        avg_preis_pro_los = guv.umsatz / total_lose_verkauft
        db_pro_los = avg_preis_pro_los - HK_PRO_LOS  # Deckungsbeitrag
        fixkosten = guv.gemeinkosten + guv.abschreibungen
        kpis.fixkosten = round(fixkosten, 4)
        kpis.variable_stueckkosten = HK_PRO_LOS
        if db_pro_los > 0:
            kpis.bep = round(fixkosten / db_pro_los, 2)

    # Liquidität (kurzfrist. VB = aufgelaufener Lieferantenkredit)
    kurzfrist_vb = team.material_schulden_vorquartal
    if kurzfrist_vb > 0:
        kpis.liquiditaet_1 = round(team.aktiva.kasse / kurzfrist_vb, 4)
        kpis.liquiditaet_2 = round(
            (team.aktiva.kasse + team.aktiva.forderungen) / kurzfrist_vb, 4
        )

    return kpis
