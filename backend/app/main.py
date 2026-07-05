from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.shared.database.session import init_db

app = FastAPI(title="Novaris AI", version="1.0.0")

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()

