import os


def cors_origins() -> list[str]:
    """Origins allowed to call this API.

    Set CORS_ORIGINS to a comma-separated list to override the local default,
    e.g. CORS_ORIGINS="https://spmg3t7.example.com,http://localhost:5173"
    """
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
