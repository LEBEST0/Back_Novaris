"""Calcul des variables contextuelles utilisées à la fois par les règles et par le modèle ML.

Ce module est la source unique de vérité pour la logique "point-in-time" :
- à l'entraînement (scripts/train_model.py), on rejoue l'historique chronologique et on ne
  regarde jamais une transaction future par rapport à la transaction courante ;
- en production (repository.py), on interroge la base pour l'historique réel du client.

Centraliser cette logique évite le "train/serve skew" (le modèle voit à l'entraînement
exactement les mêmes variables qu'au moment de noter une transaction en direct).

Multi-devises : tous les montants utilisés pour le scoring (ratios, seuils, historique,
feature ML) sont normalisés en équivalent XOF via shared/utils/currency.py, pour qu'un
seuil ait le même sens réel qu'il s'agisse de XOF, NGN ou GHS. Le montant brut et la
devise d'origine (`amount`, `currency`) restent disponibles pour l'affichage/l'audit.
"""

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.utils.currency import to_xof_equivalent

# Fenêtre de recherche d'une transaction entrante récente pour détecter un schéma de
# transit ("passthrough") : reçu puis renvoyé très vite vers un autre pays, ou vers un
# compte mule (cf. PASSTHROUGH_CYCLE_WINDOW_DAYS ci-dessous).
PASSTHROUGH_WINDOW_MINUTES = 60
PASSTHROUGH_AMOUNT_RATIO_RANGE = (0.7, 1.3)
NO_INCOMING_SENTINEL_MINUTES = 999_999.0

# Solde après transaction considéré comme "compte vidé" (équivalent XOF, proche de zéro).
BALANCE_DRAINED_THRESHOLD_XOF = 500.0

# Fenêtre d'historique pour détecter un compte mule récidiviste (cycles répétés
# dépôt/réception -> retrait rapide, cf. rules.MULE_PASSTHROUGH_PATTERN). Un cycle isolé
# est un usage normal (ex. dépôt puis envoi immédiat à un proche) ; c'est la répétition
# sur la durée qui distingue le mule — les seuils de déclenchement vivent dans rules.py.
PASSTHROUGH_CYCLE_WINDOW_DAYS = 30

# Comportement de saisie côté canal appelant (ex. Amani Wallet), transmis en option — pas
# une variable ML (dataset synthétique non ré-entraîné avec ce signal), seulement une
# règle auditable. En dessous de ce seuil, une confirmation de transfert est implausible
# pour un humain qui relit un récapitulatif (plutôt un envoi scripté/automatisé).
BEHAVIOUR_VERY_FAST_MS_THRESHOLD = 2500
# Au-delà, le nombre de modifications du champ montant avant confirmation devient un
# signal d'hésitation ou de guidage externe (ingénierie sociale) plutôt qu'une simple saisie.
BEHAVIOUR_EXCESSIVE_EDITS_THRESHOLD = 8


@dataclass
class HistoryEntry:
    receiver_phone: str
    amount_xof_equivalent: float
    created_at: datetime
    transaction_type: str = "transfer"
    agent_id: str | None = None
    device_id: str | None = None


@dataclass
class IncomingEntry:
    """Transaction reçue par le client (lui en tant que destinataire), utilisée pour
    détecter un schéma de transit transfrontalier (reçu d'un pays, renvoyé vers un autre)
    ou un cycle de passage type compte mule (reçu puis retiré/renvoyé rapidement,
    répété dans le temps)."""

    sender_country: str | None
    amount_xof_equivalent: float
    created_at: datetime
    transaction_type: str = "transfer"
    sender_phone: str | None = None


@dataclass
class PassthroughLeg:
    """Une jambe entrante ou sortante du compte analysé, utilisée pour détecter des
    cycles dépôt/réception -> retrait rapide (cf. compute_passthrough_cycles)."""

    direction: str  # "in" | "out"
    amount_xof_equivalent: float
    created_at: datetime
    # Identité de la source, uniquement pour les jambes entrantes : numéro de l'émetteur
    # (transfert reçu) ou "agent:<id>" (dépôt en agence). None si la source n'est pas
    # traçable (ex. dépôt direct depuis un compte Mobile money externe non modélisé).
    source_identity: str | None = None


