"""Peuple la base live (data/novaris.db) avec des transactions réalistes en passant par
le vrai pipeline d'analyse (règles + ML + SHAP), exactement comme le ferait l'API — pour
que le dashboard Admin ait des données à afficher sans attendre de vrai trafic.

Contrairement à scripts/generate_synthetic_data.py (qui génère un CSV massif pour
l'entraînement du modèle), ce script écrit directement dans la base servie par l'API, sur
une fenêtre de 7 jours glissante (alignée sur GET /api/v1/dashboard/trend).

Inclut volontairement quelques clients KYC complet qui possèdent DEUX comptes (numéros/
opérateurs/pays différents) partageant le même national_id, pour illustrer le cas
d'identité inter-réseaux discuté pour l'écran Graphe : le téléphone seul ne suffit pas à
identifier une personne, le national_id (quand le KYC est fait) le permet.
"""

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.transaction_monitoring.models import Customer
from modules.transaction_monitoring.schemas import TransactionIn
from modules.transaction_monitoring.service import TransactionMonitoringService
from shared.database.session import session_scope
from shared.utils.id_generator import generate_customer_id, generate_national_id
from shared.utils.phone import random_phone_for_country

random.seed(7)

HOME_CITY = {
    "Côte d'Ivoire": "Abidjan",
    "Sénégal": "Dakar",
    "Ghana": "Accra",
    "Cameroun": "Douala",
    "Kenya": "Nairobi",
    "Mali": "Bamako",
    "Nigeria": "Lagos",
    "Bénin": "Cotonou",
}

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


def _make_customer(country: str, *, kyc_level: str, national_id: str | None, created_days_ago: int) -> Customer:
    phone, operator = random_phone_for_country(country)
    return Customer(
        customer_id=generate_customer_id(),
        phone=phone,
        full_name="Client démo",
        kyc_level=kyc_level,
        national_id=national_id,
        customer_type="individual",
        operator=operator,
        country=country,
        home_city=HOME_CITY.get(country, "Abidjan"),
        account_created_at=NOW - timedelta(days=created_days_ago),
    )


def seed_customers(db) -> list[Customer]:
    customers: list[Customer] = []

    # Clients KYC basique (téléphone seul comme identifiant) — majorité réaliste.
    for _ in range(14):
        country = random.choices(
            ["Côte d'Ivoire", "Sénégal", "Ghana", "Cameroun", "Kenya", "Mali"],
            weights=[0.45, 0.15, 0.12, 0.1, 0.1, 0.08],
        )[0]
        customers.append(_make_customer(country, kyc_level="basic", national_id=None, created_days_ago=random.randint(30, 900)))

    # Clients KYC complet, comptes uniques (national_id renseigné, un seul compte).
    for _ in range(6):
        country = random.choice(["Côte d'Ivoire", "Sénégal", "Ghana", "Cameroun"])
        customers.append(
            _make_customer(
                country,
                kyc_level=random.choice(["standard", "premium"]),
                national_id=generate_national_id(),
                created_days_ago=random.randint(60, 900),
            )
        )

    # Même personne, plusieurs comptes (national_id partagé) — le cas qui motive la
    # résolution d'identité inter-réseaux : deux numéros/opérateurs/pays, un seul humain.
    shared_pairs = [
        ("Côte d'Ivoire", "Sénégal"),
        ("Côte d'Ivoire", "Ghana"),
        ("Cameroun", "Côte d'Ivoire"),
    ]
    for country_a, country_b in shared_pairs:
        shared_id = generate_national_id()
        kyc = random.choice(["standard", "premium"])
        customers.append(_make_customer(country_a, kyc_level=kyc, national_id=shared_id, created_days_ago=random.randint(200, 900)))
        customers.append(_make_customer(country_b, kyc_level=kyc, national_id=shared_id, created_days_ago=random.randint(30, 180)))

    db.add_all(customers)
    db.flush()
    return customers


def analyze(service: TransactionMonitoringService, **kwargs) -> str:
    payload = TransactionIn(**kwargs)
    result = service.analyze(payload)
    return result.decision


