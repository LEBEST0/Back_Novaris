"""Conversion approximative de devise vers un équivalent XOF, utilisée uniquement en
interne par le moteur de scoring pour comparer des montants entre pays sur une même
échelle (ex : un seuil "montant élevé" doit avoir le même sens réel en NGN qu'en XOF).

Ce ne sont PAS des taux de change temps réel — des ordres de grandeur indicatifs figés
dans le code, pour la démonstration. Une intégration réelle utiliserait un service de
taux de change à jour (même principe mock-aujourd'hui/API-demain que les autres
connecteurs externes du produit). Ne jamais utiliser ces valeurs pour un usage financier
réel (conversion affichée au client, réconciliation comptable...).

Le montant brut et la devise d'origine restent toujours stockés et affichés tels quels
(TransactionAnalysis, reasons) ; seule la logique de scoring (ratios, seuils, feature ML)
travaille sur l'équivalent XOF.
"""

# Valeur approximative d'une unité de devise locale, exprimée en XOF.
APPROX_XOF_PER_UNIT = {
    "XOF": 1.0,
    "XAF": 1.0,  # même parité que XOF : zone CFA, ancrage EUR identique
    "GHS": 40.0,
    "NGN": 0.41,
    "KES": 4.7,
    "RWF": 0.47,
    "UGX": 0.165,
    "TZS": 0.244,
    "GMD": 8.7,
    "GNF": 0.071,
    "SLE": 27.7,
}


def to_xof_equivalent(amount: float, currency: str) -> float:
    return amount * APPROX_XOF_PER_UNIT.get(currency, 1.0)
