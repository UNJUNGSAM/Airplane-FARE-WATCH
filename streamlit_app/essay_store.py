"""독서논술 첨삭 수업을 오래 보관하는 곳 (암호화해서 저장소에 둔다).

저장소가 공개라서 아이의 글이 담긴 수업은 반드시 암호화해서 올린다.
암호 열쇠는 따로 만들지 않고 GEMINI_API_KEY 에서 뽑아 쓴다.
(GitHub Actions 비밀값과 학습자료 앱 Secrets 양쪽에 이미 같은 키가 있으므로 새로 넣을 것이 없다.)

보관함    streamlit_app/essay_store/<수업 번호>.meta    목록용 (책 제목, 만든 날 등)
          streamlit_app/essay_store/<수업 번호>.lesson  수업 전체 (lesson.json + 음성 mp3 를 zip 으로 묶은 것)
          둘 다 AES-GCM 으로 잠근다.

받은편지함 tools/essay_inbox/<수업 번호>.bin
          클로드 채팅방에서 받은 독후감 사진을 GitHub Actions 만 열 수 있게 잠가 올리는 곳.
          (X25519 공개 열쇠는 tools/essay_inbox/inbox_pub.txt, 개인 열쇠는 GEMINI_API_KEY 에서 뽑는다)
          Actions(.github/workflows/essay.yml)가 열어서 수업을 만들고 보관함에 넣은 뒤 지운다.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STORE_DIR = HERE / "essay_store"
INBOX_DIR = ROOT / "tools" / "essay_inbox"
INBOX_PUB = INBOX_DIR / "inbox_pub.txt"
DEFAULT_REPO = "unjungsam/airplane-fare-watch"

_MAGIC_STORE = b"ES1"
_MAGIC_INBOX = b"EI1"


class StoreError(Exception):
    pass


# ---------------------------------------------------------------------------
# 열쇠
# ---------------------------------------------------------------------------
def _master() -> str:
    import essay_coach

    key = essay_coach.api_key()
    if not key:
        raise StoreError("GEMINI_API_KEY 가 없어 보관함을 열 수 없어요.")
    return key


def _derive(purpose: str, master: str | None = None) -> bytes:
    return hashlib.sha256(f"rowoon-essay:{purpose}:{master or _master()}".encode()).digest()


def available() -> bool:
    try:
        _master()
        return True
    except StoreError:
        return False


# ---------------------------------------------------------------------------
# 보관함 잠금 (대칭)
# ---------------------------------------------------------------------------
def seal(data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return _MAGIC_STORE + nonce + AESGCM(_derive("store")).encrypt(nonce, data, _MAGIC_STORE)


def unseal(blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(_MAGIC_STORE):
        raise StoreError("보관 파일 형식이 아니에요.")
    nonce, ct = blob[3:15], blob[15:]
    return AESGCM(_derive("store")).decrypt(nonce, ct, _MAGIC_STORE)


# ---------------------------------------------------------------------------
# 받은편지함 잠금 (공개 열쇠: 보내는 쪽은 Gemini 키가 없어도 잠글 수 있다)
# ---------------------------------------------------------------------------
def inbox_private(master: str | None = None):
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    return X25519PrivateKey.from_private_bytes(_derive("inbox", master))


def _raw_pub(pub) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def inbox_public_b64(master: str | None = None) -> str:
    return base64.b64encode(_raw_pub(inbox_private(master).public_key())).decode()


def _inbox_key(shared: bytes, eph: bytes, pub: bytes) -> bytes:
    return hashlib.sha256(b"rowoon-essay-inbox" + shared + eph + pub).digest()


def seal_inbox(data: bytes, pub_b64: str) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    pub = base64.b64decode(pub_b64.strip())
    eph = X25519PrivateKey.generate()
    eph_pub = _raw_pub(eph.public_key())
    key = _inbox_key(eph.exchange(X25519PublicKey.from_public_bytes(pub)), eph_pub, pub)
    nonce = os.urandom(12)
    return _MAGIC_INBOX + eph_pub + nonce + AESGCM(key).encrypt(nonce, data, _MAGIC_INBOX)


def unseal_inbox(blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(_MAGIC_INBOX):
        raise StoreError("받은편지함 파일 형식이 아니에요.")
    eph_pub, nonce, ct = blob[3:35], blob[35:47], blob[47:]
    priv = inbox_private()
    pub = _raw_pub(priv.public_key())
    key = _inbox_key(priv.exchange(X25519PublicKey.from_public_bytes(eph_pub)), eph_pub, pub)
    return AESGCM(key).decrypt(nonce, ct, _MAGIC_INBOX)


# ---------------------------------------------------------------------------
# 수업 묶기·풀기
# ---------------------------------------------------------------------------
def meta_of(saved: dict) -> dict:
    les = saved.get("lesson", {})
    return {
        "book": saved.get("book") or les.get("book_title", ""),
        "author": les.get("book_author", ""),
        "title": les.get("essay_title", ""),
        "focus": (les.get("diagnosis") or {}).get("focus", ""),
        "name": saved.get("name", ""),
        "grade": saved.get("grade", ""),
        "created": saved.get("created", ""),
    }


def pack(lid: str) -> tuple[bytes, bytes]:
    """임시 수업 폴더(static/essay_voice/<번호>)를 잠근 (meta, lesson) 두 덩어리로 만든다."""
    import essay_coach

    d = essay_coach.lesson_dir(lid)
    saved = json.loads((d / "lesson.json").read_text(encoding="utf-8"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix in (".json", ".mp3", ".wav"):
                z.write(f, f.name)
    return seal(json.dumps(meta_of(saved), ensure_ascii=False).encode()), seal(buf.getvalue())


def save_local(lid: str) -> None:
    """보관함 폴더에 바로 쓴다 (GitHub Actions 처럼 저장소 안에서 돌 때)."""
    import essay_coach

    essay_coach.lesson_dir(lid)  # 번호 검사
    meta, lesson = pack(lid)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    (STORE_DIR / f"{lid}.lesson").write_bytes(lesson)
    (STORE_DIR / f"{lid}.meta").write_bytes(meta)


def has(lid: str) -> bool:
    return (STORE_DIR / f"{lid}.lesson").exists()


def restore(lid: str) -> bool:
    """보관함에 있는 수업을 임시 수업 폴더로 풀어 놓는다. 이미 풀려 있으면 그대로."""
    import essay_coach

    d = essay_coach.lesson_dir(lid)
    if (d / "lesson.json").exists():
        return True
    src = STORE_DIR / f"{lid}.lesson"
    if not src.exists():
        return False
    try:
        raw = unseal(src.read_bytes())
    except Exception:
        return False
    d.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if "/" not in n and "\\" not in n and not n.startswith(".")]
        # lesson.json 을 맨 나중에 써야, 반쯤 풀린 수업을 다른 화면이 열지 않는다
        for name in sorted(names, key=lambda n: n == "lesson.json"):
            essay_coach._write_atomic(d / name, z.read(name))
    return (d / "lesson.json").exists()


_LIST_CACHE: dict[str, Any] = {}


def list_saved() -> list[dict]:
    """보관된 수업 목록 (최근 것부터). [{id, book, title, created, ...}]"""
    if not STORE_DIR.exists() or not available():
        return []
    out = []
    for f in STORE_DIR.glob("*.meta"):
        lid = f.stem
        stamp = f.stat().st_mtime
        hit = _LIST_CACHE.get(lid)
        if not hit or hit[0] != stamp:
            try:
                meta = json.loads(unseal(f.read_bytes()))
            except Exception:
                continue
            hit = (stamp, meta)
            _LIST_CACHE[lid] = hit
        out.append({"id": lid, **hit[1]})
    out.sort(key=lambda m: m.get("created", ""), reverse=True)
    return out


# ---------------------------------------------------------------------------
# 웹에서 만든 수업을 저장소에 올리기 (GITHUB_TOKEN 이 Secrets 에 있을 때만)
# ---------------------------------------------------------------------------
def _gh_settings() -> tuple[str, str]:
    import study_page

    token = study_page._secret("GITHUB_TOKEN")
    repo = study_page._secret("GITHUB_REPO") or DEFAULT_REPO
    return token, repo


def can_upload() -> bool:
    try:
        return bool(_gh_settings()[0]) and available()
    except Exception:
        return False


def _gh_put(token: str, repo: str, path: str, data: bytes, message: str) -> None:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    head = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "User-Agent": "rowoon-study"}
    body = {"message": message, "content": base64.b64encode(data).decode(), "branch": "main"}
    try:  # 같은 이름이 이미 있으면 덮어쓴다
        req = urllib.request.Request(f"{url}?ref=main", headers=head)
        with urllib.request.urlopen(req, timeout=30) as r:
            body["sha"] = json.loads(r.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=head, method="PUT")
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()


def upload(lid: str) -> None:
    """수업을 잠가 저장소 main 의 보관함에 올린다. 실패하면 예외."""
    token, repo = _gh_settings()
    if not token:
        raise StoreError("GITHUB_TOKEN 이 없어요.")
    meta, lesson = pack(lid)
    # 수업 파일을 먼저, 목록 파일을 나중에 올려야 목록에 뜬 수업이 늘 열린다.
    for attempt in range(3):
        try:
            _gh_put(token, repo, f"streamlit_app/essay_store/{lid}.lesson", lesson,
                    f"chore: 독서논술 수업 보관 {lid[:6]} [skip ci]")
            _gh_put(token, repo, f"streamlit_app/essay_store/{lid}.meta", meta,
                    f"chore: 독서논술 수업 목록 {lid[:6]} [skip ci]")
            break
        except urllib.error.HTTPError as e:
            if e.code in (409, 422, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    # 이 서버의 보관함에도 바로 넣어 둔다 (재배포 전에도 목록에 보이게)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    (STORE_DIR / f"{lid}.lesson").write_bytes(lesson)
    (STORE_DIR / f"{lid}.meta").write_bytes(meta)
