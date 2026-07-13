"""Moteur de règles métier pour le module Transaction Monitoring.

Chaque règle est déterministe, auditable et documentée : elle produit un code, un poids
(contribution au score 0-100) et une raison lisible par un analyste. Les règles servent de
garde-fou explicable en complément du modèle ML (cf. shared/config/settings.py:
critical_rule_score_floor).

Les seuils monétaires (LARGE_AMOUNT_THRESHOLD, STRUCTURING_CEILING...) sont exprimés en
équivalent XOF et comparés à `f.amount_xof_equivalent` (normalisé multi-devises, voir
feature_engineering.py) — un même seuil a donc le même sens réel en XOF, NGN ou GHS. Les
messages affichés à l'analyste utilisent en revanche `f.amount` + `f.currency` (montant
et devise d'origine, non convertis) pour rester fidèles à ce que le client a réellement
transigé.
"""

from dataclasses import dataclass

from modules.transaction_monitoring.feature_engineering import ContextFeatures

NIGHT_HOURS = set(range(0, 5))
STRUCTURING_CEILING = 500_000.0  # équivalent XOF
LARGE_AMOUNT_THRESHOLD = 100_000.0  # équivalent XOF
NIGHT_AMOUNT_THRESHOLD = 50_000.0  # équivalent XOF
STRUCTURING_CUMULATIVE_THRESHOLD = 1_000_000.0  # équivalent XOF

BATCH_MIN_LEGS_BEFORE_CHECK = 3
BATCH_UNKNOWN_RATIO_THRESHOLD = 0.8
SOCIAL_ENGINEERING_MIN_ACCOUNT_AGE_DAYS = 180
SOCIAL_ENGINEERING_RATIO_THRESHOLD = 8
SOCIAL_ENGINEERING_CHANNELS = {"mobile_app", "web", "ussd"}  # canaux en self-service
AGENT_COLLUSION_TX_THRESHOLD = 6
AGENT_COLLUSION_DISTINCT_SENDERS_THRESHOLD = 5


@dataclass
class RuleResult:
    code: str
    description: str
    weight: float
    triggered: bool


def _r_amount_spike(f: ContextFeatures) -> RuleResult:
    ratio = f.amount_to_avg_ratio
    triggered = f.has_history and f.sender_avg_amount_30d > 0 and ratio >= 5
    desc = (
        f"Montant de {f.amount:,.0f} {f.currency} = {ratio:.1f}x la moyenne habituelle du "
        f"client (équivalent {f.sender_avg_amount_30d:,.0f} XOF sur 30 jours)"
    )
    return RuleResult("AMOUNT_SPIKE", desc, 35.0, triggered)


def _r_high_velocity(f: ContextFeatures) -> RuleResult:
    triggered = f.tx_count_last_10min >= 3
    desc = f"{f.tx_count_last_10min} transactions du même client en moins de 10 minutes"
    return RuleResult("HIGH_VELOCITY", desc, 30.0, triggered)


def _r_unknown_receiver_high_amount(f: ContextFeatures) -> RuleResult:
    triggered = not f.is_known_receiver and f.amount_xof_equivalent >= LARGE_AMOUNT_THRESHOLD
    desc = (
        f"Bénéficiaire jamais utilisé par ce client pour un montant de "
        f"{f.amount:,.0f} {f.currency}"
    )
    return RuleResult("UNKNOWN_RECEIVER_HIGH_AMOUNT", desc, 25.0, triggered)


def _r_night_activity(f: ContextFeatures) -> RuleResult:
    triggered = f.hour in NIGHT_HOURS and f.amount_xof_equivalent >= NIGHT_AMOUNT_THRESHOLD
    desc = f"Transaction nocturne ({f.hour:02d}h) d'un montant significatif ({f.amount:,.0f} {f.currency})"
    return RuleResult("NIGHT_ACTIVITY", desc, 15.0, triggered)


def _r_new_account_high_value(f: ContextFeatures) -> RuleResult:
    triggered = f.account_age_days < 7 and f.amount_xof_equivalent >= LARGE_AMOUNT_THRESHOLD
    desc = (
        f"Compte créé il y a {f.account_age_days:.1f} jours effectuant une "
        f"transaction de {f.amount:,.0f} {f.currency}"
    )
    return RuleResult("NEW_ACCOUNT_HIGH_VALUE", desc, 30.0, triggered)


def _r_structuring(f: ContextFeatures) -> RuleResult:
    triggered = (
        f.tx_count_last_1h >= 4
        and f.sum_amount_last_1h + f.amount_xof_equivalent >= STRUCTURING_CUMULATIVE_THRESHOLD
        and f.amount_xof_equivalent < STRUCTURING_CEILING
    )
    desc = (
        f"Possible fractionnement : {f.tx_count_last_1h + 1} transactions cumulant "
        f"l'équivalent de {f.sum_amount_last_1h + f.amount_xof_equivalent:,.0f} XOF en 1h, "
        f"chacune sous le seuil de {STRUCTURING_CEILING:,.0f} XOF"
    )
    return RuleResult("STRUCTURING_SUSPECTED", desc, 35.0, triggered)


