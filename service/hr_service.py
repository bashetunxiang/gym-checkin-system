from __future__ import annotations

import re
import threading
from datetime import datetime
from typing import Any, Dict

from werkzeug.security import check_password_hash, generate_password_hash

from util.io_tools import load_account_data, save_account_data


ACCOUNT_LOCK = threading.RLock()
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
DEFAULT_INITIAL_PASSWORD = "88888888"


class AccountService:
    """Account registration, authentication and password recovery service."""

    def __init__(self) -> None:
        with ACCOUNT_LOCK:
            self.store = self._load_and_migrate()

    def _load_and_migrate(self) -> Dict[str, Any]:
        store = load_account_data()
        accounts = store.get("accounts", {})
        if not isinstance(accounts, dict):
            accounts = {}

        migrated: Dict[str, Dict[str, Any]] = {}
        changed = store.get("version") != 2
        for raw_username, raw_account in accounts.items():
            username = str(raw_username).strip()
            if not username:
                changed = True
                continue
            if isinstance(raw_account, str):
                migrated[username] = self._new_record(raw_account, must_change=False)
                changed = True
            elif isinstance(raw_account, dict) and raw_account.get("password_hash"):
                migrated[username] = dict(raw_account)
            else:
                changed = True

        normalized = {"version": 2, "accounts": migrated}
        if changed:
            save_account_data(normalized)
        return normalized

    @staticmethod
    def _new_record(password: str, must_change: bool) -> Dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        password_hash = generate_password_hash(password)
        return {
            "password_hash": password_hash,
            "initial_password_hash": password_hash,
            "must_change_password": must_change,
            "created_at": now,
            "password_changed_at": None,
        }

    @staticmethod
    def validate_username(username: str) -> str:
        username = username.strip()
        if not USERNAME_PATTERN.fullmatch(username):
            raise ValueError("账号须为 3–32 位，只能包含字母、数字、点、短横线或下划线。")
        return username

    @staticmethod
    def validate_new_password(password: str) -> str:
        if len(password) < 8:
            raise ValueError("新密码至少需要 8 位。")
        if len(password) > 128:
            raise ValueError("新密码不能超过 128 位。")
        return password

    @staticmethod
    def _generate_initial_password() -> str:
        return DEFAULT_INITIAL_PASSWORD

    def _reload(self) -> None:
        self.store = self._load_and_migrate()

    def _save(self) -> None:
        save_account_data(self.store)

    def authenticate(self, username: str, password: str) -> bool:
        with ACCOUNT_LOCK:
            self._reload()
            account = self.store["accounts"].get(username)
            return bool(
                isinstance(account, dict)
                and check_password_hash(str(account.get("password_hash", "")), password)
            )

    def needs_password_change(self, username: str) -> bool:
        with ACCOUNT_LOCK:
            self._reload()
            account = self.store["accounts"].get(username, {})
            return bool(account.get("must_change_password")) if isinstance(account, dict) else False

    def register(self, username: str) -> str:
        username = self.validate_username(username)
        with ACCOUNT_LOCK:
            self._reload()
            if username.casefold() in {name.casefold() for name in self.store["accounts"]}:
                raise ValueError("该账号已有人注册，请更换账号。")
            initial_password = self._generate_initial_password()
            self.store["accounts"][username] = self._new_record(initial_password, must_change=True)
            self._save()
            return initial_password

    def change_password(self, username: str, current_password: str, new_password: str) -> None:
        new_password = self.validate_new_password(new_password)
        with ACCOUNT_LOCK:
            self._reload()
            account = self.store["accounts"].get(username)
            if not isinstance(account, dict):
                raise ValueError("账号不存在。")
            if not check_password_hash(str(account.get("password_hash", "")), current_password):
                raise ValueError("当前密码错误。")
            if check_password_hash(str(account.get("password_hash", "")), new_password):
                raise ValueError("新密码不能与当前密码相同。")
            account["password_hash"] = generate_password_hash(new_password)
            account["must_change_password"] = False
            account["password_changed_at"] = datetime.now().isoformat(timespec="seconds")
            self._save()

    def reset_password(self, username: str, initial_password: str, new_password: str) -> None:
        new_password = self.validate_new_password(new_password)
        with ACCOUNT_LOCK:
            self._reload()
            account = self.store["accounts"].get(username)
            if not isinstance(account, dict):
                raise ValueError("账号或初始密码错误。")
            initial_hash = str(account.get("initial_password_hash", ""))
            if not initial_hash or not check_password_hash(initial_hash, initial_password):
                raise ValueError("账号或初始密码错误。")
            if check_password_hash(str(account.get("password_hash", "")), new_password):
                raise ValueError("新密码不能与当前密码相同。")
            account["password_hash"] = generate_password_hash(new_password)
            account["must_change_password"] = False
            account["password_changed_at"] = datetime.now().isoformat(timespec="seconds")
            self._save()


def login(max_attempts: int = 3) -> bool:
    account_service = AccountService()
    for attempt in range(1, max_attempts + 1):
        username = input("账号: ").strip()
        password = input("密码: ").strip()
        if account_service.authenticate(username, password):
            print("登录成功。")
            return True
        remaining = max_attempts - attempt
        if remaining:
            print(f"账号或密码错误，还可尝试 {remaining} 次。")
    print("登录失败。")
    return False
