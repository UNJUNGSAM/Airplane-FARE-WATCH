"""설정 로딩 모듈.

우선순위:
1. 환경 변수 (로컬 실행 시 프로젝트 루트의 .env 자동 로드)
2. Streamlit st.secrets (.streamlit/secrets.toml 또는 클라우드 Secrets)

이중 지원으로 로컬(.env)과 Streamlit Cloud(secrets.toml) 양쪽에서 동일하게 동작합니다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # 로컬 실행 시 .env 로드 (설치 안 된 환경에서도 무시하고 진행)
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def get_secret(key: str, default: str | None = None) -> str | None:
    """환경 변수 및 Streamlit Secrets에서 실시간으로 키를 조회한다."""
    # 1. os.environ 조회
    for k in (key, key.upper(), key.lower()):
        val = os.environ.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()

    # 2. Streamlit Secrets 조회
    try:
        import streamlit as st

        # st.secrets 직접 조회 시도
        for k in (key, key.upper(), key.lower()):
            try:
                if k in st.secrets:
                    val = st.secrets[k]
                    if val is not None and str(val).strip():
                        return str(val).strip()
            except Exception:
                pass
            try:
                val = st.secrets.get(k)
                if val is not None and str(val).strip():
                    return str(val).strip()
            except Exception:
                pass

        # st.secrets 전체 키 순회
        try:
            for k in list(st.secrets.keys()):
                if str(k).strip().upper() == key.upper():
                    val = st.secrets[k]
                    if val is not None and str(val).strip():
                        return str(val).strip()
                try:
                    section = st.secrets[k]
                    if hasattr(section, "keys") and callable(section.keys):
                        for sub_k in section.keys():
                            if str(sub_k).strip().upper() == key.upper():
                                val = section[sub_k]
                                if val is not None and str(val).strip():
                                    return str(val).strip()
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass

    return default


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def __getattr__(name: str) -> Any:
    """모듈 변수 접근 시 실시간으로 최신 secrets를 반환합니다."""
    if name == "GEMINI_API_KEY":
        return get_secret("GEMINI_API_KEY")
    if name == "GEMINI_MODEL":
        return get_secret("GEMINI_MODEL", "gemini-2.5-flash")
    if name == "TELEGRAM_BOT_TOKEN":
        return get_secret("TELEGRAM_BOT_TOKEN")
    if name == "TELEGRAM_CHAT_ID":
        return get_secret("TELEGRAM_CHAT_ID")
    if name == "GITHUB_TOKEN":
        return get_secret("GITHUB_TOKEN")
    if name == "GITHUB_REPO":
        return get_secret("GITHUB_REPO")
    if name == "GITHUB_BRANCH":
        return get_secret("GITHUB_BRANCH", "main")
    if name == "DB_PATH":
        return get_secret("DB_PATH", str(PROJECT_ROOT / "data" / "flights.db"))
    if name == "DEFAULT_CURRENCY":
        return get_secret("DEFAULT_CURRENCY", "KRW")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def gemini_ready() -> bool:
    return bool(get_secret("GEMINI_API_KEY"))


def telegram_ready() -> bool:
    return bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))


def github_sync_ready() -> bool:
    return bool(get_secret("GITHUB_TOKEN") and get_secret("GITHUB_REPO"))