def compute_passthrough_cycles(legs: list["PassthroughLeg"]) -> tuple[int, int, int]:
    """Pour chaque jambe entrante, cherche une jambe sortante d'un montant équivalent
    dans les PASSTHROUGH_WINDOW_MINUTES qui suivent — un cycle complet. Retourne
    (nombre de cycles, nombre de cycles dont la source est identifiée, nombre de
    sources distinctes parmi ces cycles identifiés). Une jambe sortante peut clore
    plusieurs cycles entrants (simplification volontaire : c'est un signal de risque,
    pas un grand livre comptable précis)."""
    incoming = sorted((leg for leg in legs if leg.direction == "in"), key=lambda leg: leg.created_at)
    outgoing = sorted((leg for leg in legs if leg.direction == "out"), key=lambda leg: leg.created_at)

    cycle_count = 0
    identified_sources: list[str] = []
    for inc in incoming:
        if inc.amount_xof_equivalent <= 0:
            continue
        matched = False
        for out in outgoing:
            if out.created_at <= inc.created_at:
                continue
            delta_minutes = (out.created_at - inc.created_at).total_seconds() / 60
            if delta_minutes > PASSTHROUGH_WINDOW_MINUTES:
                break  # outgoing triées par date : inutile de chercher plus loin
            ratio = out.amount_xof_equivalent / inc.amount_xof_equivalent
            if PASSTHROUGH_AMOUNT_RATIO_RANGE[0] <= ratio <= PASSTHROUGH_AMOUNT_RATIO_RANGE[1]:
                matched = True
                break
        if matched:
            cycle_count += 1
            if inc.source_identity is not None:
                identified_sources.append(inc.source_identity)

    return cycle_count, len(identified_sources), len(set(identified_sources))


def is_payday_window(timestamp: datetime) -> bool:
    """Fenêtre de paie / fin de mois (5 premiers jours et 5 derniers jours du mois) :
    période où les flux Mobile Money augmentent structurellement en Afrique de l'Ouest
    (versement des salaires, loyers, factures). Sert à la fois à injecter ce pattern
    dans le dataset synthétique (scripts/generate_synthetic_data.py) et à le calculer en
    production, pour que le modèle apprenne à ne pas confondre un pic de paie normal
    avec une anomalie."""
    _, days_in_month = calendar.monthrange(timestamp.year, timestamp.month)
    return timestamp.day <= 5 or timestamp.day > days_in_month - 5


@dataclass
class ContextFeatures:
    amount: float
    currency: str
    amount_xof_equivalent: float
    hour: int
    day_of_week: int
    day_of_month: int
    is_payday_window: bool
    account_age_days: float
    has_history: bool
    sender_avg_amount_30d: float
    amount_to_avg_ratio: float
    is_known_receiver: bool
    tx_count_last_10min: int
    tx_count_last_1h: int
    sum_amount_last_1h: float
    distinct_receivers_last_1h: int
    is_cross_border: bool
    minutes_since_last_incoming: float
    incoming_amount_ratio: float
    is_cross_border_passthrough: bool
    is_new_device: bool
    is_balance_drained: bool
    # Cycles dépôt/réception -> retrait rapide sur 30 jours (cf. compute_passthrough_cycles)
    # — signal de compte mule récidiviste, indépendant du canal (app ou agence).
    passthrough_cycle_count_30d: int
    passthrough_identified_cycle_count_30d: int
    passthrough_distinct_sources_30d: int
    kyc_level: str
    customer_type: str
    transaction_type: str
    channel: str
    # Comportement de saisie (optionnel, cf. BEHAVIOUR_VERY_FAST_MS_THRESHOLD ci-dessus) —
    # utilisé uniquement par une règle auditable, jamais par le modèle ML (absent de
    # to_dict) : le dataset synthétique d'entraînement ne porte pas ce signal.
    behaviour_time_to_complete_ms: float | None
    behaviour_amount_field_edits: int | None
    behaviour_very_fast: bool
    behaviour_excessive_edits: bool

    def to_dict(self) -> dict:
        return {
            "amount_xof_equivalent": self.amount_xof_equivalent,
            "hour": self.hour,
            "day_of_week": self.day_of_week,
            "day_of_month": self.day_of_month,
            "is_payday_window": self.is_payday_window,
            "account_age_days": self.account_age_days,
            "has_history": self.has_history,
            "sender_avg_amount_30d": self.sender_avg_amount_30d,
            "amount_to_avg_ratio": self.amount_to_avg_ratio,
            "is_known_receiver": self.is_known_receiver,
            "tx_count_last_10min": self.tx_count_last_10min,
            "tx_count_last_1h": self.tx_count_last_1h,
            "sum_amount_last_1h": self.sum_amount_last_1h,
            "distinct_receivers_last_1h": self.distinct_receivers_last_1h,
            "is_cross_border": self.is_cross_border,
            "minutes_since_last_incoming": self.minutes_since_last_incoming,
            "incoming_amount_ratio": self.incoming_amount_ratio,
            "is_cross_border_passthrough": self.is_cross_border_passthrough,
            "is_new_device": self.is_new_device,
            "is_balance_drained": self.is_balance_drained,
            "passthrough_cycle_count_30d": self.passthrough_cycle_count_30d,
            "passthrough_identified_cycle_count_30d": self.passthrough_identified_cycle_count_30d,
            "passthrough_distinct_sources_30d": self.passthrough_distinct_sources_30d,
            "kyc_level": self.kyc_level,
            "customer_type": self.customer_type,
            "transaction_type": self.transaction_type,
            "channel": self.channel,
        }


