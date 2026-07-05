from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "Novaris AI - Transaction Monitoring"
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'novaris.db').as_posix()}"

    # Modèle ML
    ml_model_path: str = str(BASE_DIR / "ml_models" / "transaction_risk_model.joblib")
    ml_feature_list_path: str = str(BASE_DIR / "ml_models" / "feature_columns.json")
    ml_model_version: str = "txn-monitoring-v1"

    # Pondération hybride règles / ML dans le score final
    rule_weight: float = 0.45
    ml_weight: float = 0.55

    # Seuils de décision (score final 0-100), alignés sur la matrice du document produit
    threshold_monitor: float = 30.0
    threshold_review: float = 60.0
    threshold_block: float = 80.0

    # Si le score de règles dépasse ce plancher, il impose un score final minimum
    # (garde-fou auditable : le ML seul ne peut pas diluer un signal de règle critique)
    critical_rule_score_floor: float = 80.0

    model_config = SettingsConfigDict(env_prefix="NOVARIS_")


settings = Settings()
