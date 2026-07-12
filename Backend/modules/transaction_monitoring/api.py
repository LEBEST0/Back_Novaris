from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db
from modules.transaction_monitoring.presenters import transaction_to_analysis_out
from modules.transaction_monitoring.repository import TransactionRepository
from modules.transaction_monitoring.schemas import (
    DashboardKpisOut,
    DashboardTrendPointOut,
    FeedbackIn,
    NetworkGraphOut,
    TransactionAnalysisOut,
    TransactionIn,
)
from modules.transaction_monitoring.service import TransactionMonitoringService

router = APIRouter(prefix="/api/v1/transactions", tags=["transaction-monitoring"])
dashboard_router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.post("/analyze", response_model=TransactionAnalysisOut)
def analyze_transaction(payload: TransactionIn, db: Session = Depends(get_db)):
    service = TransactionMonitoringService(db)
    return service.analyze(payload)


@router.get("", response_model=list[TransactionAnalysisOut])
def list_transactions(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """Transactions les plus récentes, analyse incluse — alimente la table/les alertes
    du dashboard admin. `limit` plafonné pour éviter une requête involontairement énorme."""
    limit = max(1, min(limit, 200))
    transactions = TransactionRepository(db).list_transactions(limit=limit, offset=offset)
    return [transaction_to_analysis_out(t, db) for t in transactions if t.analysis]


@router.get("/network", response_model=NetworkGraphOut)
def get_network_graph(limit: int = 500, db: Session = Depends(get_db)):
    """Graphe réseau construit à partir de TOUTES les transactions récentes (pas une
    seule) — nœuds clients/agents/devices, arêtes = transactions. Doit être déclaré avant
    /{transaction_id} pour ne pas être capturé par la route générique."""
    limit = max(1, min(limit, 2000))
    return TransactionMonitoringService(db).build_network_graph(limit=limit)


@router.get("/{transaction_id}", response_model=TransactionAnalysisOut)
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    transaction = TransactionRepository(db).get_transaction(transaction_id)
    if not transaction or not transaction.analysis:
        raise HTTPException(status_code=404, detail="Transaction introuvable")
    return transaction_to_analysis_out(transaction, db)


@router.patch("/{transaction_id}/feedback", response_model=TransactionAnalysisOut)
def submit_feedback(transaction_id: str, payload: FeedbackIn, db: Session = Depends(get_db)):
    """Retour d'un analyste après revue (dashboard admin) : confirme l'alerte ou
    l'écarte comme faux positif. Piste d'audit pour mesurer la precision perçue."""
    transaction = TransactionRepository(db).set_feedback(
        transaction_id, feedback=payload.feedback, note=payload.note
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction introuvable")
    return transaction_to_analysis_out(transaction, db)


@dashboard_router.get("/kpis", response_model=DashboardKpisOut)
def dashboard_kpis(db: Session = Depends(get_db)):
    return TransactionRepository(db).get_dashboard_kpis()


@dashboard_router.get("/trend", response_model=list[DashboardTrendPointOut])
def dashboard_trend(days: int = 7, db: Session = Depends(get_db)):
    days = max(1, min(days, 90))
    return TransactionRepository(db).get_dashboard_trend(days=days)
