from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.config import cors_origins
from app.event_requests import router as event_requests_router
from app.events import router as events_router

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
app.include_router(event_requests_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. The frontend calls this to confirm it can reach the API."""
    return {"status": "ok"}
