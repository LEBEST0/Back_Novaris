"""Génération et interprétation de numéros Mobile Money multi-pays.

Couvre les pays où Clapay annonce une présence (Bénin, Burkina Faso, Cameroun, Congo,
Côte d'Ivoire, Gabon, Gambie, Ghana, Guinée Conakry, Kenya, Mali, Niger, Nigeria,
Ouganda, Rwanda, Sénégal, Sierra Leone, Tanzanie, Togo).

Niveaux de confiance différents selon les champs :
- `calling_code` et `currency` sont des codes officiels stables (ITU / ISO 4217) : fiables.
- `operators` liste les opérateurs Mobile Money majeurs réellement présents dans chaque
  pays (fait de notoriété publique) : fiable pour le nom de l'opérateur assigné à un
  client synthétique.
- La correspondance **préfixe de numéro -> opérateur** n'est précise que pour la
  Côte d'Ivoire (plan de numérotation à 10 chiffres, cf. OPERATOR_PREFIXES_CI) et reste
  indicative même là. Pour les autres pays, le numéro généré respecte l'indicatif et une
  longueur nationale plausible, mais ne prétend pas à une correspondance officielle
  préfixe -> opérateur : `operator_from_phone` renvoie 'Autre / inconnu' hors Côte
  d'Ivoire plutôt que d'inventer une règle non vérifiée.
"""

import random

UNKNOWN_OPERATOR = "Autre / inconnu"

# Côte d'Ivoire : seul pays où on modélise finement le préfixe -> opérateur (voir
# shared/utils/phone.py docstring pour le niveau de confiance).
CI_CALLING_CODE = "225"
OPERATOR_PREFIXES_CI = {
    "Moov Money CI": ["01", "02", "03"],
    "MTN MoMo CI": ["05", "06"],
    "Orange Money CI": ["07", "08", "09"],
}
_PREFIX_TO_OPERATOR_CI = {
    prefix: operator for operator, prefixes in OPERATOR_PREFIXES_CI.items() for prefix in prefixes
}

# calling_code : indicatif téléphonique (ITU, fiable)
# currency     : devise ISO 4217 (fiable)
# operators    : vraies marques Mobile Money majeures présentes dans le pays (fait de
#                notoriété publique — ex: M-Pesa au Kenya, pas juste "l'opérateur
#                générique") ; pas de correspondance précise avec un préfixe pour ces pays
# national_length : nombre de chiffres après l'indicatif (approximatif hors CI)
COUNTRIES = {
    "Côte d'Ivoire": {"calling_code": "225", "currency": "XOF", "national_length": 10, "operators": ["Orange Money CI", "MTN MoMo CI", "Moov Money CI"]},
    "Sénégal": {"calling_code": "221", "currency": "XOF", "national_length": 9, "operators": ["Orange Money SN", "Free Money", "Expresso E-Money"]},
    "Mali": {"calling_code": "223", "currency": "XOF", "national_length": 8, "operators": ["Orange Money ML", "Moov Money ML"]},
    "Burkina Faso": {"calling_code": "226", "currency": "XOF", "national_length": 8, "operators": ["Orange Money BF", "Moov Money BF", "Telecel Faso"]},
    "Bénin": {"calling_code": "229", "currency": "XOF", "national_length": 10, "operators": ["MTN MoMo BJ", "Moov Money BJ"]},
    "Togo": {"calling_code": "228", "currency": "XOF", "national_length": 8, "operators": ["Togocom T-Money", "Moov Money TG"]},
    "Niger": {"calling_code": "227", "currency": "XOF", "national_length": 8, "operators": ["Orange Money NE", "Moov Money NE", "Airtel Money NE"]},
    "Cameroun": {"calling_code": "237", "currency": "XAF", "national_length": 9, "operators": ["MTN MoMo CM", "Orange Money CM"]},
    "Gabon": {"calling_code": "241", "currency": "XAF", "national_length": 8, "operators": ["Airtel Money GA", "Moov Money GA"]},
    "Congo": {"calling_code": "242", "currency": "XAF", "national_length": 9, "operators": ["MTN MoMo CG", "Airtel Money CG"]},
    "Ghana": {"calling_code": "233", "currency": "GHS", "national_length": 9, "operators": ["MTN MoMo GH", "Vodafone Cash", "AirtelTigo Money"]},
    "Nigeria": {"calling_code": "234", "currency": "NGN", "national_length": 10, "operators": ["MTN MoMo NG", "Airtel Money NG", "Glo Mobile Money"]},
    "Kenya": {"calling_code": "254", "currency": "KES", "national_length": 9, "operators": ["M-Pesa", "Airtel Money KE"]},
    "Rwanda": {"calling_code": "250", "currency": "RWF", "national_length": 9, "operators": ["MTN MoMo RW", "Airtel Money RW"]},
    "Ouganda": {"calling_code": "256", "currency": "UGX", "national_length": 9, "operators": ["MTN MoMo UG", "Airtel Money UG"]},
    "Tanzanie": {"calling_code": "255", "currency": "TZS", "national_length": 9, "operators": ["M-Pesa TZ", "Airtel Money TZ"]},
    "Sierra Leone": {"calling_code": "232", "currency": "SLE", "national_length": 8, "operators": ["Orange Money SL", "Africell Money"]},
    "Gambie": {"calling_code": "220", "currency": "GMD", "national_length": 7, "operators": ["Africell Money GM", "Qcell Money"]},
    "Guinée Conakry": {"calling_code": "224", "currency": "GNF", "national_length": 9, "operators": ["Orange Money GN", "MTN MoMo GN"]},
}

