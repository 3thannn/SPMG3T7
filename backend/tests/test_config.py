from app.config import cors_origins


def test_defaults_to_local_frontend(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert cors_origins() == ["http://localhost:5173"]


def test_splits_and_trims_configured_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com, https://b.example.com ")
    assert cors_origins() == ["https://a.example.com", "https://b.example.com"]
