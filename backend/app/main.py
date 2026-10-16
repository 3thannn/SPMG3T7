from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.config import cors_origins
from app.equipment import router as equipment_router
from app.events import router as events_router
from app.holds import router as holds_router
from app.notifications import router as notifications_router
from app.venues import router as venues_router

app = FastAPI(title="SPMG3T7 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(events_router)
app.include_router(equipment_router)
app.include_router(venues_router)
app.include_router(notifications_router)
app.include_router(holds_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. The frontend calls this to confirm it can reach the API."""
    return {"status": "ok"}
