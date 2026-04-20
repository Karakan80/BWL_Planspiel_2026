"""
engine/production.py – Quartalsmechanik

Implementiert die 10 Original-Quartalschritte in exakter Reihenfolge.
Alle monetären Werte in Mio. EUR.

Schrittfolge (Original-Spielmechanik):
    1.  Material bestellen & bezahlen    (3 M/Los)
    2.  Rohmaterial ins Lager
    3.  Produktion Stufe 1 starten       (3 M/Los)
    4.  Endmontage Stufe 2               (1 M/Los)
    5.  Fertigprodukte ins Lager
    6.  Rechnung stellen → Erlös zu Forderungen
    7.  Herstellungskosten notieren
    8.  Produkte liefern
    9.  Forderungen vom Vorquartal einziehen → Kasse
    10. Gemeinkosten zahlen
"""
from __future__ import annotations

from src.models.market import MarktZustand
from src.models.round import (
    Cashflow,
    GuV,
    InvestitionsTyp,
    QuartalErgebnis,
    TeamEntscheidung,
)
from src.models.team import Team

# ─── Kostenkonstanten (Original-Spielmechanik, Mio. EUR pro Los) ─────────────
MATERIAL_PRO_LOS: float = 3.0    # Schritt 1: Rohmaterialkosten
FERTIGUNG_PRO_LOS: float = 3.0   # Schritt 3: Fertigungskosten Stufe 1
MONTAGE_PRO_LOS: float = 1.0     # Schritt 4: Endmontagekosten Stufe 2
HK_PRO_LOS: float = 7.0          # Herstellungskosten gesamt (= Summe der drei oben)


