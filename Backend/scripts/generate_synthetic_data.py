"""Génère un dataset synthétique réaliste de transactions Mobile Money multi-pays.

Aucune donnée personnelle réelle n'est utilisée (cf. document produit : "Données
synthétiques : créer des transactions réalistes ... sans données personnelles").

Périmètre volontairement restreint à ce que Novaris couvre réellement : les wallets
(dépôt, retrait, transfert P2P) via l'app ou en agence — pas de paiement marchand, de
paiement de masse B2B, ni de canaux USSD/web/API. Couvre les 18 pays où Clapay annonce
une présence, avec des transactions domestiques et transfrontalières.

Produit trois fichiers dans data/ :
- customers.csv   : les titulaires de portefeuille suivis (profil de comportement habituel)
- transactions.csv: le flux de transactions, normal + scénarios de fraude injectés et labellisés
- agents.csv      : le pool d'agents Mobile Money (cash-in/cash-out en agence)

Usage:
    python scripts/generate_synthetic_data.py
"""

import calendar
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules.transaction_monitoring.feature_engineering import is_payday_window  # noqa: E402
from shared.utils.currency import APPROX_XOF_PER_UNIT  # noqa: E402
from shared.utils.phone import (  # noqa: E402
    COUNTRIES,
    country_from_phone,
    currency_for_country,
    random_phone_for_country,
)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

NUM_CUSTOMERS = 1500
# 12 mois : couvre un cycle annuel complet (~12 cycles de paie mensuels) et laisse le
# modèle apprendre à ne pas confondre un pic de paie récurrent avec une anomalie (cf.
# limite documentée sur une fenêtre de 60 jours, insuffisante pour toute saisonnalité
# mensuelle ou tendance de plus long terme).
SIM_DAYS = 365
NOW = datetime(2026, 7, 4, 12, 0, 0)
SIM_START = NOW - timedelta(days=SIM_DAYS)

PAYDAY_BIAS_PROB = 0.35  # probabilité qu'une transaction "normale" soit recentrée sur une
                          # fenêtre de paie du même mois plutôt que tirée uniformément
PAYDAY_AMOUNT_MULTIPLIER_RANGE = (1.4, 2.8)  # boost de montant en période de paie
PAYDAY_ELIGIBLE_TYPES = {"deposit", "withdrawal", "transfer"}

# Poids de marché indicatifs (Côte d'Ivoire = marché de référence déjà calibré ailleurs
# dans le produit ; les autres pays reflètent la présence Clapay sans prétendre à une
# part de marché réelle mesurée).
COUNTRY_WEIGHTS = {
    "Côte d'Ivoire": 0.30,
    "Sénégal": 0.10,
    "Cameroun": 0.07,
    "Mali": 0.06,
    "Burkina Faso": 0.06,
    "Ghana": 0.06,
    "Nigeria": 0.06,
    "Bénin": 0.05,
    "Togo": 0.04,
    "Niger": 0.04,
    "Kenya": 0.04,
    "Gabon": 0.03,
    "Congo": 0.03,
    "Rwanda": 0.02,
    "Ouganda": 0.02,
    "Tanzanie": 0.01,
    "Sierra Leone": 0.01,
    "Gambie": 0.005,
    "Guinée Conakry": 0.005,
}
COUNTRY_NAMES = list(COUNTRY_WEIGHTS.keys())
COUNTRY_W = list(COUNTRY_WEIGHTS.values())

