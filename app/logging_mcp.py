from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any, Dict

class JsonlLogger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.open("a", encoding="utf-8").close()

    def write(self, record: Dict[str, Any]) -> None:
        rec = dict(record)
        rec.setdefault("ts", time.time())
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