def verarbeite_quartal(
    team: Team,
    entscheidung: TeamEntscheidung,
    markt: MarktZustand,
    verkaufte_lose: int,
    forderungen_vorquartal: float,
) -> QuartalErgebnis:
    """
    Führt alle 10 Quartalschritte in Original-Reihenfolge aus.

    ``team`` wird direkt mutiert (Aktiva, Passiva, Kapazitäten).
    Gibt einen unveränderlichen QuartalErgebnis-Snapshot zurück.

    Args:
        team:                   Teamzustand (wird in-place verändert).
        entscheidung:           Abgegebene Teamentscheidungen für dieses Quartal.
        markt:                  Marktparameter inkl. aktiver Ereigniseffekte.
        verkaufte_lose:         Vom Demand-Engine zugeteilte Verkaufslose.
        forderungen_vorquartal: Forderungsbestand aus dem Vorquartal (Schritt 9).

    Returns:
        Unveränderlicher ``QuartalErgebnis``-Snapshot mit GuV, Cashflow und Bilanz.
    """
    cf = Cashflow()
    guv = GuV()

    # Kapazitätsgrenze: Team kann nicht mehr produzieren als installierte Kapazität
    produzierte_lose: int = min(
        entscheidung.produktionsmenge_lose,
        team.kapazitaet_lose_pro_quartal,
    )

    # Effektive Stückkosten inkl. Ereignis-Multiplikatoren (z.B. Streik +15%)
    mat_preis: float = markt.materialpreis_fuer(entscheidung.material_einkauf)
    fert_eff: float = FERTIGUNG_PRO_LOS * markt.fertigungskosten_faktor
    mont_eff: float = MONTAGE_PRO_LOS * markt.fertigungskosten_faktor
    hk_eff: float = mat_preis + fert_eff + mont_eff

    # ── Schritte 1 + 2: Material bestellen & bezahlen │ Rohmaterial ins Lager ─
    mat_kosten: float = produzierte_lose * mat_preis
    _zahle_material(team, mat_kosten, cf)
    if not team.jit_aktiv:
        # Normalbetrieb: Material landet im Lager, bevor es verbraucht wird
        team.aktiva.rohmaterial += mat_kosten

    # ── Schritt 3: Produktion Stufe 1 (Fertigung) ─────────────────────────────
    fert_kosten: float = produzierte_lose * fert_eff
    team.aktiva.kasse -= fert_kosten
    cf.auszahlungen_fertigung_stufe1 = fert_kosten
    # Rohmaterial wird verbraucht; kombinierter Wert geht in WIP
    team.aktiva.rohmaterial = max(0.0, team.aktiva.rohmaterial - mat_kosten)
    team.aktiva.unfertige_erzeugnisse += produzierte_lose * (mat_preis + fert_eff)

    # ── Schritte 4 + 5: Endmontage Stufe 2 │ Fertigprodukte ins Lager ─────────
    mont_kosten: float = produzierte_lose * mont_eff
    team.aktiva.kasse -= mont_kosten
    cf.auszahlungen_montage_stufe2 = mont_kosten
    # WIP abbauen; fertige Lose werden zu Herstellungskosten ins Fertigwarenlager gebucht
    team.aktiva.unfertige_erzeugnisse = max(
        0.0,
        team.aktiva.unfertige_erzeugnisse - produzierte_lose * (mat_preis + fert_eff),
    )
    team.aktiva.fertigwaren += produzierte_lose * hk_eff

    # ── Schritte 6 + 7: Rechnung stellen │ Herstellungskosten notieren ────────
    # Lieferbar = min(Markt-Nachfrage, Fertigwaren-Lagerbestand in Losen)
    lieferbare_lose: int = _berechne_lieferbare_lose(team, verkaufte_lose, hk_eff)
    erloes: float = lieferbare_lose * entscheidung.verkaufspreis
    # GuV: Herstellungskosten = PRODUZIERTE Lose × HK (Gesamtkostenverfahren)
    hk_produziert: float = produzierte_lose * hk_eff
    hk_geliefert: float = lieferbare_lose * hk_eff   # für Fertigwarenbewegung
    guv.umsatz = erloes
    guv.herstellungskosten = hk_produziert
    guv.rohertrag = erloes - hk_produziert
    guv.gemeinkosten = team.gemeinkosten_pro_quartal
    # Erlös → Forderungen (cash erst nächstes Quartal, Schritt 9)
    team.aktiva.forderungen = erloes

    # ── Schritt 8: Produkte liefern ────────────────────────────────────────────
    team.aktiva.fertigwaren = max(0.0, team.aktiva.fertigwaren - hk_geliefert)

    # ── Schritt 9: Forderungen vom Vorquartal einziehen → Kasse ───────────────
    team.aktiva.kasse += forderungen_vorquartal
    cf.einzahlungen_forderungen = forderungen_vorquartal

    # ── Schritt 10: Gemeinkosten zahlen ───────────────────────────────────────
    team.aktiva.kasse -= team.gemeinkosten_pro_quartal
    cf.auszahlungen_gemeinkosten = team.gemeinkosten_pro_quartal

    # ── Erweiterungen (außerhalb der 10 Original-Schritte) ────────────────────
    # Marketing: cashwirksamer operativer Aufwand
    team.aktiva.kasse -= entscheidung.marketingbudget
    cf.auszahlungen_marketing = entscheidung.marketingbudget

    _verarbeite_investition(team, entscheidung, markt, cf)
    _verarbeite_kredit(team, entscheidung, cf)

    # ── Insolvenz-Check ────────────────────────────────────────────────────────
    _pruefe_insolvenz(team)

    # Score-Objekt aus MarktZustand lesen (vom Demand-Engine befüllt)
    score_obj = markt.team_scores.get(team.id)

    return QuartalErgebnis(
        team_id=team.id,
        jahr=entscheidung.jahr,
        quartal=entscheidung.quartal,
        entscheidung=entscheidung,
        guv=guv,
        cashflow=cf,
        marktanteil=score_obj.marktanteil if score_obj else 0.0,
        verkaufte_lose=lieferbare_lose,
        score=score_obj.rohscore if score_obj else 0.0,
        kasse_nach_quartal=team.aktiva.kasse,
        forderungen_nach_quartal=team.aktiva.forderungen,
        eigenkapital_nach_quartal=team.passiva.eigenkapital,
        fremdkapital_nach_quartal=team.passiva.langfristiges_fk,
    )


# ─── Private Hilfsfunktionen ─────────────────────────────────────────────────