# Quelques villes réelles par pays (pas exhaustif, juste de quoi varier les profils).
CITIES_BY_COUNTRY = {
    "Côte d'Ivoire": (["Abidjan", "Bouaké", "Yamoussoukro", "San-Pédro", "Korhogo", "Daloa", "Man", "Gagnoa"],
                      [0.45, 0.12, 0.08, 0.08, 0.07, 0.08, 0.06, 0.06]),
    "Sénégal": (["Dakar", "Thiès", "Saint-Louis"], [0.7, 0.2, 0.1]),
    "Mali": (["Bamako", "Sikasso"], [0.8, 0.2]),
    "Burkina Faso": (["Ouagadougou", "Bobo-Dioulasso"], [0.7, 0.3]),
    "Bénin": (["Cotonou", "Porto-Novo"], [0.8, 0.2]),
    "Togo": (["Lomé", "Kara"], [0.85, 0.15]),
    "Niger": (["Niamey", "Zinder"], [0.8, 0.2]),
    "Cameroun": (["Douala", "Yaoundé"], [0.55, 0.45]),
    "Gabon": (["Libreville", "Port-Gentil"], [0.8, 0.2]),
    "Congo": (["Brazzaville", "Pointe-Noire"], [0.6, 0.4]),
    "Ghana": (["Accra", "Kumasi"], [0.65, 0.35]),
    "Nigeria": (["Lagos", "Abuja"], [0.75, 0.25]),
    "Kenya": (["Nairobi", "Mombasa"], [0.75, 0.25]),
    "Rwanda": (["Kigali"], [1.0]),
    "Ouganda": (["Kampala"], [1.0]),
    "Tanzanie": (["Dar es Salaam", "Dodoma"], [0.85, 0.15]),
    "Sierra Leone": (["Freetown"], [1.0]),
    "Gambie": (["Banjul"], [1.0]),
    "Guinée Conakry": (["Conakry"], [1.0]),
}

KYC_LEVELS = ["basic", "standard", "premium"]
KYC_WEIGHTS = [0.55, 0.35, 0.10]
CUSTOMER_TYPES = ["individual", "merchant", "agent"]
CUSTOMER_TYPE_WEIGHTS = [0.85, 0.10, 0.05]
# Périmètre Novaris : wallet (dépôt/retrait/transfert). Le cash-in/cash-out domine
# toujours largement le volume réel du Mobile Money — pas de répartition uniforme.
TRANSACTION_TYPES = ["deposit", "withdrawal", "transfer"]
TRANSACTION_TYPE_WEIGHTS = [0.40, 0.37, 0.23]  # dans l'ordre de TRANSACTION_TYPES
AGENT_MEDIATED_TYPES = {"deposit", "withdrawal"}
CHANNELS = ["mobile_app", "agent"]
# Le retrait exige toujours un point de cash physique (agence) — impossible de "retirer
# du cash" depuis l'app seule. Le dépôt, lui, peut passer soit par un agent (cash-in
# physique), soit directement depuis un compte Mobile money externe via l'app.
DEPOSIT_AGENT_SHARE = 0.65

# Montant "baseline" moyen en équivalent XOF par type de transaction (avant application
# du facteur client et de la conversion vers la devise locale du client).
TYPE_BASELINE_AMOUNT_XOF = {
    "deposit": 40_000,
    "withdrawal": 35_000,
    "transfer": 30_000,
}
CUSTOMER_TYPE_SCALE = {"individual": 1.0, "merchant": 8.0, "agent": 15.0}

# Proportion de bénéficiaires réguliers d'un client qui sont dans un pays différent du
# sien (l'interopérabilité transfrontalière est un vrai produit Clapay, pas une exception).
CROSS_BORDER_CONTACT_RATE = 0.12
CROSS_BORDER_ADHOC_RATE = 0.05  # part des transactions "hors contacts habituels" qui partent à l'étranger

FRAUD_SCENARIOS = [
    "amount_spike", "velocity_burst", "structuring", "night_fraud",
    "new_account_takeover", "fanout_mule", "cross_border_passthrough",
    "sim_swap_takeover", "social_engineering", "mule_passthrough",
]
N_PER_SCENARIO = 45  # nb de clients cibles par scénario de fraude

# Agents "préférés" : dans la réalité, un client revient chez le même agent de quartier
# plutôt que d'en choisir un au hasard à chaque opération — ce qui concentre le volume
# sur un sous-ensemble d'agents plutôt que de l'étaler uniformément (cf. discussion
# produit : un agent Wave-like traite couramment 20+ opérations/heure en heure de pointe).
PREFERRED_AGENT_USAGE_RATE = 0.85
# Fenêtres de forte affluence partagées par toute la clientèle locale d'un pays (matin,
# pause déjeuner, sortie de travail) — sans ça, les habitudes horaires individuelles de
# chaque client (habitual_hour) restent trop dispersées pour produire de vrais pics.
AGENT_PEAK_HOURS = [8, 13, 18]
AGENT_PEAK_HOUR_PROBABILITY = 0.55


