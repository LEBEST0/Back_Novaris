import uuid


def generate_transaction_id() -> str:
    return f"TXN-{uuid.uuid4().hex[:16].upper()}"


def generate_customer_id() -> str:
    return f"CUST-{uuid.uuid4().hex[:12].upper()}"
