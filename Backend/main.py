from fastapi import FastAPI

from api.router import api_router
from shared.config.settings import settings
from shared.database.database import Base, engine
from modules.transaction_monitoring import models  # noqa: F401 (enregistre les tables)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)
app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
