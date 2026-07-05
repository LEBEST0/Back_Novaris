"""Génère un dataset synthétique réaliste de transactions Mobile Money (Afrique de l'Ouest).

Aucune donnée personnelle réelle n'est utilisée (cf. document produit : "Données
synthétiques : créer des transactions réalistes ... sans données personnelles").

Produit deux fichiers dans data/ :
- customers.csv   : les titulaires de portefeuille suivis (profil de comportement habituel)
- transactions.csv: le flux de transactions, normal + scénarios de fraude injectés et labellisés

Usage:
    python scripts/generate_synthetic_data.py
"""

import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import calendar

import numpy as np
import pandas as pd
from faker import Faker

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules.transaction_monitoring.feature_engineering import is_payday_window  # noqa: E402
from shared.utils.phone import random_ci_phone  # noqa: E402

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

# Marché initial de la roadmap produit : Côte d'Ivoire uniquement. Villes réelles, pondérées
# approximativement par poids démographique/économique (Abidjan très majoritaire).
CITIES = ["Abidjan", "Bouaké", "Yamoussoukro", "San-Pédro", "Korhogo", "Daloa", "Man", "Gagnoa"]
CITY_WEIGHTS = [0.45, 0.12, 0.08, 0.08, 0.07, 0.08, 0.06, 0.06]
KYC_LEVELS = ["basic", "standard", "premium"]
KYC_WEIGHTS = [0.55, 0.35, 0.10]
CUSTOMER_TYPES = ["individual", "merchant", "agent"]
CUSTOMER_TYPE_WEIGHTS = [0.85, 0.10, 0.05]
TRANSACTION_TYPES = [
    "deposit", "withdrawal", "transfer", "merchant_payment", "airtime_purchase", "bill_payment",
]
CHANNELS = ["mobile_app", "ussd", "agent", "web", "api"]
CHANNEL_WEIGHTS = [0.45, 0.30, 0.15, 0.05, 0.05]

# Montant "baseline" moyen en XOF par type de transaction (avant application du facteur client)
TYPE_BASELINE_AMOUNT = {
    "airtime_purchase": 1_500,
    "bill_payment": 15_000,
    "deposit": 40_000,
    "withdrawal": 35_000,
    "transfer": 30_000,
    "merchant_payment": 20_000,
}
CUSTOMER_TYPE_SCALE = {"individual": 1.0, "merchant": 8.0, "agent": 15.0}

FRAUD_SCENARIOS = [
    "amount_spike", "velocity_burst", "structuring", "night_fraud",
    "new_account_takeover", "fanout_mule",
]
N_PER_SCENARIO = 45  # nb de clients cibles par scénario de fraude (~18% de clients frauduleux)


@dataclass
class CustomerProfile:
    phone: str
    full_name: str
    kyc_level: str
    customer_type: str
    operator: str
    home_city: str
    account_created_at: datetime
    scale: float
    regular_receivers: list[str] = field(default_factory=list)
    habitual_hour: int = 12


def build_customers(n: int) -> list[CustomerProfile]:
    customers = []
    for _ in range(n):
        customer_type = random.choices(CUSTOMER_TYPES, weights=CUSTOMER_TYPE_WEIGHTS)[0]
        # 4% des comptes sont très récents (créés pendant la fenêtre de simulation) :
        # cible naturelle pour le scénario "new_account_takeover".
        if random.random() < 0.04:
            created_at = SIM_START + timedelta(days=random.uniform(0, SIM_DAYS - 1))
        else:
            created_at = NOW - timedelta(days=random.uniform(35, 900))

        phone, operator = random_ci_phone()
        profile = CustomerProfile(
            phone=phone,
            full_name=fake.name(),
            kyc_level=random.choices(KYC_LEVELS, weights=KYC_WEIGHTS)[0],
            customer_type=customer_type,
            operator=operator,
            home_city=random.choices(CITIES, weights=CITY_WEIGHTS)[0],
            account_created_at=created_at,
            scale=CUSTOMER_TYPE_SCALE[customer_type] * random.uniform(0.7, 1.4),
            habitual_hour=random.randint(8, 21),
        )
        n_contacts = random.randint(2, 6)
        # Les contacts réguliers d'un client ne sont pas forcément chez le même opérateur.
        profile.regular_receivers = [random_ci_phone()[0] for _ in range(n_contacts)]
        customers.append(profile)
    return customers


def sample_amount(transaction_type: str, scale: float) -> float:
    baseline = TYPE_BASELINE_AMOUNT[transaction_type] * scale
    amount = np.random.lognormal(mean=np.log(baseline), sigma=0.6)
    return float(np.clip(amount, 100, 5_000_000))


def sample_timestamp(profile: CustomerProfile) -> datetime:
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

    hour = int(np.clip(np.random.normal(profile.habitual_hour, 3), 0, 23))
    return ts.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))