def _amount_in_local_currency(baseline_xof: float, currency: str) -> float:
    """Convertit un montant baseline (équivalent XOF) vers la devise locale, pour que les
    montants générés aient un ordre de grandeur plausible par pays."""
    return baseline_xof / APPROX_XOF_PER_UNIT.get(currency, 1.0)


@dataclass
class CustomerProfile:
    phone: str
    full_name: str
    kyc_level: str
    customer_type: str
    operator: str
    country: str
    currency: str
    home_city: str
    account_created_at: datetime
    scale: float
    regular_receivers: list[str] = field(default_factory=list)
    habitual_hour: int = 12
    preferred_agent_id: str | None = None


def build_customers(n: int, agents_by_country: dict[str, list["Agent"]]) -> list[CustomerProfile]:
    customers = []
    for _ in range(n):
        customer_type = random.choices(CUSTOMER_TYPES, weights=CUSTOMER_TYPE_WEIGHTS)[0]
        country = random.choices(COUNTRY_NAMES, weights=COUNTRY_W)[0]
        currency = currency_for_country(country)
        cities, city_weights = CITIES_BY_COUNTRY[country]

        # 4% des comptes sont très récents (créés pendant la fenêtre de simulation) :
        # cible naturelle pour le scénario "new_account_takeover".
        if random.random() < 0.04:
            created_at = SIM_START + timedelta(days=random.uniform(0, SIM_DAYS - 1))
        else:
            created_at = NOW - timedelta(days=random.uniform(35, 900))

        phone, operator = random_phone_for_country(country)
        local_agents = agents_by_country.get(country, [])
        profile = CustomerProfile(
            phone=phone,
            full_name=fake.name(),
            kyc_level=random.choices(KYC_LEVELS, weights=KYC_WEIGHTS)[0],
            customer_type=customer_type,
            operator=operator,
            country=country,
            currency=currency,
            home_city=random.choices(cities, weights=city_weights)[0],
            account_created_at=created_at,
            scale=CUSTOMER_TYPE_SCALE[customer_type] * random.uniform(0.7, 1.4),
            habitual_hour=random.randint(8, 21),
            preferred_agent_id=random.choice(local_agents).agent_id if local_agents else None,
        )
        n_contacts = random.randint(2, 6)
        contacts = []
        for _ in range(n_contacts):
            if random.random() < CROSS_BORDER_CONTACT_RATE:
                other_country = random.choice([c for c in COUNTRY_NAMES if c != country])
                contacts.append(random_phone_for_country(other_country)[0])
            else:
                contacts.append(random_phone_for_country(country)[0])
        profile.regular_receivers = contacts
        customers.append(profile)
    return customers


@dataclass
class Agent:
    agent_id: str
    country: str
    city: str


def build_agents() -> list[Agent]:
    """Pool d'agents Mobile Money (cash-in/cash-out), réparti par pays proportionnellement
    à COUNTRY_WEIGHTS. Densité volontairement plus faible qu'un simple "un agent pour
    quelques clients" : dans la réalité, un agent de quartier sert une base large de
    clients qui reviennent régulièrement, ce qui concentre le volume et produit de vrais
    pics de fréquentation (cf. PREFERRED_AGENT_USAGE_RATE) plutôt qu'un trafic étalé et
    plafonné artificiellement bas."""
    agents = []
    counter = 1
    for country in COUNTRY_NAMES:
        cities, city_weights = CITIES_BY_COUNTRY[country]
        n_agents = max(1, round(COUNTRY_WEIGHTS[country] * 20))
        for _ in range(n_agents):
            city = random.choices(cities, weights=city_weights)[0]
            agents.append(Agent(agent_id=f"AGT-{counter:05d}", country=country, city=city))
            counter += 1
    return agents


def sample_amount(transaction_type: str, scale: float, currency: str) -> float:
    baseline = _amount_in_local_currency(TYPE_BASELINE_AMOUNT_XOF[transaction_type] * scale, currency)
    amount = np.random.lognormal(mean=np.log(baseline), sigma=0.6)
    return float(np.clip(amount, baseline * 0.01, baseline * 100))


