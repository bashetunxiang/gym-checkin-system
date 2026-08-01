from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import util.io_tools as io_tools
from app import app
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
        self.assertTrue(initial_password)

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
        self.assertIn(b'class="topbar-actions"', settings_page.data)

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


if __name__ == "__main__":
    unittest.main()
