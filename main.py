from __future__ import annotations

from entity.organizations import GymCheckinRecord
from service.attendance_service import GymAttendanceService
from service.hr_service import login
from service.person_service import PersonService
from service.recognize_service import RecognizeService
from service.record_service import GymRecordService
from service.statistics_service import GymStatisticsService
from util.public_tools import format_duration, prompt_optional, prompt_required


def print_header() -> None:
    print("=" * 50)
    print("体育馆视频打卡管理系统")
    print("=" * 50)


def print_menu() -> None:
    print()
    print("1. 人员管理")
    print("2. 人员进入场馆")
    print("3. 人员离开场馆")
    print("4. 查询当前在馆人员")
    print("5. 查询全部到馆记录")
    print("6. 查看数据统计")
    print("7. 摄像头识别入馆")
    print("8. 摄像头识别离馆")
    print("9. 日报（今天在馆时长）")
    print("10. 月报（本月在馆时长）")
    print("0. 退出系统")


def print_person_menu() -> None:
    print()
    print("1. 添加或更新人员")
    print("2. 查看人员列表")
    print("3. 查询人员")
    print("0. 返回主菜单")


def print_person(person: dict) -> None:
    print(
        f"编号: {person.get('person_id', '')} | 姓名: {person.get('name', '')} | "
        f"电话: {person.get('phone', '')} | 备注: {person.get('remark', '')}"
    )


def print_record(record: GymCheckinRecord) -> None:
    leave_time = record.leave_time or "未离馆"
    print(
        f"第{record.sequence}位 | 编号: {record.person_id} | 姓名: {record.person_name} | "
        f"入馆: {record.enter_time} | 离馆: {leave_time} | 停留: {format_duration(record.duration_seconds)}"
    )


def print_duration_report(title: str, report: dict) -> None:
    print(title)
    print(f"统计范围：{report['start']} 至 {report['end']}")
    print(f"到馆人数：{report['people_count']}")
    print(f"到馆次数：{report['records_count']}")
    print(f"累计在馆时长：{format_duration(report['total_stay_seconds'])}")
    rows = report["rows"]
    if not rows:
        print("暂无在馆时长记录。")
        return
    for row in rows:
        print(
            f"编号: {row['person_id']} | 姓名: {row['person_name']} | "
            f"到馆次数: {row['visit_count']} | 在馆时长: {format_duration(row['stay_seconds'])}"
        )


def handle_person_management(person_service: PersonService) -> None:
    while True:
        print_person_menu()
        choice = input("请选择人员管理操作: ").strip()
        if choice == "0":
            return
        if choice == "1":
            person_id = prompt_required("人员编号")
            name = prompt_optional("人员姓名（可直接回车使用编号）", person_id)
            phone = prompt_optional("联系电话")
            remark = prompt_optional("备注")
            person = person_service.add_or_update(person_id, name, phone, remark)
            print("人员信息已保存。")
            print_person(person)
        elif choice == "2":
            persons = person_service.list_persons()
            if not persons:
                print("暂无人员信息。")
                continue
            print(f"人员数量：{len(persons)}")
            for person in persons:
                print_person(person)
        elif choice == "3":
            person_id = prompt_required("人员编号")
            person = person_service.find_person(person_id)
            if person is None:
                print("未找到该人员。")
            else:
                print_person(person)
        else:
            print("无效操作，请重新选择。")


def resolve_person_name(person_service: PersonService, person_id: str, typed_name: str) -> str:
    if typed_name:
        return typed_name
    person = person_service.find_person(person_id)
    if person:
        return person.get("name") or person_id
    return person_id


def handle_enter(
    attendance_service: GymAttendanceService,
    person_service: PersonService,
) -> None:
    person_id = prompt_required("人员编号")
    typed_name = prompt_optional("人员姓名（可直接回车使用已登记姓名或编号）")
    person_name = resolve_person_name(person_service, person_id, typed_name)
    record = attendance_service.person_enter(person_id, person_name)
    print(f"入馆成功：{record.person_name} 是第 {record.sequence} 个进入场馆人员。")
    print_record(record)


