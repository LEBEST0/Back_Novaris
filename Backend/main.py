from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import api_router
from shared.config.settings import settings
from shared.database.database import Base, engine
from modules.transaction_monitoring import models  # noqa: F401 (enregistre les tables)
from modules.wallet_access import models as wallet_models  # noqa: F401 (enregistre les tables)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

# Dev local : tout port localhost/127.0.0.1 (Vite change de port tout seul si 5173 est
# déjà occupé). Production : les deux frontends déployés sur Vercel, en autorisant aussi
# les URLs de preview (*.vercel.app) pour ne pas casser le déploiement à chaque nouveau hash.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://backnovaris.vercel.app",
        "https://novaris-amani-wallet.vercel.app",
    ],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$|^https://[a-z0-9-]+\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