def _zahle_material(team: Team, betrag: float, cf: Cashflow) -> None:
    """
    Bucht Materialauszahlung unter Berücksichtigung des Lieferantenkredits.

    Normalbetrieb:      Sofortzahlung.
    Lieferantenkredit:  Zahlung um 1 Quartal verzögert – dieses Quartal werden
                        die Schulden des Vorquartals bezahlt; die aktuellen Kosten
                        werden als ``material_schulden_vorquartal`` zurückgestellt.
    """
    if team.lieferantenkredit_aktiv:
        heute = team.material_schulden_vorquartal
        team.aktiva.kasse -= heute
        cf.auszahlungen_material = heute
        team.material_schulden_vorquartal = betrag  # wird nächste Periode gezahlt
    else:
        team.aktiva.kasse -= betrag
        cf.auszahlungen_material = betrag
        team.material_schulden_vorquartal = 0.0


def _berechne_lieferbare_lose(team: Team, nachfrage: int, hk_pro_los: float) -> int:
    """
    Lieferbare Lose = min(Markt-Nachfrage, Fertigwaren-Lagerbestand in Losen).
    Der Lagerbestand wird durch ganzzahlige Division in Lose umgerechnet.
    """
    if hk_pro_los <= 0:
        return 0
    lager_in_losen = int(team.aktiva.fertigwaren / hk_pro_los)
    return min(nachfrage, lager_in_losen)


def _verarbeite_investition(
    team: Team,
    entscheidung: TeamEntscheidung,
    markt: MarktZustand,
    cf: Cashflow,
) -> None:
    """
    Bucht Investitionsauszahlung und aktualisiert Bilanz sowie operative Parameter.

    Effektiver Betrag = Entscheidungsbetrag × ``investitionskosten_faktor``
    (z.B. 0.8 beim Ereignis TECHNOLOGIESPRUNG → Investition 20 % günstiger).

    Nutzungsdauer vereinfacht auf 10 Jahre für alle Investitionstypen.
    """
    if entscheidung.investition_typ is None or entscheidung.investition_betrag <= 0:
        return

    betrag: float = entscheidung.investition_betrag * markt.investitionskosten_faktor
    team.aktiva.kasse -= betrag
    cf.auszahlungen_investition = betrag
    afa_delta: float = round(betrag / 10.0, 4)  # Abschreibung p.a.

    if entscheidung.investition_typ == InvestitionsTyp.MASCHINE:
        # Neue Maschine: Kapazität steigt um 1 Los/Q; Maschinenwert + AfA erhöhen
        team.aktiva.maschinen += betrag
        team.kapazitaet_lose_pro_quartal += 1
        team.abschreibungen.maschinen += afa_delta

    elif entscheidung.investition_typ == InvestitionsTyp.AUTOMATISIERUNG:
        # Automatisierung: BGA-Wert steigt; quality_factor bleibt; AfA erhöhen
        team.aktiva.bga += betrag
        team.automatisierungsinvestition_gesamt += betrag
        team.abschreibungen.bga += afa_delta

    elif entscheidung.investition_typ == InvestitionsTyp.QUALITAET:
        # Qualitätsinvestition: BGA + kumulierter Betrag für Scoring
        team.aktiva.bga += betrag
        team.qualitaetsinvestition_gesamt += betrag
        team.abschreibungen.bga += afa_delta


def _verarbeite_kredit(team: Team, entscheidung: TeamEntscheidung, cf: Cashflow) -> None:
    """Kreditaufnahme und freiwillige Tilgung."""
    if entscheidung.kredit_aufnahme > 0:
        team.aktiva.kasse += entscheidung.kredit_aufnahme
        team.passiva.langfristiges_fk += entscheidung.kredit_aufnahme
        cf.einzahlungen_kredit = entscheidung.kredit_aufnahme

    if entscheidung.tilgung > 0:
        # Tilgung kann FK nicht unter 0 bringen
        tilgung: float = min(entscheidung.tilgung, team.passiva.langfristiges_fk)
        team.aktiva.kasse -= tilgung
        team.passiva.langfristiges_fk -= tilgung
        cf.auszahlungen_tilgung = tilgung


def _pruefe_insolvenz(team: Team) -> None:
    """
    Insolvenz-Regel (Konzept §6):
    Kasse < 0 für 2 aufeinanderfolgende Quartale → ``team.ist_insolvent = True``.
    Ein positives Kassensaldo setzt den Zähler zurück.
    """
    if team.aktiva.kasse < 0:
        team.negative_kasse_quartale += 1
        if team.negative_kasse_quartale >= 2:
            team.ist_insolvent = True
    else:
        team.negative_kasse_quartale = 0
