"""
engine/finance.py – Jahresabschluss-Engine

Führt am Ende von Q4 den vollständigen Jahresabschluss durch.
Reihenfolge (Original-Spielmechanik):
    1. Zinsen berechnen und zahlen          (GuV + Cashflow)
    2. Abschreibungen buchen                (nur GuV; reduziert Buchwerte)
    3. EBT = EBIT − Zinsen
    4. Steuern: 1/3 auf EBT > 0            (GuV + Cashflow; NIEMALS negativ)
    5. Nettogewinn → Gewinnrücklage         (Eigenkapital steigt/sinkt)
    6. Kennzahlen berechnen
    7. Bilanzgleichung prüfen               (Aktiva = Passiva; Warnung bei Abweichung)

Alle Werte in Mio. EUR.
"""
from __future__ import annotations

import warnings

from src.models.round import GuV, Kennzahlen, QuartalErgebnis
from src.models.team import Team

STEUERSATZ: float = 1 / 3   # 33,3 % auf positiven EBT – NIEMALS negativ
HK_PRO_LOS: float = 7.0     # variable Stückkosten für BEP-Berechnung (Original-HK)


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
                            Tilgungen im Original-Spiel mindern die Zinslast des
                            laufenden Jahres nicht.
        zinssatz:           Effektiver Jahreszinssatz (Standard 10 %; kann durch
                            Ereignis ZINSERHOEHUNG erhöht sein).

    Returns:
        ``(jahres_guv, kennzahlen)``
    """
    guv = _summiere_operative_guv(quartal_ergebnisse)

    # 1. Zinsen (cashwirksam, auf FK zu Jahresbeginn)
    guv.zinsen = round(fk_jahresbeginn * zinssatz, 4)
    team.aktiva.kasse -= guv.zinsen

    # 2. Abschreibungen (NICHT cashwirksam; reduziert Buchwerte und GuV-EBIT)
    guv.abschreibungen = round(team.abschreibungen.gesamt, 4)
    guv.ebit = round(guv.rohertrag - guv.gemeinkosten - guv.abschreibungen, 4)
    _reduziere_buchwerte(team)

    # 3. EBT
    guv.ebt = round(guv.ebit - guv.zinsen, 4)

    # 4. Steuern: max(0, EBT) × 1/3 → NIEMALS negativ
    guv.steuern = round(max(0.0, guv.ebt) * STEUERSATZ, 4)
    team.aktiva.kasse -= guv.steuern

    # 5. Nettogewinn → Eigenkapital (Gewinnrücklage)
    guv.nettogewinn = round(guv.ebt - guv.steuern, 4)
    team.passiva.gewinnruecklage += guv.nettogewinn

    # 6. Kennzahlen
    total_lose = sum(qe.verkaufte_lose for qe in quartal_ergebnisse)
    kpis = _berechne_kennzahlen(guv, team, total_lose)

    # 7. Bilanzgleichung prüfen (warnt, schlägt nicht fehl)
    _pruefe_bilanzgleichung(team)

    return guv, kpis


# ─── Private Hilfsfunktionen ─────────────────────────────────────────────────


def _summiere_operative_guv(quartal_ergebnisse: list[QuartalErgebnis]) -> GuV:
    """
    Aggregiert Umsatz, Herstellungskosten (produzierte Lose) und Gemeinkosten
    aus den 4 Quartalen. Marketing-Budget wird als Bestandteil der Gemeinkosten
    eingerechnet. AfA, Zinsen, Steuern werden von buche_jahresabschluss gesetzt.
    """
    guv = GuV()
    for qe in quartal_ergebnisse:
        guv.umsatz += qe.guv.umsatz
        guv.herstellungskosten += qe.guv.herstellungskosten  # = produzierte Lose × HK
        guv.gemeinkosten += qe.guv.gemeinkosten  # already includes marketing budget

    guv.rohertrag = round(guv.umsatz - guv.herstellungskosten, 4)
    return guv


def _reduziere_buchwerte(team: Team) -> None:
    """
    Bucht jährliche Abschreibungen gegen Anlagevermögen.
    Buchwerte können nicht negativ werden (kein Cashflow-Effekt).
    """
    team.aktiva.gebaeude = max(0.0, round(team.aktiva.gebaeude - team.abschreibungen.gebaeude, 4))
    team.aktiva.maschinen = max(0.0, round(team.aktiva.maschinen - team.abschreibungen.maschinen, 4))
    team.aktiva.bga = max(0.0, round(team.aktiva.bga - team.abschreibungen.bga, 4))


def _pruefe_bilanzgleichung(team: Team) -> None:
    """
    Warnt wenn Aktiva ≠ Passiva nach dem Jahresabschluss.

    Kleine Abweichungen (≤ 0.01 Mio. EUR) werden durch float-Rundung toleriert.
    Größere Differenzen deuten auf einen Implementierungsfehler hin.
    """
    aktiva = team.aktiva.summe
    passiva = team.passiva.summe
    differenz = abs(aktiva - passiva)
    if differenz > 0.01:
        warnings.warn(
            f"[Bilanz {team.name}] Aktiva {aktiva:.4f} ≠ Passiva {passiva:.4f} "
            f"(Differenz {differenz:.4f} Mio. €). "
            "Hinweis: Bei Gesamtkostenverfahren (HK=produziert) kann Imbalance "
            "entstehen wenn produzierte ≠ verkaufte Lose.",
            stacklevel=2,
        )


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
        BEP  = Fixkosten / (Ø-Preis_pro_Los − HK_PRO_LOS)  [Einheit: Lose]
        Liq1 = Kasse / kurzfrist. Verbindlichkeiten
        Liq2 = (Kasse + Forderungen) / kurzfrist. Verbindlichkeiten

    Kennzahlen bleiben ``None`` wenn der Nenner 0 ist.
    Liquiditätskennzahlen sind nur definiert wenn Lieferantenkredit aktiv.
    """
    kpis = Kennzahlen()
    gesamtkapital = team.aktiva.summe
    ek = team.passiva.eigenkapital

    if guv.umsatz > 0:
        kpis.ros = round(guv.ebit / guv.umsatz * 100, 2)

    if ek != 0:
        kpis.roe = round(guv.nettogewinn / ek * 100, 2)

    if gesamtkapital > 0:
        kpis.roi = round(guv.ebit / gesamtkapital * 100, 2)
        kpis.ku = round(guv.umsatz / gesamtkapital, 4)

    if total_lose_verkauft > 0 and guv.umsatz > 0:
        avg_preis_pro_los = guv.umsatz / total_lose_verkauft
        db_pro_los = avg_preis_pro_los - HK_PRO_LOS
        fixkosten = guv.gemeinkosten + guv.abschreibungen
        kpis.fixkosten = round(fixkosten, 4)
        kpis.variable_stueckkosten = HK_PRO_LOS
        if db_pro_los > 0:
            kpis.bep = round(fixkosten / db_pro_los, 2)

    # Liquidität: nur wenn Lieferantenkredit-Verbindlichkeiten bestehen
    kurzfrist_vb = team.material_schulden_vorquartal
    if kurzfrist_vb > 0:
        kpis.liquiditaet_1 = round(team.aktiva.kasse / kurzfrist_vb, 4)
        kpis.liquiditaet_2 = round(
            (team.aktiva.kasse + team.aktiva.forderungen) / kurzfrist_vb, 4
        )

    return kpis