def sample_timestamp(profile: CustomerProfile, *, agent_mediated: bool = False) -> datetime:
    day_offset = random.uniform(0, SIM_DAYS)
    ts = SIM_START + timedelta(days=day_offset)

    # Biais de paie : recentre la date (même mois) sur les 5 premiers ou 5 derniers jours,
    # pour que le dataset contienne une vraie saisonnalité mensuelle à apprendre plutôt
    # qu'un volume uniformément réparti sur la fenêtre de simulation.
    if random.random() < PAYDAY_BIAS_PROB:
        _, days_in_month = calendar.monthrange(ts.year, ts.month)
        day = random.randint(1, 5) if random.random() < 0.5 else random.randint(days_in_month - 5, days_in_month)
        candidate = ts.replace(day=day)
        if SIM_START <= candidate <= NOW:
            ts = candidate

    # Une opération en agence suit les heures d'affluence partagées par toute la
    # clientèle locale (matin, pause déjeuner, sortie de travail) plutôt que la seule
    # habitude individuelle du client — sans ça, le volume par agent reste artificiellement
    # étalé et ne produit jamais de vrai pic horaire (cf. AGENT_PEAK_HOURS).
    if agent_mediated and random.random() < AGENT_PEAK_HOUR_PROBABILITY:
        hour = int(np.clip(np.random.normal(random.choice(AGENT_PEAK_HOURS), 0.6), 0, 23))
    else:
        hour = int(np.clip(np.random.normal(profile.habitual_hour, 3), 0, 23))
    return ts.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))


def generate_normal_transactions(profile: CustomerProfile, agents_by_country: dict[str, list[Agent]]) -> list[dict]:
    txs = []
    days_active = max((NOW - profile.account_created_at).days, 1)
    rate_per_day = {"individual": 0.6, "merchant": 4.0, "agent": 7.0}[profile.customer_type]
    n_tx = np.random.poisson(rate_per_day * min(days_active, SIM_DAYS))
    local_agents = agents_by_country.get(profile.country, [])

    for _ in range(n_tx):
        transaction_type = random.choices(TRANSACTION_TYPES, weights=TRANSACTION_TYPE_WEIGHTS)[0]

        # Retrait : toujours en agence (impossible de sortir du cash depuis l'app seule).
        # Dépôt : agence (cash physique) ou app-direct (compte Mobile money externe lié) —
        # deux façons réelles d'alimenter un wallet, cf. discussion produit.
        agent_id = None
        channel = "mobile_app"
        if transaction_type == "withdrawal" or (
            transaction_type == "deposit" and random.random() < DEPOSIT_AGENT_SHARE
        ):
            if local_agents:
                use_preferred = profile.preferred_agent_id and random.random() < PREFERRED_AGENT_USAGE_RATE
                agent_id = profile.preferred_agent_id if use_preferred else random.choice(local_agents).agent_id
                channel = "agent"

        ts = sample_timestamp(profile, agent_mediated=channel == "agent")
        if ts < profile.account_created_at:
            continue

        if transaction_type in AGENT_MEDIATED_TYPES:
            # Cash-in/cash-out : le client transige avec lui-même (le "bénéficiaire" du
            # dépôt/retrait est le client lui-même côté portefeuille), que ce soit en
            # agence ou en app-direct.
            receiver = profile.phone
        elif random.random() < 0.85:
            receiver = random.choice(profile.regular_receivers)
        elif random.random() < CROSS_BORDER_ADHOC_RATE / 0.15:
            other_country = random.choice([c for c in COUNTRY_NAMES if c != profile.country])
            receiver = random_phone_for_country(other_country)[0]
        else:
            receiver = random_phone_for_country(profile.country)[0]

        amount = sample_amount(transaction_type, profile.scale, profile.currency)
        # Effet de paie : les particuliers reçoivent/dépensent davantage en début et fin
        # de mois (salaires, loyers, factures) — un pattern global que le modèle doit
        # apprendre à distinguer d'une anomalie individuelle.
        if (
            profile.customer_type == "individual"
            and transaction_type in PAYDAY_ELIGIBLE_TYPES
            and is_payday_window(ts)
        ):
            amount *= random.uniform(*PAYDAY_AMOUNT_MULTIPLIER_RANGE)

        txs.append({
            "sender_phone": profile.phone,
            "receiver_phone": receiver,
            "amount": round(amount, 2),
            "currency": profile.currency,
            "transaction_type": transaction_type,
            "channel": channel,
            "timestamp": ts,
            "sender_city": profile.home_city,
            "device_id": f"DEV-{abs(hash(profile.phone)) % 100000}",
            "agent_id": agent_id,
            "is_fraud": 0,
            "fraud_scenario": "",
        })
    return txs


