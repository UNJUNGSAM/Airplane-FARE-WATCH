"""GitHub 저장소 DB 동기화 모듈.

Streamlit Cloud에서 대시보드가 감시 조건을 변경하면,
원격 저장소의 data/flights.db 를 받아 편집한 뒤 커밋하는 역할을 한다.
이렇게 해야 GitHub Actions 크론이 항상 최신 조건으로 감시할 수 있다.
"""
from __future__ import annotations

import base64
import logging

from app import config

logger = logging.getLogger(__name__)

DB_REMOTE_PATH = "data/flights.db"


def ready() -> bool:
    return config.github_sync_ready()


def _repo():
    from github import Auth, Github

    client = Github(auth=Auth.Token(config.GITHUB_TOKEN), per_page=10)
    return client.get_repo(config.GITHUB_REPO)


def fetch_remote_db_bytes() -> bytes | None:
    """원격 저장소의 최신 flights.db 내용. 파일이 없으면 None."""
    if not ready():
        return None
    try:
        contents = _repo().get_contents(DB_REMOTE_PATH, ref=config.GITHUB_BRANCH)
        return base64.b64decode(contents.content)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "404" in msg or "Not Found" in msg:
            logger.info("원격 DB가 아직 없습니다 (첫 커밋 시 생성됩니다).")
        else:
            logger.warning("원격 DB 조회 실패: %s", exc)
        return None


def commit_db_bytes(data: bytes, message: str) -> bool:
    """flights.db 를 원격 저장소에 커밋. 성공 시 True."""
    if not ready():
        return False
    repo = _repo()
    try:
        contents = repo.get_contents(DB_REMOTE_PATH, ref=config.GITHUB_BRANCH)
        repo.update_file(
            DB_REMOTE_PATH, message, data, contents.sha, branch=config.GITHUB_BRANCH
        )
    except Exception as exc:  # noqa: BLE001 - 404면 신규 생성
        if "404" in str(exc) or "Not Found" in str(exc):
            repo.create_file(DB_REMOTE_PATH, message, data, branch=config.GITHUB_BRANCH)
        else:
            raise
    logger.info("GitHub 커밋 완료: %s", message)
    return True
