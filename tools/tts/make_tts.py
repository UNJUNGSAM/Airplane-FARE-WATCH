"""학습자료 해설 음성을 Gemini TTS로 만든다.

tools/tts/jobs/*.json 작업 파일을 읽어, 아직 없는 mp3만 새로 만든다.
(무료 키는 하루 횟수 제한이 있어서, 이미 만든 파일은 건너뛰고 다음에 이어서 만든다.)

작업 파일 형식:
{
  "out_dir": "streamlit_app/static/learning/science_xxx/audio",
  "voice": "Kore",                    # 기본 목소리 (사용자 선택) (항목마다 "voice"로 바꿀 수 있음)
  "style": "다정한 선생님처럼 읽어 주세요:",  # 읽는 말투 지시 (선택)
  "items": [{"key": "n_cover", "text": "안녕하세요!"}]
}

사용법: GEMINI_API_KEY=... python tools/tts/make_tts.py [작업 파일 ...]
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"
ROOT = Path(__file__).resolve().parents[2]
JOBS_DIR = Path(__file__).resolve().parent / "jobs"

# 앞에 있을수록 먼저 시도한다. 목록에 없는 TTS 모델이 새로 나오면 맨 뒤에서 시도한다.
PREFERRED_MODELS = [
    "gemini-3.1-flash-tts-preview",
    "gemini-3.1-flash-preview-tts",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]


class QuotaExceeded(Exception):
    pass


def _request(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def find_models(key: str) -> list[str]:
    try:
        listed = _request(f"{API}/models?pageSize=1000&key={key}").get("models", [])
        available = [m["name"].split("/", 1)[1] for m in listed if "tts" in m["name"]]
    except urllib.error.URLError as e:
        print(f"모델 목록을 못 읽었어요 ({e}). 기본 목록으로 시도합니다.")
        return PREFERRED_MODELS
    ordered = [m for m in PREFERRED_MODELS if m in available]
    ordered += sorted((m for m in available if m not in ordered), reverse=True)
    print("쓸 수 있는 TTS 모델:", ", ".join(ordered) or "(없음)")
    return ordered


def synthesize(key: str, models: list[str], text: str, voice: str) -> tuple[bytes, str]:
    """PCM(16bit, 24kHz, 모노)과 사용한 모델 이름을 돌려준다."""
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    quota_hit = False
    for model in models:
        for attempt in range(3):
            try:
                res = _request(f"{API}/models/{model}:generateContent?key={key}", body)
                part = res["candidates"][0]["content"]["parts"][0]
                return base64.b64decode(part["inlineData"]["data"]), model
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                if e.code == 429:
                    quota_hit = True
                    print(f"  {model}: 사용 한도 도달 -> 다른 모델 시도")
                    break
                if e.code in (500, 503) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                print(f"  {model}: 오류 {e.code} {detail}")
                break
            except (KeyError, IndexError) as e:
                print(f"  {model}: 음성이 비어 있음 ({e})")
                break
    if quota_hit:
        raise QuotaExceeded
    raise RuntimeError("모든 모델에서 음성을 만들지 못했어요")


def ffmpeg_exe() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def pcm_to_mp3(pcm: bytes, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".pcm") as tmp:
        tmp.write(pcm)
        tmp.flush()
        subprocess.run(
            [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1",
             "-i", tmp.name, "-af", "silenceremove=start_periods=1:start_threshold=-50dB,"
             "areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
             "adelay=150", "-b:a", "96k", str(dest)],
            check=True,
        )


def run_job(path: Path, key: str, models: list[str]) -> bool:
    job = json.loads(path.read_text(encoding="utf-8"))
    out_dir = ROOT / job["out_dir"]
    style = job.get("style", "").strip()
    made = skipped = 0
    for item in job["items"]:
        dest = out_dir / f"{item['key']}.mp3"
        if dest.exists():
            skipped += 1
            continue
        text = f"{style}\n{item['text']}" if style else item["text"]
        voice = item.get("voice", job.get("voice", "Kore"))
        try:
            pcm, model = synthesize(key, models, text, voice)
        except QuotaExceeded:
            print(f"[{path.name}] 오늘 한도에 걸려 멈춰요. 만든 것 {made}개, 남은 것은 다음 실행에서 이어서 만들어요.")
            return False
        pcm_to_mp3(pcm, dest)
        made += 1
        print(f"  만듦: {dest.relative_to(ROOT)} ({voice}, {model})")
        time.sleep(7)  # 무료 키의 분당 요청 제한을 넘지 않도록
    print(f"[{path.name}] 새로 만든 것 {made}개, 이미 있던 것 {skipped}개")
    return True


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY가 없어요.")
        return 1
    if not ffmpeg_exe():
        print("ffmpeg가 필요해요. (pip install imageio-ffmpeg)")
        return 1
    jobs = [Path(p) for p in sys.argv[1:]] or sorted(JOBS_DIR.glob("*.json"))
    models = find_models(key)
    for job in jobs:
        if not run_job(job, key, models):
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
