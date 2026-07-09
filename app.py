from __future__ import annotations

import base64
import threading
import time
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

from service.attendance_service import GymAttendanceService
from service.hr_service import AccountService
from service.person_service import PersonService
from service.recognize_service import RecognizeService
from service.record_service import GymRecordService
from service.statistics_service import GymStatisticsService
from util.io_tools import LOCK_RECORD_FILE, PERSONNEL_FILE, USER_PASSWORD_FILE
from util.public_tools import format_duration
from util.camera import Camera, CameraError, cv2


app = Flask(__name__)
app.secret_key = "gym-checkin-system-secret-key"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


class CameraStream:
    """Keep one camera reader alive so web preview does not reopen the device per frame."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.recognize_service = RecognizeService()
        self.latest_raw_frame: Any = None
        self.latest_jpeg: bytes | None = None
        self.available = False
        self.face_count = 0
        self.recognition: Dict[str, Any] | None = None
        self.message = "摄像头尚未启动。"
        self.last_update = 0.0

    def start(self) -> None:
        if cv2 is None:
            with self.lock:
                self.available = False
                self.message = "未安装 OpenCV。"
            return
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _set_status(self, available: bool, message: str) -> None:
        with self.lock:
            self.available = available
            self.message = message

    def _run(self) -> None:
        camera = Camera(0)
        try:
            camera.open()
            if camera.capture is not None:
                camera.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                camera.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                camera.capture.set(cv2.CAP_PROP_FPS, 15)
                camera.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            while True:
                frame = camera.read_frame()
                raw_frame = frame.copy()
                frame, face_count, recognition = self.recognize_service.annotate_frame(frame)
                ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    if recognition and recognition.get("recognized") and recognition.get("person_id"):
                        message = f"已识别：{recognition['person_id']}。"
                    elif face_count:
                        message = f"已检测到 {face_count} 张人脸。"
                    else:
                        message = "摄像头画面正常，暂未检测到人脸。"
                    with self.lock:
                        self.latest_raw_frame = raw_frame
                        self.latest_jpeg = buffer.tobytes()
                        self.available = True
                        self.face_count = face_count
                        self.recognition = recognition
                        self.message = message
                        self.last_update = time.time()
                time.sleep(0.07)
        except CameraError as exc:
            self._set_status(False, str(exc))
        finally:
            camera.release()

    def reload_recognizer(self) -> None:
        self.recognize_service = RecognizeService()

    def snapshot(self) -> Dict[str, Any]:
        self.start()
        with self.lock:
            return {
                "available": self.available,
                "face_count": self.face_count,
                "recognition": self.recognition,
                "message": self.message,
                "has_frame": self.latest_jpeg is not None,
                "last_update": self.last_update,
            }

    def frame(self) -> bytes | None:
        self.start()
        with self.lock:
            return self.latest_jpeg

    def raw_frame(self) -> Any:
        self.start()
        with self.lock:
            if self.latest_raw_frame is None:
                return None
            return self.latest_raw_frame.copy()


camera_stream = CameraStream()
AUTO_CHECKIN_COOLDOWN_SECONDS = 8
auto_checkin_times: Dict[str, float] = {}


@app.after_request
def add_no_cache_headers(response: Any) -> Any:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)

    return wrapper


def api_login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not session.get("logged_in"):
            return jsonify({"ok": False, "message": "请先登录。"}), 401
        return view(*args, **kwargs)

    return wrapper


def make_services() -> tuple[GymRecordService, GymAttendanceService, GymStatisticsService]:
    record_service = GymRecordService()
    attendance_service = GymAttendanceService(record_service)
    statistics_service = GymStatisticsService(record_service)
    return record_service, attendance_service, statistics_service


def record_to_dict(record: Any) -> Dict[str, Any]:
    data = record.to_dict()
    data["duration_text"] = format_duration(data.get("duration_seconds"))
    data["status"] = "在馆" if record.is_inside else "已离馆"
    return data


def report_row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    item["stay_text"] = format_duration(int(item.get("stay_seconds", 0)))
    return item


def render_page(template: str, active: str, title: str) -> str:
    return render_template(template, active=active, title=title)


@app.route("/")
def index() -> Any:
    if session.get("logged_in"):
        return redirect(url_for("dashboard_page"))
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page() -> str:
    return render_template("login.html")


@app.route("/logout")
def logout() -> Any:
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/dashboard")
@login_required
def dashboard_page() -> str:
    return render_page("dashboard.html", "dashboard", "首页 Dashboard")


@app.route("/video")
@login_required
def video_page() -> str:
    return render_page("video_checkin.html", "video", "视频打卡")


def generate_camera_frames() -> Any:
    while True:
        frame = camera_stream.frame()
        if frame is not None:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame
                + b"\r\n"
            )
        time.sleep(0.07)


def capture_annotated_frame() -> Dict[str, Any]:
    status = camera_stream.snapshot()
    frame = camera_stream.frame()
    if frame is not None:
        status["image"] = "data:image/jpeg;base64," + base64.b64encode(frame).decode("ascii")
    return status


@app.route("/video_feed")
@login_required
def video_feed() -> Response:
    return Response(
        generate_camera_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/camera/status")
@api_login_required
def api_camera_status() -> Any:
    if cv2 is None:
        return jsonify({"ok": True, "data": {"available": False, "message": "未安装 OpenCV。"}})

    recognize_service = RecognizeService()
    status = camera_stream.snapshot()
    if recognize_service.face_detection_available:
        model_message = "人脸检测已启用。"
    else:
        model_message = "OpenCV 人脸检测模型未加载。"
    if status["available"] or status["has_frame"]:
        status["message"] = f"{status['message']} {model_message}"
    elif status["message"] == "摄像头尚未启动。":
        status["message"] = f"摄像头正在启动... {model_message}"
    return jsonify({"ok": True, "data": status})


@app.get("/api/camera/frame")
@api_login_required
def api_camera_frame() -> Any:
    return jsonify({"ok": True, "data": capture_annotated_frame()})


@app.post("/api/face/enroll")
@api_login_required
def api_face_enroll() -> Any:
    payload = request.get_json(silent=True) or {}
    person_id = str(payload.get("person_id", "")).strip()
    if not PersonService().find_person(person_id):
        return jsonify({"ok": False, "message": "请先在人员管理中添加该人员编号。"}), 400

    frame = camera_stream.raw_frame()
    if frame is None:
        return jsonify({"ok": False, "message": "摄像头画面尚未准备好。"}), 400
    try:
        result = RecognizeService().save_face_sample(person_id, frame)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    return jsonify({"ok": True, "data": result})


@app.post("/api/face/train")
@api_login_required
def api_face_train() -> Any:
    try:
        result = RecognizeService().train_model()
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    camera_stream.reload_recognizer()
    return jsonify({"ok": True, "data": result})


@app.get("/api/face/recognize")
@api_login_required
def api_face_recognize() -> Any:
    frame = camera_stream.raw_frame()
    if frame is None:
        return jsonify({"ok": False, "message": "摄像头画面尚未准备好。"}), 400
    result = RecognizeService().best_recognition(frame)
    if result.get("person_id"):
        person = PersonService().find_person(str(result["person_id"]))
        if person:
            result["person_name"] = person.get("name", result["person_id"])
    return jsonify({"ok": True, "data": result})


@app.post("/api/face/auto_checkin")
@api_login_required
def api_face_auto_checkin() -> Any:
    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode", "enter")).strip()
    if mode not in {"enter", "leave"}:
        return jsonify({"ok": False, "message": "自动打卡模式只能是入馆或离馆。"}), 400

    frame = camera_stream.raw_frame()
    if frame is None:
        return jsonify({"ok": False, "message": "摄像头画面尚未准备好。"}), 400

    recognition = RecognizeService().best_recognition(frame)
    if not recognition.get("recognized") or not recognition.get("person_id"):
        return jsonify({"ok": False, "message": "暂未识别到已训练人员。"}), 400

    person_id = str(recognition["person_id"])
    person = PersonService().find_person(person_id)
    if not person:
        return jsonify({"ok": False, "message": f"识别到 {person_id}，但人员档案不存在。"}), 400

    now = time.time()
    cooldown_key = f"{mode}:{person_id}"
    last_time = auto_checkin_times.get(cooldown_key, 0)
    if now - last_time < AUTO_CHECKIN_COOLDOWN_SECONDS:
        return jsonify(
            {
                "ok": True,
                "data": {
                    "skipped": True,
                    "message": f"{person.get('name', person_id)} 刚刚已自动打卡，请稍后再试。",
                    "recognition": recognition,
                },
            }
        )

    record_service, attendance_service, _statistics_service = make_services()
    try:
        if mode == "enter":
            if record_service.find_open_record(person_id):
                return jsonify(
                    {
                        "ok": True,
                        "data": {
                            "skipped": True,
                            "message": f"{person.get('name', person_id)} 当前已在馆。",
                            "recognition": recognition,
                        },
                    }
                )
            record = attendance_service.person_enter(person_id, person.get("name", person_id))
            action = "enter"
        else:
            record = attendance_service.person_leave(person_id)
            action = "leave"
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    auto_checkin_times[cooldown_key] = now
    return jsonify(
        {
            "ok": True,
            "data": {
                "skipped": False,
                "action": action,
                "message": f"{person.get('name', person_id)} 自动{'入馆' if action == 'enter' else '离馆'}成功。",
                "record": record_to_dict(record),
                "recognition": recognition,
            },
        }
    )


@app.route("/persons")
@login_required
def persons_page() -> str:
    return render_page("persons.html", "persons", "人员管理")


@app.route("/inside")
@login_required
def inside_page() -> str:
    return render_page("inside.html", "inside", "场馆人员")


@app.route("/records")
@login_required
def records_page() -> str:
    return render_page("records.html", "records", "到馆记录")


@app.route("/analytics")
@login_required
def analytics_page() -> str:
    return render_page("analytics.html", "analytics", "数据分析")


@app.route("/settings")
@login_required
def settings_page() -> str:
    return render_page("settings.html", "settings", "系统设置")


@app.post("/api/login")
def api_login() -> Any:
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    if AccountService().authenticate(username, password):
        session["logged_in"] = True
        session["username"] = username
        return jsonify({"ok": True, "redirect": url_for("dashboard_page")})
    return jsonify({"ok": False, "message": "账号或密码错误。"}), 401


@app.get("/api/summary")
@api_login_required
def api_summary() -> Any:
    _record_service, _attendance_service, statistics_service = make_services()
    summary = statistics_service.today_summary()
    summary["average_stay_text"] = format_duration(summary["average_stay_seconds"])
    summary["today_stay_text"] = format_duration(summary["today_stay_seconds"])
    return jsonify({"ok": True, "data": summary})


@app.route("/api/persons", methods=["GET", "POST"])
@api_login_required
def api_persons() -> Any:
    person_service = PersonService()
    if request.method == "GET":
        return jsonify({"ok": True, "data": person_service.list_persons()})

    payload = request.get_json(silent=True) or {}
    try:
        person = person_service.add_or_update(
            str(payload.get("person_id", "")),
            str(payload.get("name", "")),
            str(payload.get("phone", "")),
            str(payload.get("remark", "")),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    return jsonify({"ok": True, "data": person})


@app.post("/api/checkin/enter")
@api_login_required
def api_enter() -> Any:
    payload = request.get_json(silent=True) or {}
    person_id = str(payload.get("person_id", "")).strip()
    person_name = str(payload.get("person_name", "")).strip()

    person = PersonService().find_person(person_id)
    if not person_name and person:
        person_name = person.get("name", "")

    _record_service, attendance_service, _statistics_service = make_services()
    try:
        record = attendance_service.person_enter(person_id, person_name or person_id)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    return jsonify({"ok": True, "data": record_to_dict(record)})


@app.post("/api/checkin/leave")
@api_login_required
def api_leave() -> Any:
    payload = request.get_json(silent=True) or {}
    person_id = str(payload.get("person_id", "")).strip()

    _record_service, attendance_service, _statistics_service = make_services()
    try:
        record = attendance_service.person_leave(person_id)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    return jsonify({"ok": True, "data": record_to_dict(record)})


@app.get("/api/inside")
@api_login_required
def api_inside() -> Any:
    _record_service, attendance_service, _statistics_service = make_services()
    records = [record_to_dict(record) for record in attendance_service.current_inside()]
    return jsonify({"ok": True, "data": records})


@app.get("/api/records")
@api_login_required
def api_records() -> Any:
    _record_service, attendance_service, _statistics_service = make_services()
    records = [record_to_dict(record) for record in attendance_service.all_records()]
    records.sort(key=lambda item: int(item.get("sequence", 0)), reverse=True)
    return jsonify({"ok": True, "data": records})


@app.get("/api/analytics")
@api_login_required
def api_analytics() -> Any:
    _record_service, _attendance_service, statistics_service = make_services()
    today = date.today()
    daily_reports = []
    for offset in range(6, -1, -1):
        target_date = today - timedelta(days=offset)
        report = statistics_service.daily_duration_report(target_date)
        daily_reports.append(
            {
                "date": target_date.strftime("%m-%d"),
                "people_count": report["people_count"],
                "records_count": report["records_count"],
                "stay_minutes": round(int(report["total_stay_seconds"]) / 60, 2),
            }
        )

    monthly_report = statistics_service.monthly_duration_report(today)
    monthly_rows = [report_row_to_dict(row) for row in monthly_report["rows"]]
    return jsonify(
        {
            "ok": True,
            "data": {
                "daily": daily_reports,
                "month": monthly_report["month"],
                "monthly_rows": monthly_rows,
                "monthly_total_text": format_duration(monthly_report["total_stay_seconds"]),
            },
        }
    )


@app.get("/api/settings")
@api_login_required
def api_settings() -> Any:
    persons = PersonService().list_persons()
    record_service, _attendance_service, _statistics_service = make_services()
    files: List[Dict[str, Any]] = []
    for label, path in [
        ("账号文件", USER_PASSWORD_FILE),
        ("打卡记录文件", LOCK_RECORD_FILE),
        ("人员文件", PERSONNEL_FILE),
    ]:
        file_path = Path(path)
        files.append(
            {
                "label": label,
                "path": str(file_path),
                "exists": file_path.exists(),
                "size": file_path.stat().st_size if file_path.exists() else 0,
            }
        )
    return jsonify(
        {
            "ok": True,
            "data": {
                "username": session.get("username", ""),
                "files": files,
                "person_count": len(persons),
                "record_count": len(record_service.all_records()),
            },
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
