"""Masquage des identifiants sensibles affichés côté client (section 18 : ne jamais
exposer un numéro complet inutilement)."""


def mask_phone(phone: str) -> str:
    if len(phone) <= 4:
        return "•" * len(phone)
    return f"{phone[:4]}{'•' * (len(phone) - 6)}{phone[-2:]}"


def mask_wallet_number(wallet_number: str) -> str:
    if len(wallet_number) <= 4:
        return "•" * len(wallet_number)
    return f"{'•' * (len(wallet_number) - 4)}{wallet_number[-4:]}"
