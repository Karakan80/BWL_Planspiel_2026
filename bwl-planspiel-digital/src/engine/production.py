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
AUTOMATISIERUNG_ERSPARNIS_PRO_MIO: float = 0.02
AUTOMATISIERUNG_MAX_ERSPARNIS: float = 0.30


def verarbeite_quartal(
    team: Team,
    entscheidung: TeamEntscheidung,
    markt: MarktZustand,
    verkaufte_lose: int,
    forderungen_vorquartal: float,
    fk_jahresbeginn: float = 0.0,
    zinssatz: float = 0.10,
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
    automatisierungsfaktor = _automatisierungs_kostenfaktor(team)
    fert_eff: float = FERTIGUNG_PRO_LOS * markt.fertigungskosten_faktor * automatisierungsfaktor
    mont_eff: float = MONTAGE_PRO_LOS * markt.fertigungskosten_faktor * automatisierungsfaktor
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
    team.fertigwaren_lose += produzierte_lose

    # ── Schritte 6 + 7: Rechnung stellen │ Herstellungskosten notieren ────────
    # Lieferbar = min(Markt-Nachfrage, Fertigwaren-Lagerbestand in Losen)
    lieferbare_lose: int = _berechne_lieferbare_lose(team, verkaufte_lose)
    erloes: float = lieferbare_lose * entscheidung.verkaufspreis
    hk_geliefert: float = _bewerte_und_entnehme_fertigwaren(team, lieferbare_lose)
    guv.umsatz = erloes
    guv.herstellungskosten = hk_geliefert
    guv.rohertrag = erloes - hk_geliefert
    gemeinkosten_effektiv = max(0.0, team.gemeinkosten_pro_quartal + entscheidung.gemeinkosten_delta)
    guv.gemeinkosten = gemeinkosten_effektiv + entscheidung.marketingbudget
    # Erlös → Forderungen (cash erst nächstes Quartal, Schritt 9)
    team.aktiva.forderungen = erloes

    # ── Schritt 8: Produkte liefern ────────────────────────────────────────────
    # Der Lagerabgang wurde bereits mit Durchschnittskosten bewertet und gebucht.

    # ── Schritt 9: Forderungen vom Vorquartal einziehen → Kasse ───────────────
    team.aktiva.kasse += forderungen_vorquartal
    cf.einzahlungen_forderungen = forderungen_vorquartal

    # ── Schritt 10: Gemeinkosten zahlen ───────────────────────────────────────
    team.aktiva.kasse -= gemeinkosten_effektiv
    cf.auszahlungen_gemeinkosten = gemeinkosten_effektiv

    # ── Erweiterungen (außerhalb der 10 Original-Schritte) ────────────────────
    # Marketing: cashwirksamer operativer Aufwand
    team.aktiva.kasse -= entscheidung.marketingbudget
    cf.auszahlungen_marketing = entscheidung.marketingbudget

    _verarbeite_investition(team, entscheidung, markt, cf)
    _verarbeite_kredit(team, entscheidung, cf)

    # ── Quartal-GuV vervollständigen (AfA + Zinsen → EBIT/EBT/Steuern) ────────
    afa_quartal: float = round(team.abschreibungen.gesamt / 4, 4)
    zinsen_quartal: float = round(fk_jahresbeginn * zinssatz / 4, 4)
    guv.abschreibungen = afa_quartal
    guv.ebit = round(guv.rohertrag - guv.gemeinkosten - afa_quartal, 4)
    guv.zinsen = zinsen_quartal
    guv.ebt = round(guv.ebit - zinsen_quartal, 4)
    guv.steuern = round(max(0.0, guv.ebt) * (1 / 3), 4)
    guv.nettogewinn = round(guv.ebt - guv.steuern, 4)

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
        marktvolumen_lose=markt.aktuelles_marktvolumen_lose,
        marktvolumen_vor_preis_lose=markt.marktvolumen_vor_preis_lose,
        aktive_teamanzahl=markt.aktive_teamanzahl,
        teamanzahl_faktor=markt.teamanzahl_faktor,
        durchschnittspreis_markt=markt.durchschnittspreis_markt,
        preis_elastizitaets_faktor=markt.preis_elastizitaets_faktor,
        score=score_obj.rohscore if score_obj else 0.0,
        score_marketing_term=score_obj.marketing_term if score_obj else 1.0,
        score_qualitaets_faktor=score_obj.quality_factor if score_obj else 1.0,
        score_gemeinkosten_faktor=score_obj.gemeinkosten_factor if score_obj else 1.0,
        score_preis_faktor=score_obj.price_factor if score_obj else 1.0,
        score_ereignis_faktor=score_obj.ereignis_factor if score_obj else 1.0,
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


def _automatisierungs_kostenfaktor(team: Team) -> float:
    """
    Automatisierungsinvestitionen senken Fertigungs- und Montagekosten.

    Pro investierter Mio. EUR sinken die direkten Fertigungskosten um 2 Prozentpunkte,
    maximal um 30 %. Die Wirkung startet ab dem Folgequartal, weil Investitionen erst
    nach der laufenden Produktion gebucht werden.
    """
    ersparnis = min(
        AUTOMATISIERUNG_MAX_ERSPARNIS,
        team.automatisierungsinvestition_gesamt * AUTOMATISIERUNG_ERSPARNIS_PRO_MIO,
    )
    return 1.0 - ersparnis


def _berechne_lieferbare_lose(team: Team, nachfrage: int) -> int:
    """
    Lieferbare Lose = min(Markt-Nachfrage, physischer Fertigwarenbestand).
    """
    return min(nachfrage, max(0, team.fertigwaren_lose))


def _bewerte_und_entnehme_fertigwaren(team: Team, lose: int) -> float:
    """
    Bucht den Lagerabgang der gelieferten Lose mit Durchschnittskosten.

    Damit werden auch alte Lagerbestände korrekt als Herstellungskosten erfasst,
    statt nur die im aktuellen Quartal produzierten Lose in die GuV zu nehmen.
    """
    if lose <= 0 or team.fertigwaren_lose <= 0:
        return 0.0

    avg_cost = team.aktiva.fertigwaren / team.fertigwaren_lose
    hk_geliefert = min(team.aktiva.fertigwaren, lose * avg_cost)
    team.aktiva.fertigwaren = max(0.0, round(team.aktiva.fertigwaren - hk_geliefert, 4))
    team.fertigwaren_lose = max(0, team.fertigwaren_lose - lose)
    return round(hk_geliefert, 4)


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
        team.aktiva.maschinen += betrag
        team.kapazitaet_lose_pro_quartal += entscheidung.maschinen_kapazitaets_zuwachs
        team.automatisierungsinvestition_gesamt += (
            entscheidung.maschinen_automatisierung_bonus
        )
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
