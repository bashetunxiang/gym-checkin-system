from __future__ import annotations

import ast
import copy
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict

from util.public_tools import ensure_directory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
USER_PASSWORD_FILE = DATA_DIR / "user_password.txt"
LOCK_RECORD_FILE = DATA_DIR / "lock_record.txt"
PERSONNEL_FILE = DATA_DIR / "personnel.txt"
LEGACY_USER_PASSWORD_FILE = PROJECT_ROOT / "user_password.txt"
LEGACY_LOCK_RECORD_FILE = PROJECT_ROOT / "lock_record.txt"

DEFAULT_PASSWORDS: Dict[str, str] = {"dhl": "541610"}
DEFAULT_LOCK_RECORD: Dict[str, Any] = {"next_sequence": 1, "records": []}
DEFAULT_PERSONNEL: Dict[str, Any] = {"persons": []}


def _clone_default(default: Any) -> Any:
    return copy.deepcopy(default)


def load_json_file(path: str | Path, default: Any) -> Any:
    path = Path(path)
    if not path.exists():
        return _clone_default(default)

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return _clone_default(default)

    try:
        return json.loads(text)
    except JSONDecodeError:
        pass

    try:
        legacy_data = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return _clone_default(default)

    if isinstance(legacy_data, (dict, list)):
        save_json_file(path, legacy_data)
        return legacy_data
    return _clone_default(default)


def load_json_file_with_legacy(path: str | Path, legacy_path: str | Path, default: Any) -> Any:
    path = Path(path)
    legacy_path = Path(legacy_path)
    if path.exists():
        return load_json_file(path, default)
    if legacy_path.exists():
        data = load_json_file(legacy_path, default)
        try_save_json_file(path, data)
        return data
    return _clone_default(default)


def save_json_file(path: str | Path, data: Any) -> None:
    path = Path(path)
    ensure_directory(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def try_save_json_file(path: str | Path, data: Any) -> bool:
    try:
        save_json_file(path, data)
    except OSError:
        return False
    return True


def load_user_passwords() -> Dict[str, str]:
    data = load_json_file_with_legacy(
        USER_PASSWORD_FILE,
        LEGACY_USER_PASSWORD_FILE,
        DEFAULT_PASSWORDS,
    )
    if not isinstance(data, dict):
        data = {}

    normalized = {str(key): str(value) for key, value in data.items()}
    normalized.update(DEFAULT_PASSWORDS)
    if normalized != data:
        try_save_json_file(USER_PASSWORD_FILE, normalized)
    return normalized


def normalize_lock_record_data(data: Any) -> Dict[str, Any]:
    if isinstance(data, list):
        records = data
        next_sequence = len(records) + 1
    elif isinstance(data, dict):
        records = data.get("records", [])
        next_sequence = data.get("next_sequence", 1)
    else:
        records = []
        next_sequence = 1

    if not isinstance(records, list):
        records = []

    normalized_records = []
    max_sequence = 0
    for item in records:
        if not isinstance(item, dict):
            continue
        try:
            sequence = int(item.get("sequence", 0))
        except (TypeError, ValueError):
            sequence = 0
        if sequence <= 0:
            sequence = len(normalized_records) + 1
        max_sequence = max(max_sequence, sequence)
        normalized_records.append(
            {
                "sequence": sequence,
                "person_id": str(item.get("person_id", "")).strip(),
                "person_name": str(item.get("person_name") or item.get("person_id") or "").strip(),
                "enter_time": str(item.get("enter_time", "")).strip(),
                "leave_time": item.get("leave_time") or None,
                "duration_seconds": item.get("duration_seconds"),
            }
        )

    try:
        next_sequence = int(next_sequence)
    except (TypeError, ValueError):
        next_sequence = 1
    next_sequence = max(next_sequence, max_sequence + 1, 1)
    return {"next_sequence": next_sequence, "records": normalized_records}


def load_lock_record() -> Dict[str, Any]:
    data = load_json_file_with_legacy(
        LOCK_RECORD_FILE,
        LEGACY_LOCK_RECORD_FILE,
        DEFAULT_LOCK_RECORD,
    )
    normalized = normalize_lock_record_data(data)
    if normalized != data:
        try_save_json_file(LOCK_RECORD_FILE, normalized)
    return normalized


def save_lock_record(data: Dict[str, Any]) -> None:
    save_json_file(LOCK_RECORD_FILE, normalize_lock_record_data(data))


def normalize_personnel_data(data: Any) -> Dict[str, Any]:
    if isinstance(data, list):
        persons = data
    elif isinstance(data, dict):
        persons = data.get("persons", [])
    else:
        persons = []

    normalized_persons = []
    seen_ids = set()
    for item in persons:
        if not isinstance(item, dict):
            continue
        person_id = str(item.get("person_id", "")).strip()
        if not person_id or person_id in seen_ids:
            continue
        seen_ids.add(person_id)
        normalized_persons.append(
            {
                "person_id": person_id,
                "name": str(item.get("name") or person_id).strip(),
                "phone": str(item.get("phone", "")).strip(),
                "remark": str(item.get("remark", "")).strip(),
            }
        )
    return {"persons": normalized_persons}


def load_personnel() -> Dict[str, Any]:
    data = load_json_file(PERSONNEL_FILE, DEFAULT_PERSONNEL)
    normalized = normalize_personnel_data(data)
    if normalized != data:
        try_save_json_file(PERSONNEL_FILE, normalized)
    return normalized


def save_personnel(data: Dict[str, Any]) -> None:
    save_json_file(PERSONNEL_FILE, normalize_personnel_data(data))
