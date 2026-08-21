"""One-time login helper: open RunningHub in a browser, wait for manual login,
then persist the Rh-Accesstoken from localStorage into .rh_token.

Usage:
    python rh_login.py            # headed browser, you log in, script saves token
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(__file__).with_name(".rh_profile")


def main() -> int:
    print("将在浏览器中打开 RunningHub，请手动完成登录（Google/邮箱均可）。")
    print("登录成功回到首页后，脚本会自动抓取 token 并保存。")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1300, "height": 860},
            args=["--lang=en-US"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.runninghub.ai/", wait_until="domcontentloaded", timeout=60000)

        token = ""
        for _ in range(360):  # wait up to ~6 minutes
            time.sleep(1)
            try:
                token = page.evaluate("() => localStorage.getItem('Rh-Accesstoken') || ''")
            except Exception:
                token = ""
            if token:
                break
        if not token:
            print("超时未检测到登录 token。可重新运行本脚本。")
            return 1

        import rh_client
        rh_client.save_token(token)
        expire = page.evaluate("() => localStorage.getItem('Rh-Expire-In') || ''")
        print(f"token 已保存到 {rh_client.TOKEN_FILE}")
        print(f"过期时间戳: {expire or '未知'}（过期后重新运行本脚本登录一次即可）")
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