def handle_leave(attendance_service: GymAttendanceService) -> None:
    person_id = prompt_required("人员编号")
    record = attendance_service.person_leave(person_id)
    print("离馆成功。")
    print_record(record)


def handle_current_inside(attendance_service: GymAttendanceService) -> None:
    records = attendance_service.current_inside()
    if not records:
        print("当前没有在馆人员。")
        return
    print(f"当前在馆人数：{len(records)}")
    for record in records:
        print_record(record)


def handle_all_records(attendance_service: GymAttendanceService) -> None:
    records = attendance_service.all_records()
    if not records:
        print("暂无到馆记录。")
        return
    print(f"全部到馆记录：{len(records)} 条")
    for record in records:
        print_record(record)


def handle_statistics(statistics_service: GymStatisticsService) -> None:
    summary = statistics_service.today_summary()
    print(f"统计日期：{summary['date']}")
    print(f"今日到馆人数：{summary['today_enter_count']}")
    print(f"当前在馆人数：{summary['current_inside_count']}")
    print(f"今日离馆人数：{summary['today_leave_count']}")
    print(f"今日累计在馆时长：{format_duration(summary['today_stay_seconds'])}")
    print(f"平均停留时间：{format_duration(summary['average_stay_seconds'])}")


def handle_daily_report(statistics_service: GymStatisticsService) -> None:
    report = statistics_service.daily_duration_report()
    print_duration_report(f"日报：{report['date']} 在馆时长", report)


def handle_monthly_report(statistics_service: GymStatisticsService) -> None:
    report = statistics_service.monthly_duration_report()
    print_duration_report(f"月报：{report['month']} 在馆时长", report)


def handle_camera_enter(
    attendance_service: GymAttendanceService,
    recognize_service: RecognizeService,
) -> None:
    result = recognize_service.recognize_from_camera()
    if result is None:
        print("未识别到人员，请手动录入。")
        result = recognize_service.manual_fallback()
    person_id, person_name = result
    record = attendance_service.person_enter(person_id, person_name)
    print(f"识别入馆成功：第 {record.sequence} 个进入场馆。")
    print_record(record)


def handle_camera_leave(
    attendance_service: GymAttendanceService,
    recognize_service: RecognizeService,
) -> None:
    result = recognize_service.recognize_from_camera()
    if result is None:
        print("未识别到人员，请手动录入。")
        result = recognize_service.manual_fallback()
    person_id, _person_name = result
    record = attendance_service.person_leave(person_id)
    print("识别离馆成功。")
    print_record(record)


def main() -> None:
    print_header()
    if not login():
        return

    record_service = GymRecordService()
    attendance_service = GymAttendanceService(record_service)
    statistics_service = GymStatisticsService(record_service)
    recognize_service = RecognizeService()
    person_service = PersonService()

    actions = {
        "1": lambda: handle_person_management(person_service),
        "2": lambda: handle_enter(attendance_service, person_service),
        "3": lambda: handle_leave(attendance_service),
        "4": lambda: handle_current_inside(attendance_service),
        "5": lambda: handle_all_records(attendance_service),
        "6": lambda: handle_statistics(statistics_service),
        "7": lambda: handle_camera_enter(attendance_service, recognize_service),
        "8": lambda: handle_camera_leave(attendance_service, recognize_service),
        "9": lambda: handle_daily_report(statistics_service),
        "10": lambda: handle_monthly_report(statistics_service),
    }

    while True:
        print_menu()
        choice = input("请选择操作: ").strip()
        if choice == "0":
            print("已退出系统。")
            return
        action = actions.get(choice)
        if action is None:
            print("无效操作，请重新选择。")
            continue
        try:
            action()
        except ValueError as exc:
            print(exc)


if __name__ == "__main__":
    main()
