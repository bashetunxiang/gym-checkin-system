from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from entity.organizations import GymCheckinRecord
from service.record_service import GymRecordService
from util.public_tools import parse_datetime


class GymStatisticsService:
    """体育馆到馆、离馆、日报和月报统计。"""

    def __init__(self, record_service: Optional[GymRecordService] = None) -> None:
        self.record_service = record_service or GymRecordService()

    def _safe_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return parse_datetime(value)
        except (TypeError, ValueError):
            return None

    def _record_overlap_seconds(
        self,
        record: GymCheckinRecord,
        start_time: datetime,
        end_time: datetime,
        now: datetime,
    ) -> int:
        enter_time = self._safe_datetime(record.enter_time)
        if enter_time is None:
            return 0

        leave_time = self._safe_datetime(record.leave_time) or now
        if leave_time < enter_time:
            return 0

        overlap_start = max(enter_time, start_time)
        overlap_end = min(leave_time, end_time)
        if overlap_end <= overlap_start:
            return 0
        return int((overlap_end - overlap_start).total_seconds())

    def _record_in_period(
        self,
        record: GymCheckinRecord,
        start_time: datetime,
        end_time: datetime,
        now: datetime,
    ) -> bool:
        enter_time = self._safe_datetime(record.enter_time)
        if enter_time is None:
            return False

        leave_time = self._safe_datetime(record.leave_time) or now
        if leave_time < enter_time:
            return False
        if enter_time == leave_time:
            return start_time <= enter_time < end_time
        return enter_time < end_time and leave_time > start_time

    def _duration_report(self, start_time: datetime, end_time: datetime) -> Dict[str, object]:
        now = datetime.now()
        rows_by_person: Dict[str, Dict[str, object]] = {}
        total_stay_seconds = 0
        records_count = 0

        for record in self.record_service.all_records():
            if not self._record_in_period(record, start_time, end_time, now):
                continue
            stay_seconds = self._record_overlap_seconds(record, start_time, end_time, now)

            person_id = record.person_id
            row = rows_by_person.setdefault(
                person_id,
                {
                    "person_id": person_id,
                    "person_name": record.person_name,
                    "visit_count": 0,
                    "stay_seconds": 0,
                },
            )
            row["visit_count"] = int(row["visit_count"]) + 1
            row["stay_seconds"] = int(row["stay_seconds"]) + stay_seconds
            total_stay_seconds += stay_seconds
            records_count += 1

        rows: List[Dict[str, object]] = sorted(
            rows_by_person.values(),
            key=lambda item: (-int(item["stay_seconds"]), str(item["person_id"])),
        )
        return {
            "start": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "people_count": len(rows),
            "records_count": records_count,
            "total_stay_seconds": total_stay_seconds,
            "rows": rows,
        }

    def today_summary(self, target_date: Optional[date] = None) -> Dict[str, object]:
        target_date = target_date or date.today()
        today_records = self.record_service.today_records(target_date)
        current_inside = self.record_service.current_inside()
        today_report = self.daily_duration_report(target_date)

        today_leave_count = 0
        for record in self.record_service.all_records():
            leave_time = self._safe_datetime(record.leave_time)
            if leave_time and leave_time.date() == target_date:
                today_leave_count += 1

        records_count = int(today_report["records_count"])
        average_seconds = (
            int(int(today_report["total_stay_seconds"]) / records_count)
            if records_count
            else 0
        )
        return {
            "date": target_date.isoformat(),
            "today_enter_count": len(today_records),
            "current_inside_count": len(current_inside),
            "today_leave_count": today_leave_count,
            "average_stay_seconds": average_seconds,
            "today_stay_seconds": today_report["total_stay_seconds"],
        }

    def daily_duration_report(self, target_date: Optional[date] = None) -> Dict[str, object]:
        target_date = target_date or date.today()
        start_time = datetime.combine(target_date, time.min)
        end_time = start_time + timedelta(days=1)
        report = self._duration_report(start_time, end_time)
        report["date"] = target_date.isoformat()
        return report

    def monthly_duration_report(self, target_date: Optional[date] = None) -> Dict[str, object]:
        target_date = target_date or date.today()
        start_time = datetime.combine(target_date.replace(day=1), time.min)
        if target_date.month == 12:
            next_month = date(target_date.year + 1, 1, 1)
        else:
            next_month = date(target_date.year, target_date.month + 1, 1)
        end_time = datetime.combine(next_month, time.min)
        report = self._duration_report(start_time, end_time)
        report["month"] = target_date.strftime("%Y-%m")
        return report
