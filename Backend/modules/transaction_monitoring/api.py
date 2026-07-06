from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db
from modules.transaction_monitoring.repository import TransactionRepository
from modules.transaction_monitoring.schemas import RuleFlagOut, TransactionAnalysisOut, TransactionIn
from modules.transaction_monitoring.service import TransactionMonitoringService
from shared.utils.phone import country_from_phone

router = APIRouter(prefix="/api/v1/transactions", tags=["transaction-monitoring"])


@router.post("/analyze", response_model=TransactionAnalysisOut)
def analyze_transaction(payload: TransactionIn, db: Session = Depends(get_db)):
    service = TransactionMonitoringService(db)
    return service.analyze(payload)


@router.get("/{transaction_id}", response_model=TransactionAnalysisOut)
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    transaction = TransactionRepository(db).get_transaction(transaction_id)
    if not transaction or not transaction.analysis:
        raise HTTPException(status_code=404, detail="Transaction introuvable")

    analysis = transaction.analysis
    return TransactionAnalysisOut(
        transaction_id=transaction.transaction_id,
        sender_phone=transaction.sender_phone,
        sender_operator=transaction.sender.operator,
        sender_country=transaction.sender.country,
        receiver_phone=transaction.receiver_phone,
        receiver_country=country_from_phone(transaction.receiver_phone),
        is_cross_border=(
            country_from_phone(transaction.receiver_phone) is not None
            and country_from_phone(transaction.receiver_phone) != transaction.sender.country
        ),
        batch_id=transaction.batch_id,
        amount=transaction.amount,
        currency=transaction.currency,
        transaction_type=transaction.transaction_type,
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
    )