def generate_fraud_transactions(
    profile: CustomerProfile, scenario: str, agents_by_country: dict[str, list[Agent]]
) -> list[dict]:
    txs = []

    def base_tx(ts, receiver, amount, ttype="transfer", currency=None, device_id=None):
        # transfer est toujours en app (wallet-to-wallet, jamais physique) ; withdrawal
        # nécessite un agent — les scénarios ci-dessous injectent principalement des
        # transferts frauduleux, cohérent avec channel="mobile_app" par défaut.
        return {
            "sender_phone": profile.phone,
            "receiver_phone": receiver,
            "amount": round(amount, 2),
            "currency": currency or profile.currency,
            "transaction_type": ttype,
            "channel": "mobile_app",
            "timestamp": ts,
            "sender_city": profile.home_city,
            "device_id": device_id or f"DEV-{abs(hash(profile.phone + scenario)) % 100000}",
            "agent_id": None,
            "is_fraud": 1,
            "fraud_scenario": scenario,
        }

    event_day = random.uniform(5, SIM_DAYS - 1)
    event_ts = SIM_START + timedelta(days=event_day)
    baseline = _amount_in_local_currency(TYPE_BASELINE_AMOUNT_XOF["transfer"] * profile.scale, profile.currency)

    if scenario == "amount_spike":
        # Compte compromis effectuant un virement P2P d'un montant anormal (identifiants
        # volés, achat non autorisé revendu en cash via un tiers).
        amount = baseline * random.uniform(6, 15)
        txs.append(base_tx(event_ts, random_phone_for_country(profile.country)[0], amount))

    elif scenario == "velocity_burst":
        n = random.randint(3, 6)
        for i in range(n):
            ts = event_ts + timedelta(minutes=i * random.uniform(0.5, 2.5))
            amount = baseline * random.uniform(2, 6)
            txs.append(base_tx(ts, random_phone_for_country(profile.country)[0], amount))

    elif scenario == "structuring":
        n = random.randint(4, 8)
        receivers = [random_phone_for_country(profile.country)[0] for _ in range(random.randint(1, 2))]
        ceiling_local = _amount_in_local_currency(500_000, profile.currency)
        for i in range(n):
            ts = event_ts + timedelta(minutes=i * random.uniform(3, 9))
            amount = random.uniform(ceiling_local * 0.7, ceiling_local * 0.98)
            txs.append(base_tx(ts, random.choice(receivers), amount))

    elif scenario == "night_fraud":
        ts = event_ts.replace(hour=random.randint(1, 4))
        amount = baseline * random.uniform(4, 10)
        txs.append(base_tx(ts, random_phone_for_country(profile.country)[0], amount))

    elif scenario == "new_account_takeover":
        max_hours_available = max((NOW - profile.account_created_at).total_seconds() / 3600, 1)
        ts = profile.account_created_at + timedelta(
            hours=random.uniform(1, min(48, max_hours_available))
        )
        amount = _amount_in_local_currency(random.uniform(150_000, 800_000), profile.currency)
        txs.append(base_tx(ts, random_phone_for_country(profile.country)[0], amount))

    elif scenario == "fanout_mule":
        n = random.randint(4, 8)
        for i in range(n):
            ts = event_ts + timedelta(minutes=i * random.uniform(4, 12))
            amount = baseline * random.uniform(1, 3)
            txs.append(base_tx(ts, random_phone_for_country(profile.country)[0], amount))

    elif scenario == "cross_border_passthrough":
        # Contournement via un pays tiers : reçoit d'un pays A, renvoie vers un pays C
        # différent, très vite et pour un montant quasi identique.
        other_countries = [c for c in COUNTRY_NAMES if c != profile.country]
        origin_country = random.choice(other_countries)
        destination_country = random.choice([c for c in other_countries if c != origin_country])
        incoming_amount_xof = baseline * random.uniform(3, 8)
        incoming_amount_local = incoming_amount_xof  # baseline déjà en devise du profil (cible)
        incoming_sender_phone, _ = random_phone_for_country(origin_country)

        # jambe entrante : un tiers d'un autre pays envoie au client cible (transaction
        # normale de son point de vue, non labellisée fraude en tant que telle)
        txs.append({
            "sender_phone": incoming_sender_phone,
            "receiver_phone": profile.phone,
            "amount": round(incoming_amount_local, 2),
            "currency": currency_for_country(origin_country),
            "transaction_type": "transfer",
            "channel": "mobile_app",
            "timestamp": event_ts,
            "sender_city": "",
            "device_id": f"DEV-EXT-{abs(hash(incoming_sender_phone)) % 100000}",
            "agent_id": None,
            "is_fraud": 0,
            "fraud_scenario": "",
        })

        # jambe sortante : renvoi rapide vers un pays tiers différent, montant similaire
        outgoing_ts = event_ts + timedelta(minutes=random.uniform(10, 45))
        outgoing_receiver, _ = random_phone_for_country(destination_country)
        outgoing_amount = incoming_amount_local * random.uniform(0.85, 1.05)
        txs.append(base_tx(outgoing_ts, outgoing_receiver, outgoing_amount))

    elif scenario == "sim_swap_takeover":
        # Changement brutal d'appareil sur un compte établi (SIM swap / prise de
        # contrôle), suivi d'un virement vers un bénéficiaire inconnu. Device_id
        # délibérément distinct du device habituel du client (cf. rules.SIM_SWAP_SIGNAL).
        rare_device = f"DEV-RARE-{random.randint(0, 99999):05d}"
        amount = _amount_in_local_currency(random.uniform(150_000, 1_200_000), profile.currency)
        txs.append(base_tx(
            event_ts, random_phone_for_country(profile.country)[0], amount, device_id=rare_device,
        ))

    elif scenario == "social_engineering":
        # Client établi, stable, qui effectue en une seule fois (pas de rafale) un
        # virement très supérieur à son habitude vers un inconnu, depuis son appareil
        # habituel (pas de compromission technique) — profil d'une victime guidée par
        # téléphone plutôt que d'un compte piraté (cf. rules.SOCIAL_ENGINEERING_SIGNAL).
        usual_device = f"DEV-{abs(hash(profile.phone)) % 100000}"
        amount = baseline * random.uniform(9, 16)
        txs.append(base_tx(event_ts, random_phone_for_country(profile.country)[0], amount, device_id=usual_device))

    elif scenario == "mule_passthrough":
        # Compte mule récidiviste : encaisse (dépôt en agence ou réception d'un tiers)
        # puis ressort l'argent quasi aussitôt, de façon répétée sur plusieurs semaines,
        # depuis une source qui se répète (le complice qui alimente le compte) — c'est la
        # répétition + la concentration de la source qui distingue le mule d'un usage
        # normal ou d'un commerce (cf. rules.MULE_PASSTHROUGH_PATTERN).
        local_agents = agents_by_country.get(profile.country, [])
        via_agent = bool(local_agents) and random.random() < 0.5
        funding_agent = random.choice(local_agents) if via_agent else None
        funder_phone, _ = random_phone_for_country(profile.country)

        n_cycles = random.randint(4, 7)
        available_days = range(5, SIM_DAYS - 1)
        cycle_days = sorted(random.sample(available_days, k=min(n_cycles, len(available_days))))

        for day in cycle_days:
            in_ts = SIM_START + timedelta(days=day, hours=random.uniform(8, 20))
            amount = baseline * random.uniform(1.5, 4)

            if funding_agent is not None:
                txs.append({
                    "sender_phone": profile.phone,
                    "receiver_phone": profile.phone,
                    "amount": round(amount, 2),
                    "currency": profile.currency,
                    "transaction_type": "deposit",
                    "channel": "agent",
                    "timestamp": in_ts,
                    "sender_city": profile.home_city,
                    "device_id": f"DEV-{abs(hash(profile.phone)) % 100000}",
                    "agent_id": funding_agent.agent_id,
                    "is_fraud": 0,
                    "fraud_scenario": "",
                })
            else:
                txs.append({
                    "sender_phone": funder_phone,
                    "receiver_phone": profile.phone,
                    "amount": round(amount, 2),
                    "currency": profile.currency,
                    "transaction_type": "transfer",
                    "channel": "mobile_app",
                    "timestamp": in_ts,
                    "sender_city": "",
                    "device_id": f"DEV-EXT-{abs(hash(funder_phone)) % 100000}",
                    "agent_id": None,
                    "is_fraud": 0,
                    "fraud_scenario": "",
                })

            out_ts = in_ts + timedelta(minutes=random.uniform(5, 45))
            out_amount = amount * random.uniform(0.8, 1.0)
            if local_agents and random.random() < 0.5:
                out_agent = random.choice(local_agents)
                txs.append({
                    "sender_phone": profile.phone,
                    "receiver_phone": profile.phone,
                    "amount": round(out_amount, 2),
                    "currency": profile.currency,
                    "transaction_type": "withdrawal",
                    "channel": "agent",
                    "timestamp": out_ts,
                    "sender_city": profile.home_city,
                    "device_id": f"DEV-{abs(hash(profile.phone)) % 100000}",
                    "agent_id": out_agent.agent_id,
                    "is_fraud": 1,
                    "fraud_scenario": scenario,
                })
            else:
                txs.append(base_tx(out_ts, random_phone_for_country(profile.country)[0], out_amount))

    return [t for t in txs if t["timestamp"] >= profile.account_created_at]


