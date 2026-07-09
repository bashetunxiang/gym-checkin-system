from __future__ import annotations

from typing import List, Optional

from entity.organizations import GymCheckinRecord
from service.record_service import GymRecordService


class GymAttendanceService:
    """体育馆视频打卡业务服务。"""

    def __init__(self, record_service: Optional[GymRecordService] = None) -> None:
        self.record_service = record_service or GymRecordService()

    def person_enter(self, person_id: str, person_name: Optional[str] = None) -> GymCheckinRecord:
        return self.record_service.enter(person_id, person_name)

    def person_leave(self, person_id: str) -> GymCheckinRecord:
        return self.record_service.leave(person_id)

    def current_inside(self) -> List[GymCheckinRecord]:
        return self.record_service.current_inside()

    def all_records(self) -> List[GymCheckinRecord]:
        return self.record_service.all_records()
