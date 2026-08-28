"""GitHub 저장소 DB 동기화 모듈.

Streamlit Cloud에서 대시보드가 감시 조건을 변경하면,
원격 저장소의 data/flights.db 를 받아 편집한 뒤 커밋하는 역할을 한다.
이렇게 해야 GitHub Actions 크론이 항상 최신 조건으로 감시할 수 있다.
"""
from __future__ import annotations

import base64
import logging
from typing import NamedTuple

from app import config

logger = logging.getLogger(__name__)

DB_REMOTE_PATH = "data/flights.db"


def ready() -> bool:
    return config.github_sync_ready()


def _repo():
    from github import Auth, Github

    client = Github(auth=Auth.Token(config.GITHUB_TOKEN), per_page=10)
    return client.get_repo(config.GITHUB_REPO)


class RemoteChanged(RuntimeError):
    """커밋하려는 사이에 원격 DB가 다른 주체(다른 사용자·Actions 크론)에 의해 바뀌었다."""


class RemoteDB(NamedTuple):
    """원격 파일 내용과 그 시점의 blob SHA."""

    data: bytes | None
    sha: str | None


def fetch_remote_db() -> RemoteDB:
    """원격 flights.db 내용과 blob SHA를 함께 가져온다.

    SHA는 낙관적 동시성 제어(optimistic locking)에 쓴다. 이 SHA를 그대로
    update_file에 넘기면, 그 사이 다른 커밋이 있었을 때 GitHub이 409로 거절한다.
    """
    if not ready():
        return RemoteDB(None, None)
    try:
        contents = _repo().get_contents(DB_REMOTE_PATH, ref=config.GITHUB_BRANCH)
        return RemoteDB(base64.b64decode(contents.content), contents.sha)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "404" in msg or "Not Found" in msg:
            logger.info("원격 DB가 아직 없습니다 (첫 커밋 시 생성됩니다).")
        else:
            logger.warning("원격 DB 조회 실패: %s", exc)
        return RemoteDB(None, None)


def commit_db_bytes(data: bytes, message: str, expected_sha: str | None = None) -> bool:
    """flights.db 를 원격 저장소에 커밋. 성공 시 True.

    expected_sha를 주면 그 SHA일 때만 덮어쓴다. 원격이 그 사이 바뀌었으면
    RemoteChanged를 올려 호출자가 최신본 위에서 다시 시도하도록 한다.
    (예전에는 커밋 직전에 SHA를 새로 읽어 항상 성공시켜, 동시 수정이 조용히
     유실되는 last-write-wins 구조였다.)
    """
    if not ready():
        return False
    repo = _repo()

    sha = expected_sha
    if sha is None:
        # 호출자가 기준 SHA를 모르면 지금 값을 읽어 쓴다 (기존 동작)
        try:
            sha = repo.get_contents(DB_REMOTE_PATH, ref=config.GITHUB_BRANCH).sha
        except Exception as exc:  # noqa: BLE001 - 404면 신규 생성
            if "404" in str(exc) or "Not Found" in str(exc):
                repo.create_file(DB_REMOTE_PATH, message, data, branch=config.GITHUB_BRANCH)
                logger.info("GitHub 신규 생성 완료: %s", message)
                return True
            raise

    try:
        repo.update_file(DB_REMOTE_PATH, message, data, sha, branch=config.GITHUB_BRANCH)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "409" in msg or "does not match" in msg or "is at" in msg:
            raise RemoteChanged(msg) from exc
        if "404" in msg or "Not Found" in msg:
            repo.create_file(DB_REMOTE_PATH, message, data, branch=config.GITHUB_BRANCH)
            logger.info("GitHub 신규 생성 완료: %s", message)
            return True
        raise
    logger.info("GitHub 커밋 완료: %s", message)
    return True
