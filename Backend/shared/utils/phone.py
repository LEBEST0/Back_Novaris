"""Génération et interprétation de numéros Mobile Money au format ivoirien.

Depuis le passage au plan de numérotation à 10 chiffres (2021), un numéro ivoirien
s'écrit +225 suivi de 10 chiffres, dont les 2 premiers indiquent l'opérateur.

La répartition ci-dessous est indicative (à usage de démonstration) et reprend la
correspondance la plus couramment citée publiquement. Elle n'a pas été vérifiée auprès
du régulateur (ARTCI) et ne doit pas être présentée comme une source officielle si une
correspondance exacte est nécessaire en dehors du contexte du hackathon.
"""

import random

COUNTRY_CODE = "225"

OPERATOR_PREFIXES = {
    "Moov Africa": ["01", "02", "03"],
    "MTN": ["05", "06"],
    "Orange": ["07", "08", "09"],
}

_PREFIX_TO_OPERATOR = {
    prefix: operator for operator, prefixes in OPERATOR_PREFIXES.items() for prefix in prefixes
}

UNKNOWN_OPERATOR = "Autre / inconnu"


def random_ci_phone(operator: str | None = None) -> tuple[str, str]:
    """Génère un numéro ivoirien plausible. Retourne (numéro E.164, opérateur)."""
    if operator is None or operator not in OPERATOR_PREFIXES:
        operator = random.choices(
            list(OPERATOR_PREFIXES), weights=[0.25, 0.35, 0.40]
        )[0]
    prefix = random.choice(OPERATOR_PREFIXES[operator])
    suffix = "".join(str(random.randint(0, 9)) for _ in range(8))
    return f"+{COUNTRY_CODE}{prefix}{suffix}", operator


def operator_from_phone(phone: str) -> str:
    """Déduit l'opérateur à partir du préfixe. Retourne 'Autre / inconnu' si le numéro
    n'est pas au format ivoirien reconnu (utile pour rester robuste face à des numéros
    saisis par un client réel qui ne suivraient pas ce format)."""
    prefix_zone = f"+{COUNTRY_CODE}"
    if not phone.startswith(prefix_zone):
        return UNKNOWN_OPERATOR
    national_number = phone[len(prefix_zone):]
    prefix = national_number[:2]
    return _PREFIX_TO_OPERATOR.get(prefix, UNKNOWN_OPERATOR)
