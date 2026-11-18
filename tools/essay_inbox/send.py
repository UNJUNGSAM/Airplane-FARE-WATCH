"""독후감 사진을 잠가서 받은편지함에 넣는다 (클로드 스레드에서 쓴다).

사용법 (저장소 맨 위 폴더에서)
    python tools/essay_inbox/send.py 사진1 [사진2 ...] [--book 책제목] [--text 글.txt]

하는 일
    1. 사진을 바로 세우고 줄인 뒤, 이름 '로운'·학년 '초등 5학년'과 함께 묶는다.
    2. tools/essay_inbox/inbox_pub.txt 의 공개 열쇠로 잠가 tools/essay_inbox/<수업 번호>.bin 에 쓴다.
       (GitHub Actions 만 열 수 있다. 공개 저장소에 올려도 아무도 사진을 볼 수 없다.)
    3. 수업 번호와 수업 주소를 알려 준다.
그다음 이 파일을 커밋해 claude/... 작업 브랜치에 푸시하면 Actions(essay.yml)가 수업을 만들어
main 의 보관함(streamlit_app/essay_store/)에 넣는다. 약 5분 뒤 아래 주소로 열 수 있다.
커밋 메시지에 [skip ci] 를 넣으면 Actions 가 돌지 않으니 넣지 않는다.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "streamlit_app"))

import essay_coach  # noqa: E402
import essay_store  # noqa: E402

SITE = "https://unjungsam-study.streamlit.app/learning_korean_essay"
KST = timezone(timedelta(hours=9))


def guess_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypmsf1"):
        return "image/heic"
    return "image/jpeg"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", nargs="*")
    ap.add_argument("--book", default="")
    ap.add_argument("--grade", default="초등 5학년")
    ap.add_argument("--text", default="", help="글을 직접 옮겨 적은 텍스트 파일 (선택)")
    a = ap.parse_args()
    if not a.photos and not a.text:
        ap.error("사진이나 --text 가 필요해요.")
    if not essay_store.INBOX_PUB.exists():
        print("공개 열쇠(tools/essay_inbox/inbox_pub.txt)가 없어요. main 을 받아 오세요 (git fetch origin main).")
        return 1
    images = []
    for p in a.photos:
        raw = Path(p).read_bytes()
        data, mime = essay_coach.prepare_image(raw, guess_mime(raw))
        images.append({"mime": mime, "data": base64.b64encode(data).decode()})
    lid = essay_coach.new_id()
    job = {
        "id": lid, "name": "로운", "grade": a.grade, "book": a.book.strip(),
        "typed": Path(a.text).read_text(encoding="utf-8") if a.text else "",
        "created": datetime.now(KST).isoformat(timespec="minutes"), "images": images,
    }
    blob = essay_store.seal_inbox(json.dumps(job, ensure_ascii=False).encode(),
                                  essay_store.INBOX_PUB.read_text().strip())
    out = essay_store.INBOX_DIR / f"{lid}.bin"
    out.write_bytes(blob)
    print(f"수업 번호: {lid}")
    print(f"잠근 파일: {out.relative_to(ROOT)} ({len(blob) // 1024} KB, 사진 {len(images)}장)")
    print(f"수업 주소(약 5분 뒤): {SITE}?c={lid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