def assign_fraud_targets(customers: list[CustomerProfile]) -> list[tuple[CustomerProfile, str]]:
    """Choisit les clients cibles par scénario, en réservant les comptes récents au
    scénario new_account_takeover (sinon ce scénario n'a presque aucune chance d'être
    tiré sur un compte compatible par pur hasard)."""

    recent = [c for c in customers if 0 <= (NOW - c.account_created_at).days <= SIM_DAYS]
    recent_phones = {c.phone for c in recent}
    others = [c for c in customers if c.phone not in recent_phones]

    assignments: list[tuple[CustomerProfile, str]] = []

    n_takeover = min(N_PER_SCENARIO, len(recent))
    for c in random.sample(recent, k=n_takeover):
        assignments.append((c, "new_account_takeover"))

    other_scenarios = [s for s in FRAUD_SCENARIOS if s != "new_account_takeover"]
    random.shuffle(others)
    pool = iter(others)
    for scenario in other_scenarios:
        for _ in range(N_PER_SCENARIO):
            c = next(pool, None)
            if c is None:
                break
            assignments.append((c, scenario))

    return assignments


def apply_balance_simulation(all_txs: list[dict], customers: list[CustomerProfile]) -> None:
    """Simule un solde de portefeuille par client en rejouant ses transactions dans
    l'ordre chronologique (avant/après, émetteur uniquement) — inspiré des travaux de
    référence sur la simulation Mobile Money (PaySim, MoMTSim), où le solde est l'une des
    variables les plus prédictives (ex : compte vidé à zéro). Modifie `all_txs` en place.
    """
    OUTFLOW_TYPES = {"withdrawal", "transfer"}
    DRAIN_SCENARIOS = {"amount_spike", "new_account_takeover", "sim_swap_takeover"}

    scale_by_phone = {c.phone: c.scale for c in customers}
    currency_by_phone = {c.phone: c.currency for c in customers}

    by_sender: dict[str, list[dict]] = {}
    for tx in all_txs:
        by_sender.setdefault(tx["sender_phone"], []).append(tx)

    for phone, txs in by_sender.items():
        txs.sort(key=lambda t: t["timestamp"])
        scale = scale_by_phone.get(phone, 1.0)
        currency = currency_by_phone.get(phone, "XOF")
        baseline = _amount_in_local_currency(50_000 * scale, currency)
        balance = float(np.random.lognormal(mean=np.log(max(baseline, 1)), sigma=0.7))

        for tx in txs:
            amount = tx["amount"]
            is_drain = tx["fraud_scenario"] in DRAIN_SCENARIOS
            if tx["transaction_type"] in OUTFLOW_TYPES:
                if is_drain:
                    balance_before = amount * random.uniform(1.0, 1.05)
                    balance_after = random.uniform(0, baseline * 0.01)
                else:
                    balance_before = max(balance, amount * random.uniform(1.15, 3.0))
                    balance_after = balance_before - amount
            else:  # deposit : entrée d'argent
                balance_before = balance
                balance_after = balance + amount
            balance = balance_after
            tx["balance_before_sender"] = round(balance_before, 2)
            tx["balance_after_sender"] = round(balance_after, 2)


