"""설정 로딩 모듈.

우선순위:
1. 환경 변수 (로컬 실행 시 프로젝트 루트의 .env 자동 로드)
2. Streamlit st.secrets (.streamlit/secrets.toml 또는 클라우드 Secrets)

이중 지원으로 로컬(.env)과 Streamlit Cloud(secrets.toml) 양쪽에서 동일하게 동작합니다.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # 로컬 실행 시 .env 로드 (설치 안 된 환경에서도 무시하고 진행)
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def get_secret(key: str, default: str | None = None) -> str | None:
    """환경 변수를 먼저 조회하고, 없으면 st.secrets에서 조회한다."""
    val = os.environ.get(key)
    if val:
        return val.strip() or None
    try:
        import streamlit as st  # 지연 임포트: 순수 파이썬 실행 시 부담 제거

        try:
            if key in st.secrets:
                return str(st.secrets[key]).strip() or None
        except Exception:  # secrets.toml 부재 등
            pass
    except ImportError:
        pass
    return default


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ----- Gemini -----
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
GEMINI_MODEL = get_secret("GEMINI_MODEL", "gemini-2.5-flash")

# ----- Telegram -----
TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

# ----- GitHub 동기화 (Streamlit 대시보드 -> 저장소 DB 커밋) -----
GITHUB_TOKEN = get_secret("GITHUB_TOKEN")
GITHUB_REPO = get_secret("GITHUB_REPO")  # 예: username/airplane-tracer
GITHUB_BRANCH = get_secret("GITHUB_BRANCH", "main")

# ----- 기타 -----
DB_PATH = get_secret("DB_PATH", str(PROJECT_ROOT / "data" / "flights.db"))
DEFAULT_CURRENCY = get_secret("DEFAULT_CURRENCY", "KRW")


def gemini_ready() -> bool:
    return bool(GEMINI_API_KEY)


def telegram_ready() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def github_sync_ready() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_REPO)
