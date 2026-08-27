"""설정 로딩 모듈.

조회 우선순위 (호출할 때마다 실시간 조회):
1. 이번 브라우저 세션에서만 임시 입력한 값 (설정 페이지의 키 입력 폼)
2. 환경 변수 (로컬 실행 시 프로젝트 루트의 .env 자동 로드 · GitHub Actions Secrets)
3. Streamlit st.secrets (.streamlit/secrets.toml 또는 Streamlit Cloud Secrets)

중요: 이 모듈은 **모듈 수준 상수를 만들지 않는다.**
import 시점에 값을 고정하면 Streamlit Cloud처럼 파이썬 프로세스가 오래 살아 있는
환경에서 나중에 등록한 Secrets가 영원히 반영되지 않는다.
(실제로 이 문제로 Secrets를 저장해도 "미설정"으로 표시되는 장애가 있었다.)
모든 값은 `get_secret()` 또는 모듈 `__getattr__`을 통해 매번 새로 읽는다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# 배포된 코드가 실제로 프로세스에 반영되었는지 설정 페이지에서 확인하기 위한 표식.
# app/config.py 를 수정할 때마다 함께 올린다.
CONFIG_REVISION = "2026-08-27.1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 세션 임시 입력값을 담는 st.session_state 키 (위젯 키와 충돌하지 않도록 전용 네임스페이스)
_SESSION_BUCKET = "_config_overrides"

_KEYS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GITHUB_TOKEN",
    "GITHUB_REPO",
    "GITHUB_BRANCH",
    "DB_PATH",
    "DEFAULT_CURRENCY",
)

_DEFAULTS = {
    "GEMINI_MODEL": "gemini-2.5-flash",
    "GITHUB_BRANCH": "main",
    "DEFAULT_CURRENCY": "KRW",
}

try:  # 로컬 실행 시 .env 로드 (설치 안 된 환경에서도 무시하고 진행)
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def _clean(val: Any) -> str | None:
    """빈 값·공백만 있는 값은 None으로 정규화한다."""
    if val is None:
        return None
    text = str(val).strip()
    return text or None


# ---------------------------------------------------------------------------
# 세션 임시 오버라이드 (설정 페이지 입력 폼)
# ---------------------------------------------------------------------------
def _session_bucket(create: bool = False) -> dict[str, str] | None:
    """현재 브라우저 세션 전용 오버라이드 저장소.

    os.environ 은 프로세스 전역이라 공개 배포 앱에서 한 사람이 입력한 키가 다른
    접속자에게까지 노출된다. 반드시 세션 단위로만 보관한다.
    """
    try:
        import streamlit as st

        state = st.session_state
        bucket = state.get(_SESSION_BUCKET)
        if not isinstance(bucket, dict):
            if not create:
                return None
            bucket = {}
            state[_SESSION_BUCKET] = bucket
        return bucket
    except Exception:  # streamlit 미설치 / 스크립트 실행 컨텍스트 밖
        return None


def set_session_override(key: str, value: str | None) -> None:
    """이번 세션에서만 유효한 키 값을 설정한다 (빈 값이면 해제)."""
    bucket = _session_bucket(create=True)
    if bucket is None:
        return
    cleaned = _clean(value)
    if cleaned is None:
        bucket.pop(key.upper(), None)
    else:
        bucket[key.upper()] = cleaned


def clear_session_overrides() -> None:
    bucket = _session_bucket()
    if bucket is not None:
        bucket.clear()


def has_session_override(key: str) -> bool:
    bucket = _session_bucket()
    return bool(bucket and key.upper() in bucket)


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------
def _from_env(key: str) -> str | None:
    for k in (key, key.upper(), key.lower()):
        val = _clean(os.environ.get(k))
        if val:
            return val
    return None


def _from_secrets(key: str) -> str | None:
    """st.secrets에서 대소문자 무시 + 1단계 섹션까지 탐색한다."""
    try:
        import streamlit as st

        secrets = st.secrets  # secrets.toml 부재 시 접근 자체가 예외
    except Exception:
        return None

    target = key.upper()
    try:
        for k in (key, key.upper(), key.lower()):
            try:
                if k in secrets:
                    val = _clean(secrets[k])
                    if val:
                        return val
            except Exception:
                pass

        for k in list(secrets.keys()):
            try:
                val = secrets[k]
            except Exception:
                continue
            if str(k).strip().upper() == target:
                cleaned = _clean(val)
                if cleaned:
                    return cleaned
                continue
            # [section] 형태로 감싸 넣은 경우까지 한 단계 더 탐색
            if hasattr(val, "keys"):
                try:
                    for sub_k in list(val.keys()):
                        if str(sub_k).strip().upper() == target:
                            cleaned = _clean(val[sub_k])
                            if cleaned:
                                return cleaned
                except Exception:
                    pass
    except Exception:
        return None
    return None


def get_secret(key: str, default: str | None = None) -> str | None:
    """세션 오버라이드 → 환경 변수 → st.secrets 순으로 실시간 조회한다."""
    bucket = _session_bucket()
    if bucket:
        val = _clean(bucket.get(key.upper()))
        if val:
            return val

    val = _from_env(key)
    if val:
        return val

    val = _from_secrets(key)
    if val:
        return val

    return default


def secret_source(key: str) -> str:
    """진단용 - 해당 키가 어디에서 왔는지 반환한다."""
    bucket = _session_bucket()
    if bucket and _clean(bucket.get(key.upper())):
        return "세션 입력"
    # Streamlit은 최상위 secrets를 os.environ에도 복사하므로 secrets를 먼저 확인해야
    # 출처 표시가 정확하다.
    if _from_secrets(key):
        return "Streamlit Secrets"
    if _from_env(key):
        return "환경 변수(.env)"
    return "없음"


def __getattr__(name: str) -> Any:
    """config.GEMINI_API_KEY 처럼 접근해도 매번 최신 값을 반환한다."""
    if name in _KEYS:
        if name == "DB_PATH":
            return get_secret("DB_PATH", str(PROJECT_ROOT / "data" / "flights.db"))
        return get_secret(name, _DEFAULTS.get(name))
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def gemini_ready() -> bool:
    return bool(get_secret("GEMINI_API_KEY"))


def telegram_ready() -> bool:
    return bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))


def github_sync_ready() -> bool:
    return bool(get_secret("GITHUB_TOKEN") and get_secret("GITHUB_REPO"))


def runtime_info() -> dict[str, str]:
    """설정 페이지 진단용 - 지금 실행 중인 config 모듈의 실체."""
    return {
        "revision": CONFIG_REVISION,
        "file": str(Path(__file__).resolve()),
        "cwd": os.getcwd(),
    }