def _r_fanout(f: ContextFeatures) -> RuleResult:
    triggered = f.distinct_receivers_last_1h >= 4
    desc = (
        f"{f.distinct_receivers_last_1h} bénéficiaires distincts en moins d'une heure hors "
        f"opération de paiement de masse déclarée (schéma de distribution possible)"
    )
    return RuleResult("FANOUT_PATTERN", desc, 20.0, triggered)


def _r_cross_border_passthrough(f: ContextFeatures) -> RuleResult:
    triggered = f.is_cross_border_passthrough
    desc = (
        f"Réception d'un montant équivalent depuis un autre pays il y a moins d'une heure, "
        f"puis renvoi immédiat de {f.amount:,.0f} {f.currency} vers un pays différent "
        f"(schéma de transit / blanchiment par superposition)"
    )
    return RuleResult("CROSS_BORDER_PASSTHROUGH", desc, 40.0, triggered)


def _r_suspicious_batch(f: ContextFeatures) -> RuleResult:
    # Un lot déclaré n'est pas automatiquement légitime : le mécanisme de paiement de
    # masse peut lui-même être détourné pour disperser des fonds vers des comptes mules
    # sous couvert d'une opération "groupée". On regarde si CE lot précis envoie
    # majoritairement vers des bénéficiaires jamais vus par ce client en dehors du lot.
    triggered = (
        f.is_batch_operation
        and f.batch_size_so_far >= BATCH_MIN_LEGS_BEFORE_CHECK
        and f.batch_unknown_receiver_ratio >= BATCH_UNKNOWN_RATIO_THRESHOLD
    )
    desc = (
        f"Paiement de masse déclaré mais {f.batch_unknown_receiver_ratio * 100:.0f}% des "
        f"{f.batch_size_so_far} bénéficiaires vus jusqu'ici dans ce lot sont inconnus du "
        f"client — possible détournement du mécanisme vers des comptes mules"
    )
    return RuleResult("SUSPICIOUS_BATCH", desc, 35.0, triggered)


def _r_sim_swap_signal(f: ContextFeatures) -> RuleResult:
    # Changement d'appareil brutal sur un compte établi, combiné à un signal de risque
    # (montant élevé ou bénéficiaire inconnu) : schéma classique post-SIM swap / prise de
    # contrôle de compte (cf. module SIM Swap Intelligence de la roadmap, simplifié ici).
    triggered = f.is_new_device and f.has_history and (
        not f.is_known_receiver or f.amount_xof_equivalent >= LARGE_AMOUNT_THRESHOLD
    )
    desc = (
        "Nouvel appareil jamais utilisé par ce client, combiné à un bénéficiaire inconnu "
        f"ou un montant élevé ({f.amount:,.0f} {f.currency}) — possible SIM swap ou prise "
        "de contrôle de compte"
    )
    return RuleResult("SIM_SWAP_SIGNAL", desc, 35.0, triggered)


def _r_social_engineering_signal(f: ContextFeatures) -> RuleResult:
    # Client établi et jusque-là stable qui effectue, en une seule fois (pas de rafale),
    # un virement très supérieur à son habitude vers un bénéficiaire jamais contacté,
    # depuis un canal en self-service — profil compatible avec une victime guidée par
    # téléphone (arnaque, faux conseiller) plutôt qu'un compte compromis ou une rafale.
    triggered = (
        f.account_age_days >= SOCIAL_ENGINEERING_MIN_ACCOUNT_AGE_DAYS
        and f.has_history
        and f.sender_avg_amount_30d > 0
        and f.amount_to_avg_ratio >= SOCIAL_ENGINEERING_RATIO_THRESHOLD
        and not f.is_known_receiver
        and f.tx_count_last_1h == 0
        and f.channel in SOCIAL_ENGINEERING_CHANNELS
    )
    desc = (
        f"Client établi depuis {f.account_age_days:.0f} jours effectuant, sans rafale, un "
        f"virement isolé de {f.amount:,.0f} {f.currency} ({f.amount_to_avg_ratio:.1f}x son "
        "habitude) vers un bénéficiaire jamais contacté — profil compatible avec une "
        "victime guidée (ingénierie sociale)"
    )
    return RuleResult("SOCIAL_ENGINEERING_SIGNAL", desc, 30.0, triggered)


AGENT_COLLUSION_TYPES = {"withdrawal", "deposit"}


