from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import util.io_tools as io_tools
from app import app
from entity.organizations import GymCheckinRecord
from service.hr_service import AccountService


class AccountFlowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_account_file = io_tools.USER_PASSWORD_FILE
        self.original_legacy_file = io_tools.LEGACY_USER_PASSWORD_FILE
        io_tools.USER_PASSWORD_FILE = Path(self.temp_dir.name) / "accounts.json"
        io_tools.LEGACY_USER_PASSWORD_FILE = Path(self.temp_dir.name) / "legacy.json"
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()

    def tearDown(self) -> None:
        io_tools.USER_PASSWORD_FILE = self.original_account_file
        io_tools.LEGACY_USER_PASSWORD_FILE = self.original_legacy_file
        self.temp_dir.cleanup()

    def test_register_duplicate_change_and_recover(self) -> None:
        register = self.client.post("/api/register", json={"username": "new.member"})
        self.assertEqual(register.status_code, 201)
        initial_password = register.get_json()["data"]["initial_password"]
        self.assertEqual(initial_password, "88888888")

        duplicate = self.client.post("/api/register", json={"username": "NEW.member"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("已有人注册", duplicate.get_json()["message"])

        login = self.client.post(
            "/api/login",
            json={"username": "new.member", "password": initial_password},
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.get_json()["data"]["must_change_password"])
        self.assertEqual(login.get_json()["data"]["redirect"], "/settings")

        settings_page = self.client.get("/settings")
        self.assertEqual(settings_page.status_code, 200)
        self.assertIn(b'id="timeSky"', settings_page.data)
        self.assertIn(b'id="changePasswordForm"', settings_page.data)
        self.assertIn(b'class="app-page page-settings"', settings_page.data)
        self.assertIn(b'id="sidebarToggle"', settings_page.data)
        self.assertIn(b'class="sidebar-account"', settings_page.data)

        for path in ("/dashboard", "/persons", "/inside", "/records", "/analytics"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'class="app-page page-', response.data)
            self.assertIn(b'class="sidebar"', response.data)

        change = self.client.post(
            "/api/password/change",
            json={
                "current_password": initial_password,
                "new_password": "Changed-Password-1",
                "confirm_password": "Changed-Password-1",
            },
        )
        self.assertEqual(change.status_code, 200)
        self.client.get("/logout")

        reset = self.client.post(
            "/api/password/forgot",
            json={
                "username": "new.member",
                "initial_password": initial_password,
                "new_password": "Recovered-Password-2",
                "confirm_password": "Recovered-Password-2",
            },
        )
        self.assertEqual(reset.status_code, 200)

        final_login = self.client.post(
            "/api/login",
            json={"username": "new.member", "password": "Recovered-Password-2"},
        )
        self.assertEqual(final_login.status_code, 200)
        self.assertFalse(final_login.get_json()["data"]["must_change_password"])

    def test_legacy_account_and_auth_pages_remain_available(self) -> None:
        self.assertTrue(AccountService().authenticate("dhl", "541610"))
        for path in ("/login", "/register", "/forgot-password"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'id="timeSky"', response.data)

        login_page = self.client.get("/login")
        self.assertIn("进入系统".encode("utf-8"), login_page.data)
        self.assertIn("进入场馆".encode("utf-8"), login_page.data)
        self.assertIn("离开场馆".encode("utf-8"), login_page.data)
        self.assertIn(b'href="/face-checkin/enter"', login_page.data)
        self.assertIn(b'href="/face-checkin/leave"', login_page.data)

        for mode in ("enter", "leave"):
            face_page = self.client.get(f"/face-checkin/{mode}")
            self.assertEqual(face_page.status_code, 200)
            self.assertIn(b'id="loginCameraFeed"', face_page.data)
            self.assertIn(b'id="faceLoginButton"', face_page.data)
            self.assertIn(f'initFaceCheckinPage("{mode}")'.encode(), face_page.data)

    def test_public_face_checkin_records_attendance_without_login(self) -> None:
        recognition = {
            "recognized": True,
            "person_id": "P001",
            "confidence": 26.5,
            "face_count": 1,
        }
        record = GymCheckinRecord(
            sequence=1,
            person_id="P001",
            person_name="测试人员",
            enter_time="2026-09-03 08:00:00",
        )
        record_service = Mock()
        record_service.find_open_record.return_value = None
        attendance_service = Mock()
        attendance_service.person_enter.return_value = record
        with (
            patch("app.camera_stream.raw_frame", return_value=object()),
            patch("app.RecognizeService") as recognize_service,
            patch("app.PersonService") as person_service,
            patch(
                "app.make_services",
                return_value=(record_service, attendance_service, Mock()),
            ),
        ):
            recognize_service.return_value.best_recognition.return_value = recognition
            person_service.return_value.find_person.return_value = {
                "person_id": "P001",
                "name": "测试人员",
            }
            response = self.client.post("/api/public/face-checkin", json={"mode": "enter"})

        self.assertEqual(response.status_code, 200)
        result = response.get_json()["data"]
        self.assertEqual(result["action"], "enter")
        self.assertEqual(result["person_name"], "测试人员")
        attendance_service.person_enter.assert_called_once_with("P001", "测试人员")
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 302)
        self.assertIn("/login", dashboard.headers["Location"])

    def test_public_face_checkout_records_leave_time(self) -> None:
        recognition = {
            "recognized": True,
            "person_id": "P001",
            "confidence": 25.0,
            "face_count": 1,
        }
        record = GymCheckinRecord(
            sequence=1,
            person_id="P001",
            person_name="测试人员",
            enter_time="2026-09-03 08:00:00",
            leave_time="2026-09-03 10:00:00",
            duration_seconds=7200,
        )
        attendance_service = Mock()
        attendance_service.person_leave.return_value = record
        with (
            patch("app.camera_stream.raw_frame", return_value=object()),
            patch("app.RecognizeService") as recognize_service,
            patch("app.PersonService") as person_service,
            patch(
                "app.make_services",
                return_value=(Mock(), attendance_service, Mock()),
            ),
        ):
            recognize_service.return_value.best_recognition.return_value = recognition
            person_service.return_value.find_person.return_value = {
                "person_id": "P001",
                "name": "测试人员",
            }
            response = self.client.post("/api/public/face-checkin", json={"mode": "leave"})

        self.assertEqual(response.status_code, 200)
        result = response.get_json()["data"]
        self.assertEqual(result["action"], "leave")
        self.assertEqual(result["record"]["leave_time"], "2026-09-03 10:00:00")
        self.assertEqual(result["record"]["duration_text"], "2小时0分钟0秒")
        attendance_service.person_leave.assert_called_once_with("P001")


if __name__ == "__main__":
    unittest.main()