def seed_transactions(db, customers: list[Customer]) -> dict[str, int]:
    service = TransactionMonitoringService(db)
    counts: dict[str, int] = {}

    def record(decision: str) -> None:
        counts[decision] = counts.get(decision, 0) + 1

    # Trafic normal réparti sur les 6 derniers jours + aujourd'hui.
    for day_offset in range(6, -1, -1):
        day_start = NOW - timedelta(days=day_offset)
        volume = random.randint(10, 18)
        for _ in range(volume):
            sender = random.choice(customers)
            receiver_country = random.choices(
                [sender.country, "Sénégal", "Ghana", "Côte d'Ivoire"],
                weights=[0.75, 0.1, 0.08, 0.07],
            )[0]
            receiver_phone, _ = random_phone_for_country(receiver_country)
            hour = random.choices(range(24), weights=[1 if h not in (7, 8, 12, 18, 19, 20) else 4 for h in range(24)])[0]
            ts = day_start.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))
            amount = round(random.choice([2000, 5000, 8000, 15000, 25000, 40000, 60000]) * random.uniform(0.85, 1.2))
            tx_type = random.choices(
                ["transfer", "deposit", "withdrawal"],
                weights=[0.40, 0.32, 0.28],
            )[0]
            channel = "agent" if tx_type == "withdrawal" or (tx_type == "deposit" and random.random() < 0.65) else "mobile_app"
            decision = analyze(
                service,
                sender_phone=sender.phone,
                receiver_phone=receiver_phone,
                amount=amount,
                transaction_type=tx_type,
                channel=channel,
                agent_id="AG-DEMO01" if channel == "agent" else None,
                sender_city=sender.home_city,
                device_id=f"DEV-{sender.customer_id[-6:]}",
                timestamp=ts,
            )
            record(decision)

    # Quelques scénarios volontairement à risque, pour que le dashboard/graphe aient des
    # dossiers intéressants à montrer (pas juste des ALLOW).
    flagged_senders = random.sample(customers, k=5)

    # 1) Montant élevé, nouveau destinataire, nuit — devrait remonter en REVIEW/TEMPORARY_BLOCK.
    s = flagged_senders[0]
    receiver_phone, _ = random_phone_for_country(s.country)
    decision = analyze(
        service,
        sender_phone=s.phone,
        receiver_phone=receiver_phone,
        amount=780000,
        transaction_type="transfer",
        channel="mobile_app",
        sender_city=s.home_city,
        timestamp=NOW.replace(hour=2, minute=40),
    )
    record(decision)

    # 2) Cross-border passthrough : réception puis renvoi rapide vers un autre pays.
    s = flagged_senders[1]
    mule_receiver, _ = random_phone_for_country("Sénégal")
    analyze(
        service,
        sender_phone=mule_receiver,
        receiver_phone=s.phone,
        amount=300000,
        transaction_type="transfer",
        channel="mobile_app",
        sender_city=HOME_CITY["Sénégal"],
        timestamp=NOW - timedelta(minutes=20),
    )
    onward_receiver, _ = random_phone_for_country("Ghana")
    decision = analyze(
        service,
        sender_phone=s.phone,
        receiver_phone=onward_receiver,
        amount=295000,
        transaction_type="transfer",
        channel="mobile_app",
        sender_city=s.home_city,
        timestamp=NOW - timedelta(minutes=5),
    )
    record(decision)

    # 3) Fan-out : un émetteur vers plusieurs bénéficiaires distincts en quelques minutes.
    s = flagged_senders[2]
    for i in range(6):
        receiver_phone, _ = random_phone_for_country(s.country)
        decision = analyze(
            service,
            sender_phone=s.phone,
            receiver_phone=receiver_phone,
            amount=random.randint(45000, 65000),
            transaction_type="transfer",
            channel="mobile_app",
            sender_city=s.home_city,
            timestamp=NOW - timedelta(minutes=30 - i * 4),
        )
        record(decision)

    # 4) Compte mule récidiviste : cycles dépôt (même agent) -> retrait rapide, répétés
    # sur plusieurs semaines — cf. rules.MULE_PASSTHROUGH_PATTERN.
    s = flagged_senders[3]
    agent_id = "AG-DEMO01"
    for i, days_ago in enumerate([28, 21, 14, 7, 1]):
        cycle_start = NOW - timedelta(days=days_ago, hours=random.uniform(0, 3))
        amount = random.randint(90000, 140000)
        analyze(
            service,
            sender_phone=s.phone,
            receiver_phone=s.phone,
            amount=amount,
            transaction_type="deposit",
            channel="agent",
            agent_id=agent_id,
            sender_city=s.home_city,
            timestamp=cycle_start,
        )
        decision = analyze(
            service,
            sender_phone=s.phone,
            receiver_phone=s.phone,
            amount=round(amount * random.uniform(0.85, 0.98)),
            transaction_type="withdrawal",
            channel="agent",
            agent_id=agent_id,
            sender_city=s.home_city,
            timestamp=cycle_start + timedelta(minutes=random.uniform(10, 40)),
        )
        record(decision)

    return counts


def main() -> None:
    with session_scope() as db:
        customers = seed_customers(db)
        db.commit()
        counts = seed_transactions(db, customers)

    print(f"Clients créés : {len(customers)}")
    print("Répartition des décisions :")
    for decision, count in sorted(counts.items()):
        print(f"  {decision}: {count}")


if __name__ == "__main__":
    main()