def compute_context_features(
    *,
    amount: float,
    receiver_phone: str,
    timestamp: datetime,
    transaction_type: str,
    channel: str,
    account_created_at: datetime,
    kyc_level: str,
    prior_history: list[HistoryEntry],
    currency: str = "XOF",
    sender_country: str | None = None,
    receiver_country: str | None = None,
    customer_type: str = "individual",
    incoming_history: list[IncomingEntry] | None = None,
    device_id: str | None = None,
    balance_after_sender: float | None = None,
    behaviour_time_to_complete_ms: int | None = None,
    behaviour_amount_field_edits: int | None = None,
) -> ContextFeatures:
    """prior_history doit contenir uniquement les transactions du même émetteur
    strictement antérieures à `timestamp` (triées ou non, peu importe ici), avec des
    montants déjà normalisés en équivalent XOF (HistoryEntry.amount_xof_equivalent).
    incoming_history : transferts reçus par ce client (lui en tant que destinataire),
    utilisée pour la détection de transit transfrontalier et de cycles type mule."""

    incoming_history = incoming_history or []
    amount_xof_equivalent = to_xof_equivalent(amount, currency)

    window_30d = timestamp - timedelta(days=30)
    window_1h = timestamp - timedelta(hours=1)
    window_10min = timestamp - timedelta(minutes=10)

    past_30d = [h for h in prior_history if window_30d <= h.created_at < timestamp]
    past_1h = [h for h in prior_history if window_1h <= h.created_at < timestamp]
    past_10min = [h for h in prior_history if window_10min <= h.created_at < timestamp]

    has_history = len(prior_history) > 0
    sender_avg_amount_30d = (
        sum(h.amount_xof_equivalent for h in past_30d) / len(past_30d) if past_30d else 0.0
    )
    amount_to_avg_ratio = (
        amount_xof_equivalent / sender_avg_amount_30d if sender_avg_amount_30d > 0 else 0.0
    )

    known_receivers = {h.receiver_phone for h in prior_history}
    is_known_receiver = receiver_phone in known_receivers

    account_age_days = max((timestamp - account_created_at).total_seconds() / 86400, 0.0)

    is_cross_border = bool(
        sender_country and receiver_country and sender_country != receiver_country
    )

    # Transit transfrontalier : la transaction entrante la plus récente (avant `timestamp`)
    past_incoming = [h for h in incoming_history if h.created_at < timestamp]
    minutes_since_last_incoming = NO_INCOMING_SENTINEL_MINUTES
    incoming_amount_ratio = 0.0
    is_cross_border_passthrough = False
    if past_incoming:
        last_incoming = max(past_incoming, key=lambda h: h.created_at)
        minutes_since_last_incoming = (timestamp - last_incoming.created_at).total_seconds() / 60
        if last_incoming.amount_xof_equivalent > 0:
            incoming_amount_ratio = amount_xof_equivalent / last_incoming.amount_xof_equivalent
        same_amount = (
            PASSTHROUGH_AMOUNT_RATIO_RANGE[0] <= incoming_amount_ratio <= PASSTHROUGH_AMOUNT_RATIO_RANGE[1]
        )
        recent = minutes_since_last_incoming <= PASSTHROUGH_WINDOW_MINUTES
        different_country = (
            last_incoming.sender_country is not None
            and receiver_country is not None
            and last_incoming.sender_country != receiver_country
        )
        is_cross_border_passthrough = recent and same_amount and different_country

    # Compte mule récidiviste : on reconstitue les jambes entrantes/sortantes de CE
    # compte sur 30 jours (ses propres dépôts/retraits/transferts + les transferts reçus
    # d'un tiers) et on cherche des cycles réception -> sortie rapide répétés, avec la
    # source de financement identifiée quand c'est possible (cf. compute_passthrough_cycles).
    cycle_window_start = timestamp - timedelta(days=PASSTHROUGH_CYCLE_WINDOW_DAYS)
    passthrough_legs: list[PassthroughLeg] = []
    for h in prior_history:
        if not (cycle_window_start <= h.created_at < timestamp):
            continue
        if h.transaction_type == "deposit":
            source_identity = f"agent:{h.agent_id}" if h.agent_id else None
            passthrough_legs.append(PassthroughLeg("in", h.amount_xof_equivalent, h.created_at, source_identity))
        elif h.transaction_type in {"withdrawal", "transfer"}:
            passthrough_legs.append(PassthroughLeg("out", h.amount_xof_equivalent, h.created_at))
    for h in incoming_history:
        if h.transaction_type == "transfer" and cycle_window_start <= h.created_at < timestamp:
            passthrough_legs.append(PassthroughLeg("in", h.amount_xof_equivalent, h.created_at, h.sender_phone))
    # La transaction en cours peut elle-même clore un cycle (le retrait qui vide ce qui
    # vient d'être reçu) — on veut le détecter immédiatement, pas seulement à la
    # prochaine transaction.
    if transaction_type in {"withdrawal", "transfer"}:
        passthrough_legs.append(PassthroughLeg("out", amount_xof_equivalent, timestamp))

    (
        passthrough_cycle_count_30d,
        passthrough_identified_cycle_count_30d,
        passthrough_distinct_sources_30d,
    ) = compute_passthrough_cycles(passthrough_legs)

    # Changement d'appareil brutal sur un compte établi : signal SIM swap / prise de
    # contrôle de compte (module SIM Swap Intelligence de la roadmap, simplifié ici).
    known_devices = {h.device_id for h in prior_history if h.device_id}
    is_new_device = bool(has_history and device_id and device_id not in known_devices)

    # Compte vidé après la transaction : signal documenté par les travaux de référence
    # sur la simulation Mobile Money (PaySim, MoMTSim) comme fortement prédictif de
    # fraude/compromission. Optionnel : uniquement si le système appelant transmet le
    # solde (Novaris ne gère pas les soldes lui-même).
    is_balance_drained = bool(
        balance_after_sender is not None
        and balance_after_sender >= 0
        and to_xof_equivalent(balance_after_sender, currency) < BALANCE_DRAINED_THRESHOLD_XOF
        and amount_xof_equivalent > BALANCE_DRAINED_THRESHOLD_XOF
    )

    behaviour_very_fast = bool(
        behaviour_time_to_complete_ms is not None
        and behaviour_time_to_complete_ms < BEHAVIOUR_VERY_FAST_MS_THRESHOLD
    )
    behaviour_excessive_edits = bool(
        behaviour_amount_field_edits is not None
        and behaviour_amount_field_edits > BEHAVIOUR_EXCESSIVE_EDITS_THRESHOLD
    )

    return ContextFeatures(
        amount=amount,
        currency=currency,
        amount_xof_equivalent=amount_xof_equivalent,
        hour=timestamp.hour,
        day_of_week=timestamp.weekday(),
        day_of_month=timestamp.day,
        is_payday_window=is_payday_window(timestamp),
        account_age_days=account_age_days,
        has_history=has_history,
        sender_avg_amount_30d=sender_avg_amount_30d,
        amount_to_avg_ratio=amount_to_avg_ratio,
        is_known_receiver=is_known_receiver,
        tx_count_last_10min=len(past_10min),
        tx_count_last_1h=len(past_1h),
        sum_amount_last_1h=sum(h.amount_xof_equivalent for h in past_1h),
        distinct_receivers_last_1h=len({h.receiver_phone for h in past_1h}),
        is_cross_border=is_cross_border,
        minutes_since_last_incoming=minutes_since_last_incoming,
        incoming_amount_ratio=incoming_amount_ratio,
        is_cross_border_passthrough=is_cross_border_passthrough,
        is_new_device=is_new_device,
        is_balance_drained=is_balance_drained,
        passthrough_cycle_count_30d=passthrough_cycle_count_30d,
        passthrough_identified_cycle_count_30d=passthrough_identified_cycle_count_30d,
        passthrough_distinct_sources_30d=passthrough_distinct_sources_30d,
        kyc_level=kyc_level,
        customer_type=customer_type,
        transaction_type=transaction_type,
        channel=channel,
        behaviour_time_to_complete_ms=(
            float(behaviour_time_to_complete_ms) if behaviour_time_to_complete_ms is not None else None
        ),
        behaviour_amount_field_edits=behaviour_amount_field_edits,
        behaviour_very_fast=behaviour_very_fast,
        behaviour_excessive_edits=behaviour_excessive_edits,
    )
