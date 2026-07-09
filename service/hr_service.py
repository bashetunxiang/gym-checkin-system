from __future__ import annotations

from typing import Dict

from util.io_tools import load_user_passwords


class AccountService:
    """系统账号认证服务，不再承载员工考勤逻辑。"""

    def __init__(self) -> None:
        self.passwords: Dict[str, str] = load_user_passwords()

    def authenticate(self, username: str, password: str) -> bool:
        return self.passwords.get(username) == password


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
