"""Peuple la base avec un compte de démonstration Amani Wallet (utilisateur, appareil de
confiance, bénéficiaires, historique fictif, profil comportemental) et le catalogue des 10
scénarios du mode démonstration (cahier des charges, section 10).

Le fingerprint de l'appareil « de confiance » est calculé avec exactement le même algorithme
que le frontend (shared/utils/device_fingerprint côté doc — voir AmaniWallet/src/lib/device.ts) :

    SHA256(local_device_uuid + "|" + platform + "|" + os_version + "|" + screen_size
           + "|" + language + "|" + timezone)

Identifiants de connexion pour la démo :
    téléphone : +2250700000001
    code PIN  : 1234
"""

import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.wallet_access.models import (
    Beneficiary,
    BehaviourProfile,
    DemoScenario,
    Device,
    WalletTransaction,
    WalletUser,
)
from shared.database.session import session_scope
from shared.utils.id_generator import (
    generate_beneficiary_id,
    generate_device_id,
    generate_user_id,
    generate_wallet_transaction_id,
)
from shared.utils.security import hash_pin

NOW = datetime.now(timezone.utc).replace(tzinfo=None)

DEMO_PHONE = "+2250700000001"
DEMO_PIN = "1234"

# Doit rester identique à AmaniWallet/src/lib/device.ts (mêmes valeurs par défaut du
# profil « appareil habituel » simulé pour le scénario NORMAL_USER).
TRUSTED_DEVICE = {
    "local_device_uuid": "demo-trusted-device-0001",
    "platform": "Android",
    "os_version": "14",
    "screen_size": "412x915",
    "language": "fr-FR",
    "timezone": "Africa/Abidjan",
    "browser": "Chrome Mobile",
}
ABIDJAN = (5.348, -4.014)
PARIS = (48.8566, 2.3522)


