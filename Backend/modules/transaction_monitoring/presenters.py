"""Construction du contrat de sortie (TransactionAnalysisOut) à partir d'une Transaction
persistée. Centralisé ici pour que l'API d'analyse, la lecture unitaire et la liste du
dashboard produisent exactement le même contrat sans dupliquer la logique."""

from sqlalchemy.orm import Session

from modules.transaction_monitoring.models import Customer, Transaction
from modules.transaction_monitoring.schemas import RuleFlagOut, TransactionAnalysisOut
from shared.utils.phone import country_from_phone


def transaction_to_analysis_out(transaction: Transaction, db: Session) -> TransactionAnalysisOut:
    analysis = transaction.analysis
    receiver_country = country_from_phone(transaction.receiver_phone)
    sender_country = transaction.sender.country

    # Le destinataire n'est pas forcément un client Clapay connu (réseau externe) : on ne
    # remonte son KYC/national_id que s'il existe réellement dans notre base, jamais deviné.
    receiver_customer = db.query(Customer).filter(Customer.phone == transaction.receiver_phone).first()

    return TransactionAnalysisOut(
        transaction_id=transaction.transaction_id,
        sender_phone=transaction.sender_phone,
        sender_operator=transaction.sender.operator,
        sender_country=sender_country,
        receiver_phone=transaction.receiver_phone,
        receiver_country=receiver_country,
        is_cross_border=bool(
            receiver_country is not None and receiver_country != sender_country
        ),
        agent_id=transaction.agent_id,
        device_id=transaction.device_id,
        sender_city=transaction.sender_city,
        sender_kyc_level=transaction.sender.kyc_level,
        sender_national_id=transaction.sender.national_id,
        receiver_kyc_level=receiver_customer.kyc_level if receiver_customer else None,
        receiver_national_id=receiver_customer.national_id if receiver_customer else None,
        balance_before_sender=transaction.balance_before_sender,
        balance_after_sender=transaction.balance_after_sender,
        amount=transaction.amount,
        currency=transaction.currency,
        transaction_type=transaction.transaction_type,
        channel=transaction.channel,
        rule_score=analysis.rule_score,
        ml_score=analysis.ml_score,
        final_score=analysis.final_score,
        risk_level=analysis.risk_level,
        decision=analysis.decision,
        confidence=analysis.confidence,
        reasons=analysis.reasons,
        rule_flags=[RuleFlagOut(**flag) for flag in analysis.rule_flags],
        top_ml_factors=analysis.top_ml_factors,
        model_version=analysis.model_version,
        computed_at=analysis.computed_at,
        analyst_feedback=analysis.analyst_feedback,
        feedback_note=analysis.feedback_note,
        feedback_at=analysis.feedback_at,
    )
