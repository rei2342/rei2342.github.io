import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config


def save_case_output(data: dict, case_name: str) -> Path:
    output_dir = config.OUTPUTS_DIR / "cases"
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = case_name.replace(" ", "_").replace("/", "_")
    filename = f"{safe_name}_{date_str}.json"
    path = output_dir / filename

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_case_output(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def update_case_output(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_prompt(prompt_filename: str) -> str:
    path = config.PROMPTS_DIR / prompt_filename
    return path.read_text(encoding="utf-8")
