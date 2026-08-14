from pathlib import Path
from typing import Any

import yaml


def load_vacancy(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        data = yaml.safe_load(source)
    required = {"vacancy_id", "title", "requirements", "ai_criteria"}
    missing = required - set(data or {})
    if missing:
        raise ValueError(f"Vacancy config is missing: {', '.join(sorted(missing))}")
    return data
