from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from modules.transaction_monitoring.feature_engineering import HistoryEntry, IncomingEntry
from modules.transaction_monitoring.models import Customer, Transaction, TransactionAnalysis
from shared.utils.currency import to_xof_equivalent
from shared.utils.id_generator import generate_customer_id, generate_transaction_id
from shared.utils.phone import country_from_phone, operator_from_phone

# On ne remonte jamais plus de 30 jours d'historique : c'est la fenêtre la plus large
# utilisée par les règles/features (moyenne 30j), inutile de charger plus.
HISTORY_WINDOW_DAYS = 30


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_customer_by_phone(self, phone: str) -> Customer | None:
        return self.db.scalar(select(Customer).where(Customer.phone == phone))

    def get_or_create_customer(self, phone: str, *, now: datetime) -> Customer:
        customer = self.get_customer_by_phone(phone)
        if customer:
            return customer
        customer = Customer(
            customer_id=generate_customer_id(),
            phone=phone,
            full_name="Client inconnu",
            kyc_level="basic",
            customer_type="individual",
            operator=operator_from_phone(phone),
            country=country_from_phone(phone) or "Côte d'Ivoire",
            home_city="Abidjan",
            account_created_at=now,
        )
        self.db.add(customer)
        self.db.flush()
        return customer

    def get_sender_history(self, sender_phone: str, *, before: datetime) -> list[HistoryEntry]:
        window_start = before - timedelta(days=HISTORY_WINDOW_DAYS)
        rows = self.db.scalars(
            select(Transaction)
            .where(Transaction.sender_phone == sender_phone)
            .where(Transaction.created_at >= window_start)
            .where(Transaction.created_at < before)
        ).all()
        return [
            HistoryEntry(
                receiver_phone=r.receiver_phone,
                amount_xof_equivalent=to_xof_equivalent(r.amount, r.currency),
                created_at=r.created_at,
                transaction_type=r.transaction_type,
                agent_id=r.agent_id,
                device_id=r.device_id,
            )
            for r in rows
        ]

    def get_receiver_history(self, receiver_phone: str, *, before: datetime) -> list[IncomingEntry]:
        """Transferts reçus par ce numéro (lui en tant que destinataire) sur la même
        fenêtre de 30 jours que get_sender_history — utilisée pour la détection de transit
        transfrontalier (reçu puis renvoyé rapidement vers un autre pays) et de cycles
        type compte mule (cf. feature_engineering.compute_passthrough_cycles)."""
        window_start = before - timedelta(days=HISTORY_WINDOW_DAYS)
        rows = self.db.scalars(
            select(Transaction)
            .where(Transaction.receiver_phone == receiver_phone)
            .where(Transaction.transaction_type == "transfer")
            .where(Transaction.created_at >= window_start)
            .where(Transaction.created_at < before)
        ).all()
        return [
            IncomingEntry(
                sender_country=country_from_phone(r.sender_phone),
                amount_xof_equivalent=to_xof_equivalent(r.amount, r.currency),
                created_at=r.created_at,
                transaction_type=r.transaction_type,
                sender_phone=r.sender_phone,
            )
            for r in rows
        ]

    def save_transaction_with_analysis(
        self,
        *,
        sender: Customer,
        payload,
        timestamp: datetime,
        rule_score: float,
        ml_score: float,
        final_score: float,
        risk_level: str,
        decision: str,
        confidence: float,
        reasons: list[str],
        rule_flags: list[dict],
        top_ml_factors: list[str],
        model_version: str,
    ) -> Transaction:
        transaction = Transaction(
            transaction_id=generate_transaction_id(),
            sender_phone=sender.phone,
            receiver_phone=payload.receiver_phone,
            amount=payload.amount,
            currency=payload.currency,
            transaction_type=payload.transaction_type,
            channel=payload.channel,
            device_id=payload.device_id,
            sender_city=payload.sender_city,
            note=payload.note,
            agent_id=payload.agent_id,
            balance_before_sender=payload.balance_before_sender,
            balance_after_sender=payload.balance_after_sender,
            created_at=timestamp,
        )
        self.db.add(transaction)
        self.db.flush()

        analysis = TransactionAnalysis(
            transaction_id=transaction.transaction_id,
            rule_score=rule_score,
            ml_score=ml_score,
            final_score=final_score,
            risk_level=risk_level,
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            rule_flags=rule_flags,
            top_ml_factors=top_ml_factors,
            model_version=model_version,
            computed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(transaction)
        return transaction

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        return self.db.scalar(
            select(Transaction).where(Transaction.transaction_id == transaction_id)
        )

    def list_transactions(self, limit: int = 50, offset: int = 0) -> list[Transaction]:
        return list(
            self.db.scalars(
                select(Transaction)
                .order_by(Transaction.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def list_transactions_for_network(self, limit: int = 500) -> list[Transaction]:
        """Toutes les transactions récentes (avec émetteur + analyse préchargés) pour
        construire le graphe réseau complet — pas juste une transaction isolée."""
        return list(
            self.db.scalars(
                select(Transaction)
                .options(selectinload(Transaction.sender), selectinload(Transaction.analysis))
                .order_by(Transaction.created_at.desc())
                .limit(limit)
            )
        )

    def get_customers_by_phones(self, phones: set[str]) -> dict[str, Customer]:
        if not phones:
            return {}
        rows = self.db.scalars(select(Customer).where(Customer.phone.in_(phones))).all()
        return {c.phone: c for c in rows}

    def search_customers(self, query: str, limit: int = 20) -> list[Customer]:
        """Recherche par numéro ou nom (préfixe/sous-chaîne) — alimente le sélecteur de
        compte de l'écran Analyse manuelle (Admin), qui doit pouvoir choisir un client
        réel de la base plutôt que de saisir un numéro au hasard."""
        like = f"%{query}%"
        return list(
            self.db.scalars(
                select(Customer)
                .where(Customer.phone.ilike(like) | Customer.full_name.ilike(like))
                .order_by(Customer.account_created_at.desc())
                .limit(limit)
            )
        )

    def get_last_device_id(self, phone: str) -> str | None:
        return self.db.scalar(
            select(Transaction.device_id)
            .where(Transaction.sender_phone == phone)
            .where(Transaction.device_id.is_not(None))
            .order_by(Transaction.created_at.desc())
            .limit(1)
        )

    def set_feedback(self, transaction_id: str, *, feedback: str, note: str | None) -> Transaction | None:
        transaction = self.get_transaction(transaction_id)
        if not transaction or not transaction.analysis:
            return None
        transaction.analysis.analyst_feedback = feedback
        transaction.analysis.feedback_note = note
        transaction.analysis.feedback_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.commit()
        self.db.refresh(transaction)
        return transaction

    def get_dashboard_kpis(self) -> dict:
        """Agrégats pour le dashboard admin — calculés directement en base, jamais
        estimés côté frontend, pour rester fidèles à ce qui a réellement été analysé."""
        total = self.db.scalar(select(func.count(TransactionAnalysis.id))) or 0
        if total == 0:
            return {
                "transactions_analyzed": 0,
                "active_alerts": 0,
                "blocking_rate": 0.0,
                "average_score": 0.0,
                "pending_analyst_review": 0,
                "fraud_amount_confirmed": 0.0,
                "false_positive_rate": None,
            }

        active_alerts = self.db.scalar(
            select(func.count(TransactionAnalysis.id)).where(TransactionAnalysis.decision != "ALLOW")
        ) or 0
        blocked = self.db.scalar(
            select(func.count(TransactionAnalysis.id)).where(TransactionAnalysis.decision == "TEMPORARY_BLOCK")
        ) or 0
        average_score = self.db.scalar(select(func.avg(TransactionAnalysis.final_score))) or 0.0
        pending_review = self.db.scalar(
            select(func.count(TransactionAnalysis.id))
            .where(TransactionAnalysis.decision.in_(["REVIEW", "TEMPORARY_BLOCK"]))
            .where(TransactionAnalysis.analyst_feedback.is_(None))
        ) or 0
        fraud_amount_confirmed = self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0.0))
            .join(TransactionAnalysis, TransactionAnalysis.transaction_id == Transaction.transaction_id)
            .where(TransactionAnalysis.analyst_feedback == "CONFIRMED")
        ) or 0.0
        feedback_total = self.db.scalar(
            select(func.count(TransactionAnalysis.id)).where(TransactionAnalysis.analyst_feedback.is_not(None))
        ) or 0
        false_positive_rate = None
        if feedback_total > 0:
            false_positives = self.db.scalar(
                select(func.count(TransactionAnalysis.id)).where(
                    TransactionAnalysis.analyst_feedback == "FALSE_POSITIVE"
                )
            ) or 0
            false_positive_rate = round(false_positives / feedback_total * 100, 1)

        return {
            "transactions_analyzed": total,
            "active_alerts": active_alerts,
            "blocking_rate": round(blocked / total * 100, 1),
            "average_score": round(average_score, 1),
            "pending_analyst_review": pending_review,
            "fraud_amount_confirmed": fraud_amount_confirmed,
            "false_positive_rate": false_positive_rate,
        }

    def get_risk_distribution(self) -> list[dict]:
        """Répartition par niveau de risque calculée sur TOUTE la base (pas un échantillon
        récent côté client) — un décompte qui baisserait sans suppression donnerait
        l'impression d'un bug, cf. Dashboard "Répartition des risques"."""
        rows = self.db.execute(
            select(
                TransactionAnalysis.risk_level,
                func.count(TransactionAnalysis.id),
                func.avg(TransactionAnalysis.final_score),
            ).group_by(TransactionAnalysis.risk_level)
        ).all()
        by_level = {row[0]: (int(row[1]), float(row[2] or 0.0)) for row in rows}
        return [
            {
                "risk_level": level,
                "count": by_level.get(level, (0, 0.0))[0],
                "average_score": round(by_level.get(level, (0, 0.0))[1], 1),
            }
            for level in ["low", "moderate", "high", "critical"]
        ]

    def get_dashboard_trend(self, days: int = 7) -> list[dict]:
        """Nombre de transactions/alertes/score moyen par jour, sur les `days` derniers
        jours — agrégé en base (func.strftime, portable sur SQLite)."""
        window_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days - 1)
        day_expr = func.strftime("%Y-%m-%d", Transaction.created_at)
        rows = self.db.execute(
            select(
                day_expr.label("day"),
                func.count(Transaction.transaction_id),
                func.sum(func.iif(TransactionAnalysis.decision != "ALLOW", 1, 0)),
                func.avg(TransactionAnalysis.final_score),
            )
            .join(TransactionAnalysis, TransactionAnalysis.transaction_id == Transaction.transaction_id)
            .where(Transaction.created_at >= window_start)
            .group_by(day_expr)
            .order_by(day_expr)
        ).all()
        return [
            {
                "date": row[0],
                "transactions_analyzed": int(row[1] or 0),
                "alerts": int(row[2] or 0),
                "average_score": round(float(row[3] or 0.0), 1),
            }
            for row in rows
        ]
