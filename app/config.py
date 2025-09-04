import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or ""
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-1.5-flash"

WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR") or "workspace").resolve()
LOG_PATH = Path(os.getenv("LOG_PATH") or "logs/mcp_interactions.log.jsonl").resolve()

SERVERS_YAML = Path(os.getenv("SERVERS_YAML") or "servers.yaml")
SERVERS_EXAMPLE = Path("servers.example.yaml")
