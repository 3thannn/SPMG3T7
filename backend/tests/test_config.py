from app.config import cors_origins, session_idle_minutes


def test_defaults_to_local_frontend(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert cors_origins() == ["http://localhost:5173"]


def test_splits_and_trims_configured_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com, https://b.example.com ")
    assert cors_origins() == ["https://a.example.com", "https://b.example.com"]


def test_session_idle_defaults_to_thirty_minutes(monkeypatch):
    monkeypatch.delenv("SESSION_IDLE_MINUTES", raising=False)
    assert session_idle_minutes() == 30


def test_session_idle_is_configurable(monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "15")
    assert session_idle_minutes() == 15


def test_a_nonsense_idle_window_falls_back_rather_than_never_expiring(monkeypatch):
    for value in ("", "soon", "0", "-5"):
        monkeypatch.setenv("SESSION_IDLE_MINUTES", value)
        assert session_idle_minutes() == 30