def compute_fingerprint(d: dict) -> str:
    raw = "|".join([
        d["local_device_uuid"], d["platform"], d["os_version"], d["screen_size"], d["language"], d["timezone"],
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


DEMO_SCENARIOS = [
    {
        "name": "NORMAL_USER",
        "description": "Appareil habituel, localisation cohérente, comportement normal — accès attendu : ALLOW.",
        "mock_signals": {
            "android_id_mock": "AND-001",
            "device_integrity_mock": "PASSED",
            "emulator_detected_mock": False,
            "root_detected_mock": False,
            "sim_changed_recently_mock": False,
            "esim_activated_recently_mock": False,
            "use_trusted_device": True,
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "NEW_DEVICE",
        "description": "Connexion depuis un appareil jamais vu — déclenche une vérification d'identité (biométrie ou liveness).",
        "mock_signals": {
            "android_id_mock": "AND-NEW-002",
            "device_integrity_mock": "PASSED",
            "emulator_detected_mock": False,
            "root_detected_mock": False,
            "sim_changed_recently_mock": False,
            "use_trusted_device": False,
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "IMPOSSIBLE_TRAVEL",
        "description": "Localisation très éloignée de la zone habituelle du client (Abidjan → Paris).",
        "mock_signals": {
            "android_id_mock": "AND-NEW-003",
            "device_integrity_mock": "PASSED",
            "emulator_detected_mock": False,
            "root_detected_mock": False,
            "sim_changed_recently_mock": False,
            "use_trusted_device": False,
            "location": {"latitude": PARIS[0], "longitude": PARIS[1]},
        },
    },
    {
        "name": "CLONED_DEVICE_ID",
        "description": "Android ID identique à celui de l'appareil de confiance, mais empreinte applicative différente — usurpation probable.",
        "mock_signals": {
            "android_id_mock": "AND-001",
            "device_integrity_mock": "PASSED",
            "emulator_detected_mock": False,
            "root_detected_mock": False,
            "sim_changed_recently_mock": False,
            "use_trusted_device": False,
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "ROOTED_DEVICE",
        "description": "Appareil rooté détecté (simulation).",
        "mock_signals": {
            "android_id_mock": "AND-NEW-004",
            "device_integrity_mock": "FAILED",
            "emulator_detected_mock": False,
            "root_detected_mock": True,
            "sim_changed_recently_mock": False,
            "use_trusted_device": False,
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "EMULATOR_DEVICE",
        "description": "Émulateur détecté (simulation) — signal fort d'automatisation frauduleuse.",
        "mock_signals": {
            "android_id_mock": "AND-NEW-005",
            "device_integrity_mock": "FAILED",
            "emulator_detected_mock": True,
            "root_detected_mock": False,
            "sim_changed_recently_mock": False,
            "use_trusted_device": False,
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "RECENT_SIM_SWAP",
        "description": "SIM/eSIM changée récemment (8h) — fenêtre classique de prise de contrôle de compte.",
        "mock_signals": {
            "android_id_mock": "AND-001",
            "device_integrity_mock": "PASSED",
            "emulator_detected_mock": False,
            "root_detected_mock": False,
            "sim_changed_recently_mock": True,
            "esim_activated_recently_mock": True,
            "sim_age_hours_mock": 8,
            "use_trusted_device": True,
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "FAILED_BIOMETRIC",
        "description": "Nouvel appareil, capteurs biométriques disponibles mais la vérification échoue.",
        "mock_signals": {
            "android_id_mock": "AND-NEW-006",
            "device_integrity_mock": "PASSED",
            "emulator_detected_mock": False,
            "root_detected_mock": False,
            "sim_changed_recently_mock": False,
            "use_trusted_device": False,
            "sensors_available": True,
            "biometric_result_mock": "FAILED",
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "FAILED_LIVENESS",
        "description": "Nouvel appareil, pas de capteur biométrique disponible, la vérification de vivacité échoue — blocage attendu.",
        "mock_signals": {
            "android_id_mock": "AND-NEW-007",
            "device_integrity_mock": "PASSED",
            "emulator_detected_mock": False,
            "root_detected_mock": False,
            "sim_changed_recently_mock": False,
            "use_trusted_device": False,
            "sensors_available": False,
            "liveness_result_mock": "FAILED",
            "location": {"latitude": ABIDJAN[0], "longitude": ABIDJAN[1]},
        },
    },
    {
        "name": "MULTIPLE_RISK_SIGNALS",
        "description": "Combinaison de signaux (nouvel appareil, émulateur, root, SIM changée, localisation éloignée) — blocage temporaire attendu, chaîne complète visible.",
        "mock_signals": {
            "android_id_mock": "AND-NEW-008",
            "device_integrity_mock": "FAILED",
            "emulator_detected_mock": True,
            "root_detected_mock": True,
            "sim_changed_recently_mock": True,
            "esim_activated_recently_mock": True,
            "sim_age_hours_mock": 3,
            "use_trusted_device": False,
            "location": {"latitude": PARIS[0], "longitude": PARIS[1]},
        },
    },
]


def seed_user_and_device(db):
    trusted_fingerprint = compute_fingerprint(TRUSTED_DEVICE)
    user = WalletUser(
        id=generate_user_id(),
        full_name="Awa Koffi",
        phone=DEMO_PHONE,
        email="awa.koffi@example.test",
        pin_hash=hash_pin(DEMO_PIN),
        wallet_number="AMW-000001",
        balance=128500.0,
        kyc_status="verified",
        home_latitude=ABIDJAN[0],
        home_longitude=ABIDJAN[1],
        created_at=NOW - timedelta(days=420),
    )
    db.add(user)
    db.flush()

    device = Device(
        id=generate_device_id(),
        user_id=user.id,
        local_device_uuid=TRUSTED_DEVICE["local_device_uuid"],
        device_fingerprint=trusted_fingerprint,
        platform=TRUSTED_DEVICE["platform"],
        os_version=TRUSTED_DEVICE["os_version"],
        browser=TRUSTED_DEVICE["browser"],
        screen_size=TRUSTED_DEVICE["screen_size"],
        language=TRUSTED_DEVICE["language"],
        timezone=TRUSTED_DEVICE["timezone"],
        android_id_mock="AND-001",
        first_seen_at=NOW - timedelta(days=420),
        last_seen_at=NOW - timedelta(days=1),
        trusted=True,
    )
    db.add(device)

    profile = BehaviourProfile(
        user_id=user.id,
        average_login_duration=8200.0,
        average_pin_entry_duration=3500.0,
        average_navigation_time=4200.0,
        failed_attempt_average=0.1,
        sample_count=24,
    )
    db.add(profile)
    db.flush()
    return user


def seed_beneficiaries(db, user: WalletUser) -> list[Beneficiary]:
    rows = [
        ("Serge Konan", "+2250505123456", "AMW-100201", "habituel", 220),
        ("Fatou Bamba", "+2250708998877", "AMW-100455", "habituel", 90),
        ("Yao Coulibaly", "+2250102030405", "AMW-100812", "nouveau", 3),
    ]
    beneficiaries = []
    for full_name, phone, wallet_number, status, days_ago in rows:
        b = Beneficiary(
            id=generate_beneficiary_id(),
            user_id=user.id,
            full_name=full_name,
            phone=phone,
            wallet_number=wallet_number,
            status=status,
            added_at=NOW - timedelta(days=days_ago),
        )
        db.add(b)
        beneficiaries.append(b)
    db.flush()
    return beneficiaries


def seed_transactions(db, user: WalletUser, beneficiaries: list[Beneficiary]) -> None:
    rows = [
        (beneficiaries[0].id, 25000, "transfer", "COMPLETED", 1),
        (beneficiaries[1].id, 12000, "transfer", "COMPLETED", 3),
        (None, 50000, "recharge", "COMPLETED", 6),
        (beneficiaries[2].id, 8000, "transfer", "PENDING", 0),
        (beneficiaries[0].id, 60000, "transfer", "FAILED", 9),
        (beneficiaries[1].id, 150000, "transfer", "BLOCKED", 12),
    ]
    for beneficiary_id, amount, type_, status, days_ago in rows:
        db.add(
            WalletTransaction(
                id=generate_wallet_transaction_id(),
                user_id=user.id,
                beneficiary_id=beneficiary_id,
                amount=amount,
                type=type_,
                status=status,
                created_at=NOW - timedelta(days=days_ago, hours=2),
            )
        )
    db.flush()


def seed_demo_scenarios(db) -> None:
    for scenario in DEMO_SCENARIOS:
        existing = db.query(DemoScenario).filter(DemoScenario.name == scenario["name"]).first()
        if existing:
            existing.description = scenario["description"]
            existing.mock_signals = scenario["mock_signals"]
            existing.active = True
        else:
            db.add(DemoScenario(**scenario, active=True))
    db.flush()


def main() -> None:
    with session_scope() as db:
        existing_user = db.query(WalletUser).filter(WalletUser.phone == DEMO_PHONE).first()
        if existing_user:
            print(f"Utilisateur démo déjà présent ({DEMO_PHONE}) — seuls les scénarios sont resynchronisés.")
            seed_demo_scenarios(db)
            return

        user = seed_user_and_device(db)
        beneficiaries = seed_beneficiaries(db, user)
        seed_transactions(db, user, beneficiaries)
        seed_demo_scenarios(db)

    print("Compte de démonstration Amani Wallet créé :")
    print(f"  Téléphone : {DEMO_PHONE}")
    print(f"  Code PIN  : {DEMO_PIN}")
    print(f"  Scénarios : {len(DEMO_SCENARIOS)}")


if __name__ == "__main__":
    main()
