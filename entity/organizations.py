from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class GymPerson:
    """场馆人员基础信息。"""

    person_id: str
    name: str


@dataclass
class GymCheckinRecord:
    """一次入馆到离馆的完整记录。"""

    sequence: int
    person_id: str
    person_name: str
    enter_time: str
    leave_time: Optional[str] = None
    duration_seconds: Optional[int] = None

    @property
    def is_inside(self) -> bool:
        return self.leave_time is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "person_id": self.person_id,
            "person_name": self.person_name,
            "enter_time": self.enter_time,
            "leave_time": self.leave_time,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GymCheckinRecord":
        return cls(
            sequence=int(data.get("sequence", 0)),
            person_id=str(data.get("person_id", "")).strip(),
            person_name=str(data.get("person_name") or data.get("person_id") or "").strip(),
            enter_time=str(data.get("enter_time", "")).strip(),
            leave_time=data.get("leave_time") or None,
            duration_seconds=data.get("duration_seconds"),
        )
