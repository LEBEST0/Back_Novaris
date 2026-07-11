import random
import uuid


def generate_transaction_id() -> str:
    return f"TXN-{uuid.uuid4().hex[:16].upper()}"


def generate_customer_id() -> str:
    return f"CUST-{uuid.uuid4().hex[:12].upper()}"


def generate_national_id() -> str:
    """Identifiant de pièce d'identité KYC interne à Clapay — pas un vrai format de CNI
    (on ne modélise pas les 18 formats nationaux réels), juste une référence stable qui
    permet de relier plusieurs comptes/numéros à la même personne vérifiée."""
    return f"KYC-{uuid.uuid4().hex[:10].upper()}"


def generate_user_id() -> str:
    return f"USR-{uuid.uuid4().hex[:10].upper()}"


def generate_session_id() -> str:
    return f"SES-{uuid.uuid4().hex[:12].upper()}"


def generate_event_id() -> str:
    return f"EVT-{uuid.uuid4().hex[:12].upper()}"


def generate_device_id() -> str:
    return f"DEV-{uuid.uuid4().hex[:10].upper()}"


def generate_beneficiary_id() -> str:
    return f"BEN-{uuid.uuid4().hex[:10].upper()}"


def generate_wallet_transaction_id() -> str:
    return f"WTX-{uuid.uuid4().hex[:12].upper()}"


def generate_wallet_number() -> str:
    return f"AMW-{random.randint(0, 999999):06d}"
