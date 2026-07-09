from __future__ import annotations

from datetime import date
from typing import List, Optional

from entity.organizations import GymCheckinRecord
from util.io_tools import load_lock_record, save_lock_record
from util.public_tools import now_text, parse_datetime


class GymRecordService:
    """体育馆入馆、离馆记录读写服务。"""

    def __init__(self) -> None:
        self.data = load_lock_record()

    def _records(self) -> List[GymCheckinRecord]:
        return [GymCheckinRecord.from_dict(item) for item in self.data.get("records", [])]

    def _save_records(self, records: List[GymCheckinRecord]) -> None:
        self.data["records"] = [record.to_dict() for record in records]
        save_lock_record(self.data)

    def all_records(self) -> List[GymCheckinRecord]:
        return self._records()

    def current_inside(self) -> List[GymCheckinRecord]:
        return [record for record in self._records() if record.is_inside]

    def find_open_record(self, person_id: str) -> Optional[GymCheckinRecord]:
        for record in reversed(self._records()):
            if record.person_id == person_id and record.is_inside:
                return record
        return None

    def enter(self, person_id: str, person_name: Optional[str] = None) -> GymCheckinRecord:
        person_id = person_id.strip()
        person_name = (person_name or person_id).strip()
        if not person_id:
            raise ValueError("人员编号不能为空。")
        if self.find_open_record(person_id):
            raise ValueError(f"{person_id} 当前已在馆，不能重复入馆。")

        sequence = int(self.data.get("next_sequence", 1))
        record = GymCheckinRecord(
            sequence=sequence,
            person_id=person_id,
            person_name=person_name,
            enter_time=now_text(),
        )
        records = self._records()
        records.append(record)
        self.data["next_sequence"] = sequence + 1
        self._save_records(records)
        return record

    def leave(self, person_id: str) -> GymCheckinRecord:
        person_id = person_id.strip()
        if not person_id:
            raise ValueError("人员编号不能为空。")

        records = self._records()
        target: Optional[GymCheckinRecord] = None
        for record in reversed(records):
            if record.person_id == person_id and record.is_inside:
                target = record
                break
        if target is None:
            raise ValueError(f"没有找到 {person_id} 的在馆记录。")

        leave_time = now_text()
        enter_dt = parse_datetime(target.enter_time)
        leave_dt = parse_datetime(leave_time)
        target.leave_time = leave_time
        target.duration_seconds = max(0, int((leave_dt - enter_dt).total_seconds()))
        self._save_records(records)
        return target

    def today_records(self, target_date: Optional[date] = None) -> List[GymCheckinRecord]:
        target_date = target_date or date.today()
        records = []
        for record in self._records():
            try:
                if parse_datetime(record.enter_time).date() == target_date:
                    records.append(record)
            except ValueError:
                continue
        return records
