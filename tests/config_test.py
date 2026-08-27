"""설정 조회 회귀 테스트.

배경: Streamlit Cloud Secrets에 키를 넣어도 계속 "미설정"으로 뜨던 장애가 있었다.
원인은 config가 값을 **import 시점에 모듈 상수로 고정**한 것이었고, 프로세스가
오래 사는 배포 환경에서는 나중에 등록한 Secrets가 영원히 반영되지 않았다.
아래 테스트는 "값은 호출 시점에 읽는다"는 계약을 고정한다.

    python tests/config_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402

passed = failed = 0


def check(label: str, cond: bool) -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS - {label}")
    else:
        failed += 1
        print(f"FAIL - {label}")


def with_env(**pairs):
    """환경 변수를 임시로 바꾸는 컨텍스트."""
    class _Ctx:
        def __enter__(self):
            self.old = {k: os.environ.get(k) for k in pairs}
            for k, v in pairs.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        def __exit__(self, *exc):
            for k, v in self.old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return _Ctx()


def main() -> int:
    # --- 값은 호출 시점에 읽는다 (모듈 상수로 굳지 않는다) ---
    with with_env(GEMINI_API_KEY="key-A"):
        first = config.GEMINI_API_KEY
    with with_env(GEMINI_API_KEY="key-B"):
        second = config.GEMINI_API_KEY
    check("환경 변수를 바꾸면 즉시 반영된다 (import 시점 고정 금지)",
          first == "key-A" and second == "key-B")

    with with_env(GEMINI_API_KEY="key-C"):
        check("gemini_ready()도 같은 값을 본다", config.gemini_ready() is True)

    # --- 기본값 ---
    with with_env(GEMINI_MODEL=None):
        check("GEMINI_MODEL 기본값은 gemini-3.6-flash",
              config.GEMINI_MODEL == "gemini-3.6-flash")
    with with_env(GEMINI_MODEL="gemini-2.5-flash"):
        check("GEMINI_MODEL은 설정값이 기본값을 이긴다",
              config.GEMINI_MODEL == "gemini-2.5-flash")
    check("default_for가 기본값을 알려준다",
          config.default_for("GITHUB_BRANCH") == "main")

    # --- 공백/빈 문자열은 미설정으로 본다 ---
    with with_env(TELEGRAM_BOT_TOKEN="   ", TELEGRAM_CHAT_ID="   "):
        check("공백만 있는 값은 미설정으로 취급", config.telegram_ready() is False)

    # --- 대소문자 무시 ---
    with with_env(GEMINI_API_KEY=None, gemini_api_key="lower-key"):
        check("소문자 환경 변수도 인식", config.get_secret("GEMINI_API_KEY") == "lower-key")

    # --- 비밀번호 게이트 ---
    with with_env(APP_PASSWORD=None):
        check("APP_PASSWORD 미설정이면 인증 비활성", config.auth_enabled() is False)
        check("인증 비활성 시 검사는 항상 통과", config.check_password("") is True)
    with with_env(APP_PASSWORD="8144"):
        check("APP_PASSWORD 설정 시 인증 활성", config.auth_enabled() is True)
        check("맞는 비밀번호는 통과", config.check_password("8144") is True)
        check("틀린 비밀번호는 거절", config.check_password("0000") is False)
        check("공백은 잘라내고 비교", config.check_password(" 8144 ") is True)
        check("빈 입력은 거절", config.check_password(None) is False)

    # --- 준비 상태 판정 ---
    with with_env(GITHUB_TOKEN="t", GITHUB_REPO=None):
        check("GITHUB_REPO 없으면 동기화 미준비", config.github_sync_ready() is False)
    with with_env(GITHUB_TOKEN="t", GITHUB_REPO="u/r"):
        check("토큰+저장소 모두 있으면 준비 완료", config.github_sync_ready() is True)

    print()
    if failed:
        print(f"실패 {failed}건 / 전체 {passed + failed}건")
        return 1
    print(f"모든 설정 테스트 통과! ({passed}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
