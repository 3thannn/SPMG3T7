"""Test-only proof that API and cleanup use the same Supabase configuration."""
import hashlib
import hmac


def proof(project_url, service_key, challenge):
    message = f'spmg3t7-e2e-identity-v1\n{project_url.rstrip("/")}\n{challenge}'
    return hmac.new(service_key.encode(), message.encode(), hashlib.sha256).hexdigest()
