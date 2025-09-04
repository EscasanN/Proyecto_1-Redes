import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL") or "claude-3-haiku-20240307"
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR") or "workspace").resolve()

LOG_PATH = Path(os.getenv("LOG_PATH") or "logs/mcp_interactions.log.jsonl").resolve()

SERVERS_YAML = Path(os.getenv("SERVERS_YAML") or "servers.yaml")
SERVERS_EXAMPLE = Path("servers.example.yaml")