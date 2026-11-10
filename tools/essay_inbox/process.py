"""받은편지함의 독후감을 열어 첨삭 수업을 만들고 보관함에 넣는다 (GitHub Actions 에서 돈다).

    python tools/essay_inbox/process.py --pub   공개 열쇠 파일(inbox_pub.txt)을 Gemini 키에 맞게 쓴다
    python tools/essay_inbox/process.py         tools/essay_inbox/*.bin 을 모두 처리한다

처리한 것: streamlit_app/essay_store/<번호>.lesson/.meta 를 만들고 받은편지함 파일을 지운다.
만든 수업 번호는 tools/essay_inbox/.made 에 한 줄씩 적는다 (워크플로가 main 에 올릴 때 쓴다).
"""
from __future__ import annotations

import base64
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "streamlit_app"))

import essay_coach  # noqa: E402
import essay_store  # noqa: E402

SITE = "https://unjungsam-study.streamlit.app/learning_korean_essay"


def write_pub() -> None:
    pub = essay_store.inbox_public_b64()
    old = essay_store.INBOX_PUB.read_text().strip() if essay_store.INBOX_PUB.exists() else ""
    if old != pub:
        essay_store.INBOX_PUB.write_text(pub + "\n")
        print("공개 열쇠를 새로 썼어요.")
    else:
        print("공개 열쇠가 이미 맞아요.")


def process(path: Path) -> str | None:
    t0 = time.time()
    try:
        job = json.loads(essay_store.unseal_inbox(path.read_bytes()))
    except Exception as e:  # noqa: BLE001
        print(f"[{path.name}] 열 수 없어요 ({type(e).__name__}). 공개 열쇠가 바뀌었을 수 있어요. 지웁니다.")
        path.unlink()
        return None
    lid = job["id"]
    essay_coach.lesson_dir(lid)  # 번호 검사
    images = [(base64.b64decode(i["data"]), i.get("mime", "image/jpeg")) for i in job.get("images", [])]
    print(f"[{lid}] 사진 {len(images)}장, 첨삭 시작")
    result = None
    for attempt in range(2):
        try:
            result = essay_coach.analyze(images, job.get("typed", ""), job.get("book", ""),
                                         job.get("grade", "초등 5학년"), job.get("name", "로운"))
            break
        except essay_coach.CoachError as e:
            print(f"[{lid}] 첨삭 실패 ({attempt + 1}번째): {e}")
            if attempt == 0:
                time.sleep(20)
    if result is None:
        print(f"::error::[{lid}] 첨삭을 만들지 못했어요. 받은편지함 파일은 남겨 둡니다 (다시 실행하면 이어서).")
        return None
    if not result.get("readable"):
        print(f"[{lid}] 글을 읽지 못했어요: {result.get('problem')}")
        path.unlink()
        print(f"::error::[{lid}] 판독 실패. 더 또렷한 사진으로 다시 보내 주세요.")
        return None
    print(f"[{lid}] 첨삭 완료 ({time.time() - t0:.0f}초): {result.get('book_title')} / {result.get('essay_title')}")
    essay_coach.save_lesson(lid, {
        "lesson": result, "grade": job.get("grade", ""), "name": job.get("name", "로운"),
        "book": job.get("book") or result.get("book_title", ""), "created": job.get("created", ""),
    })
    status = essay_coach.make_voice_now(lid, result)
    eng = status.get("engine", {})
    from collections import Counter
    print(f"[{lid}] 음성 {len(status.get('files', {}))}개, 못 만든 것 {status.get('failed')}")
    for name, n in Counter(eng.values()).most_common():
        print(f"    {name}: {n}개")
    for k, v in eng.items():
        print(f"    {k}: {v}")
    essay_store.save_local(lid)
    shutil.rmtree(essay_coach.lesson_dir(lid), ignore_errors=True)
    path.unlink()
    print(f"[{lid}] 보관 완료 ({time.time() - t0:.0f}초). 주소: {SITE}?c={lid}")
    return lid


def main() -> int:
    if "--pub" in sys.argv:
        write_pub()
        return 0
    made, failed = [], 0
    for path in sorted(essay_store.INBOX_DIR.glob("*.bin")):
        lid = process(path)
        if lid:
            made.append(lid)
        else:
            failed += 1
    (essay_store.INBOX_DIR / ".made").write_text("".join(f"{x}\n" for x in made))
    print(f"만든 수업 {len(made)}개, 실패 {failed}개")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
