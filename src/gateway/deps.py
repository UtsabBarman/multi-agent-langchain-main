import os

def get_orchestrator_url() -> str:
    return os.environ.get("ORCHESTRATOR_BASE_URL", "http://127.0.0.1:8000")