_CALLING_CODE_TO_COUNTRY = {info["calling_code"]: country for country, info in COUNTRIES.items()}


def random_phone_for_country(country: str, operator: str | None = None) -> tuple[str, str]:
    """Génère un numéro plausible pour `country`. Retourne (numéro E.164, opérateur).

    Pour la Côte d'Ivoire, le préfixe encode réellement l'opérateur (cf.
    OPERATOR_PREFIXES_CI). Pour les autres pays, l'opérateur est assigné (pas déduit du
    numéro) parmi les opérateurs majeurs connus de ce pays."""
    info = COUNTRIES[country]
    if country == "Côte d'Ivoire":
        if operator is None or operator not in OPERATOR_PREFIXES_CI:
            operator = random.choices(list(OPERATOR_PREFIXES_CI), weights=[0.25, 0.35, 0.40])[0]
        prefix = random.choice(OPERATOR_PREFIXES_CI[operator])
        suffix = "".join(str(random.randint(0, 9)) for _ in range(8))
        return f"+{info['calling_code']}{prefix}{suffix}", operator

    operator = operator if operator in info["operators"] else random.choice(info["operators"])
    national_number = "".join(str(random.randint(0, 9)) for _ in range(info["national_length"]))
    return f"+{info['calling_code']}{national_number}", operator


def random_ci_phone(operator: str | None = None) -> tuple[str, str]:
    """Alias rétrocompatible : équivalent à random_phone_for_country("Côte d'Ivoire", ...)."""
    return random_phone_for_country("Côte d'Ivoire", operator)


def country_from_phone(phone: str) -> str | None:
    """Déduit le pays à partir de l'indicatif. None si non reconnu (numéro hors des 18
    pays couverts)."""
    if not phone.startswith("+"):
        return None
    digits = phone[1:]
    return _CALLING_CODE_TO_COUNTRY.get(digits[:3])


def currency_for_country(country: str | None) -> str:
    if country is None or country not in COUNTRIES:
        return "XOF"
    return COUNTRIES[country]["currency"]


def operator_from_phone(phone: str) -> str:
    """Déduit l'opérateur à partir du préfixe. Ne renvoie une correspondance précise que
    pour la Côte d'Ivoire (seul pays où le préfixe encode réellement l'opérateur dans ce
    module) ; 'Autre / inconnu' sinon, plutôt que d'inventer une correspondance non
    vérifiée pour les 17 autres pays."""
    prefix_zone = f"+{CI_CALLING_CODE}"
    if not phone.startswith(prefix_zone):
        return UNKNOWN_OPERATOR
    national_number = phone[len(prefix_zone):]
    prefix = national_number[:2]
    return _PREFIX_TO_OPERATOR_CI.get(prefix, UNKNOWN_OPERATOR)