def main():
    agents = build_agents()
    agents_by_country: dict[str, list[Agent]] = {}
    for a in agents:
        agents_by_country.setdefault(a.country, []).append(a)

    customers = build_customers(NUM_CUSTOMERS, agents_by_country)

    all_txs: list[dict] = []

    for profile in customers:
        all_txs.extend(generate_normal_transactions(profile, agents_by_country))

    for profile, scenario in assign_fraud_targets(customers):
        all_txs.extend(generate_fraud_transactions(profile, scenario, agents_by_country))

    apply_balance_simulation(all_txs, customers)

    df_tx = pd.DataFrame(all_txs).sort_values("timestamp").reset_index(drop=True)
    df_customers = pd.DataFrame([{
        "phone": c.phone,
        "full_name": c.full_name,
        "kyc_level": c.kyc_level,
        "customer_type": c.customer_type,
        "operator": c.operator,
        "country": c.country,
        "currency": c.currency,
        "home_city": c.home_city,
        "account_created_at": c.account_created_at,
    } for c in customers])
    df_agents = pd.DataFrame([{"agent_id": a.agent_id, "country": a.country, "city": a.city} for a in agents])

    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    df_customers.to_csv(data_dir / "customers.csv", index=False)
    df_tx.to_csv(data_dir / "transactions.csv", index=False)
    df_agents.to_csv(data_dir / "agents.csv", index=False)

    print(f"Clients générés        : {len(df_customers)}")
    print(f"Agents générés         : {len(df_agents)}")
    print(f"Transactions générées  : {len(df_tx)}")
    print(f"Transactions frauduleuses : {int(df_tx['is_fraud'].sum())} "
          f"({df_tx['is_fraud'].mean() * 100:.2f}%)")
    print(df_tx.groupby("fraud_scenario").size().sort_values(ascending=False))
    print("\nFraude par type de transaction :")
    print(df_tx.groupby("transaction_type")["is_fraud"].agg(["sum", "mean"]))
    print("\nDistribution des types de transaction :")
    print(df_tx["transaction_type"].value_counts(normalize=True).round(3))
    print("\nDistribution des canaux :")
    print(df_tx["channel"].value_counts(normalize=True).round(3))
    print("\nTransactions avec agent_id :", df_tx["agent_id"].notna().sum(), "/", len(df_tx))

    agent_tx = df_tx[df_tx["agent_id"].notna()].copy()
    agent_tx["hour_bucket"] = agent_tx["timestamp"].dt.floor("h")
    per_agent_hour = agent_tx.groupby(["agent_id", "hour_bucket"]).size()
    print("\nVolume horaire par agent (heures avec au moins 1 opération) :")
    print(per_agent_hour.describe(percentiles=[.5, .75, .9, .95, .99]))
    print("\nRépartition pays (clients) :")
    print(df_customers["country"].value_counts())
    print("\nRépartition opérateurs (clients) :")
    print(df_customers["operator"].value_counts())
    print("\nExemples de numéros générés :")
    print(df_customers[["phone", "country", "currency"]].sample(8, random_state=1).to_string(index=False))

    sender_country = df_tx.merge(
        df_customers[["phone", "country"]], left_on="sender_phone", right_on="phone", how="left"
    )["country"]
    receiver_country = df_tx["receiver_phone"].map(country_from_phone)
    n_cross = (sender_country != receiver_country).sum()
    print(f"\nTransactions transfrontalières (approx.) : {n_cross} / {len(df_tx)}")


if __name__ == "__main__":
    main()