def generate_normal_transactions(profile: CustomerProfile) -> list[dict]:
    txs = []
    days_active = max((NOW - profile.account_created_at).days, 1)
    rate_per_day = {"individual": 0.6, "merchant": 4.0, "agent": 7.0}[profile.customer_type]
    n_tx = np.random.poisson(rate_per_day * min(days_active, SIM_DAYS))

    for _ in range(n_tx):
        ts = sample_timestamp(profile)
        if ts < profile.account_created_at:
            continue
        transaction_type = random.choice(TRANSACTION_TYPES)
        receiver = (
            random.choice(profile.regular_receivers)
            if random.random() < 0.85
            else random_ci_phone()[0]
        )
        amount = sample_amount(transaction_type, profile.scale)
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
            "currency": "XOF",
            "transaction_type": transaction_type,
            "channel": random.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
            "timestamp": ts,
            "sender_city": profile.home_city,
            "device_id": f"DEV-{abs(hash(profile.phone)) % 100000}",
            "is_fraud": 0,
            "fraud_scenario": "",
        })
    return txs


def generate_fraud_transactions(profile: CustomerProfile, scenario: str) -> list[dict]:
    txs = []

    def base_tx(ts, receiver, amount, ttype="transfer"):
        return {
            "sender_phone": profile.phone,
            "receiver_phone": receiver,
            "amount": round(amount, 2),
            "currency": "XOF",
            "transaction_type": ttype,
            "channel": random.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
            "timestamp": ts,
            "sender_city": profile.home_city,
            "device_id": f"DEV-{abs(hash(profile.phone + scenario)) % 100000}",
            "is_fraud": 1,
            "fraud_scenario": scenario,
        }

    event_day = random.uniform(5, SIM_DAYS - 1)
    event_ts = SIM_START + timedelta(days=event_day)
    baseline = TYPE_BASELINE_AMOUNT["transfer"] * profile.scale

    if scenario == "amount_spike":
        amount = baseline * random.uniform(6, 15)
        txs.append(base_tx(event_ts, random_ci_phone()[0], amount))

    elif scenario == "velocity_burst":
        n = random.randint(3, 6)
        for i in range(n):
            ts = event_ts + timedelta(minutes=i * random.uniform(0.5, 2.5))
            amount = baseline * random.uniform(2, 6)
            txs.append(base_tx(ts, random_ci_phone()[0], amount))

    elif scenario == "structuring":
        n = random.randint(4, 8)
        receivers = [random_ci_phone()[0] for _ in range(random.randint(1, 2))]
        for i in range(n):
            ts = event_ts + timedelta(minutes=i * random.uniform(3, 9))
            amount = random.uniform(350_000, 490_000)
            txs.append(base_tx(ts, random.choice(receivers), amount))

    elif scenario == "night_fraud":
        ts = event_ts.replace(hour=random.randint(1, 4))
        amount = baseline * random.uniform(4, 10)
        txs.append(base_tx(ts, random_ci_phone()[0], amount))

    elif scenario == "new_account_takeover":
        max_hours_available = max((NOW - profile.account_created_at).total_seconds() / 3600, 1)
        ts = profile.account_created_at + timedelta(
            hours=random.uniform(1, min(48, max_hours_available))
        )
        amount = random.uniform(150_000, 800_000)
        txs.append(base_tx(ts, random_ci_phone()[0], amount))

    elif scenario == "fanout_mule":
        n = random.randint(4, 8)
        for i in range(n):
            ts = event_ts + timedelta(minutes=i * random.uniform(4, 12))
            amount = baseline * random.uniform(1, 3)
            txs.append(base_tx(ts, random_ci_phone()[0], amount))

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


def main():
    customers = build_customers(NUM_CUSTOMERS)
    all_txs: list[dict] = []

    for profile in customers:
        all_txs.extend(generate_normal_transactions(profile))

    for profile, scenario in assign_fraud_targets(customers):
        all_txs.extend(generate_fraud_transactions(profile, scenario))

    df_tx = pd.DataFrame(all_txs).sort_values("timestamp").reset_index(drop=True)
    df_customers = pd.DataFrame([{
        "phone": c.phone,
        "full_name": c.full_name,
        "kyc_level": c.kyc_level,
        "customer_type": c.customer_type,
        "operator": c.operator,
        "home_city": c.home_city,
        "account_created_at": c.account_created_at,
    } for c in customers])

    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    df_customers.to_csv(data_dir / "customers.csv", index=False)
    df_tx.to_csv(data_dir / "transactions.csv", index=False)

    print(f"Clients générés        : {len(df_customers)}")
    print(f"Transactions générées  : {len(df_tx)}")
    print(f"Transactions frauduleuses : {int(df_tx['is_fraud'].sum())} "
          f"({df_tx['is_fraud'].mean() * 100:.2f}%)")
    print(df_tx.groupby("fraud_scenario").size().sort_values(ascending=False))
    print("\nRépartition opérateurs (clients) :")
    print(df_customers["operator"].value_counts())
    print("\nRépartition villes (clients) :")
    print(df_customers["home_city"].value_counts())
    print("\nExemples de numéros générés :", df_customers["phone"].head(5).tolist())


if __name__ == "__main__":
    main()