def _r_agent_collusion_cashout(f: ContextFeatures) -> RuleResult:
    # Un agent qui traite un volume anormalement élevé de dépôts OU de retraits pour de
    # nombreux clients différents en peu de temps est un schéma documenté de complicité
    # agent (GSMA) — "cash-out mill" côté retrait, faux dépôt (crédit sans cash réel remis)
    # côté dépôt. Indépendant du comportement de CE client en particulier.
    triggered = (
        f.transaction_type in AGENT_COLLUSION_TYPES
        and f.agent_tx_count_last_1h >= AGENT_COLLUSION_TX_THRESHOLD
        and f.agent_distinct_senders_last_1h >= AGENT_COLLUSION_DISTINCT_SENDERS_THRESHOLD
    )
    action = "retraits" if f.transaction_type == "withdrawal" else "dépôts"
    desc = (
        f"Agent ayant traité {f.agent_tx_count_last_1h} {action} pour "
        f"{f.agent_distinct_senders_last_1h} clients différents en moins d'une heure — "
        "possible complicité agent (cash-out frauduleux ou faux dépôt)"
    )
    return RuleResult("AGENT_COLLUSION_CASHOUT", desc, 30.0, triggered)


def _r_merchant_layering(f: ContextFeatures) -> RuleResult:
    # Un paiement marchand reçu puis évacué (retrait ou renvoi) quasi immédiatement pour
    # un montant similaire est un schéma de blanchiment via faux marchand (transaction
    # laundering) — indépendant du pays, contrairement au transit transfrontalier.
    triggered = f.is_merchant_layering
    desc = (
        f"Paiement marchand reçu il y a moins d'une heure, puis évacuation quasi immédiate "
        f"de {f.amount:,.0f} {f.currency} — schéma de blanchiment via faux marchand"
    )
    return RuleResult("MERCHANT_LAYERING_SIGNAL", desc, 35.0, triggered)


def _r_transaction_behaviour_anomaly(f: ContextFeatures) -> RuleResult:
    # Comportement de saisie transmis par le canal appelant (ex. Amani Wallet) pendant la
    # préparation de CETTE transaction — pas le profil habituel du client (déjà couvert par
    # d'autres modules), mais un signal ponctuel : une confirmation trop rapide pour être
    # une lecture humaine du récapitulatif évoque un envoi scripté ; un nombre inhabituel de
    # modifications du montant évoque une hésitation ou un guidage externe (ingénierie
    # sociale en cours). Absent si le canal ne transmet pas ces mesures (mobile/web only).
    triggered = f.behaviour_very_fast or f.behaviour_excessive_edits
    if f.behaviour_very_fast and f.behaviour_excessive_edits:
        desc = (
            f"Transaction confirmée en {f.behaviour_time_to_complete_ms:.0f} ms avec "
            f"{f.behaviour_amount_field_edits} modifications du montant — incohérent avec une saisie humaine normale"
        )
    elif f.behaviour_very_fast:
        desc = (
            f"Transaction confirmée en seulement {f.behaviour_time_to_complete_ms:.0f} ms "
            f"— trop rapide pour une relecture humaine du récapitulatif, signe probable d'envoi automatisé"
        )
    else:
        desc = (
            f"{f.behaviour_amount_field_edits} modifications du montant avant confirmation "
            f"— hésitation inhabituelle, éventuellement un signe de guidage externe"
        )
    return RuleResult("TRANSACTION_BEHAVIOUR_ANOMALY", desc, 20.0, triggered)


def _r_account_drained(f: ContextFeatures) -> RuleResult:
    # Solde qui tombe à (quasi) zéro après la transaction : signal fortement prédictif
    # documenté par les travaux de référence sur la simulation Mobile Money (PaySim,
    # MoMTSim) — compte vidé, souvent le dernier geste d'une prise de contrôle de compte.
    triggered = f.is_balance_drained
    desc = (
        f"Le solde du client tombe à (quasi) zéro après cette transaction de "
        f"{f.amount:,.0f} {f.currency} — signal fort de compte vidé/compromis"
    )
    return RuleResult("ACCOUNT_DRAINED", desc, 30.0, triggered)


RULES = [
    _r_amount_spike,
    _r_high_velocity,
    _r_unknown_receiver_high_amount,
    _r_night_activity,
    _r_new_account_high_value,
    _r_structuring,
    _r_fanout,
    _r_cross_border_passthrough,
    _r_suspicious_batch,
    _r_sim_swap_signal,
    _r_social_engineering_signal,
    _r_agent_collusion_cashout,
    _r_account_drained,
    _r_merchant_layering,
    _r_transaction_behaviour_anomaly,
]


def evaluate_rules(features: ContextFeatures) -> list[RuleResult]:
    return [rule(features) for rule in RULES]


def aggregate_rule_score(results: list[RuleResult]) -> float:
    total = sum(r.weight for r in results if r.triggered)
    return min(total, 100.0)
