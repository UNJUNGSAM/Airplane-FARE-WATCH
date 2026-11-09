"""독서논술 첨삭 교실 실제 시험 (GitHub Actions 에서 GEMINI_API_KEY 로 돈다). 결과는 out/ 에 저장."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "streamlit_app"))
import essay_coach as ec  # noqa: E402

out = Path(__file__).resolve().parent / "out"
out.mkdir(exist_ok=True)
log = []
key = ec.api_key()
print("key:", bool(key))
text_models, tts_models = ec._models(key)
print("text models:", text_models[:6])
print("tts models:", tts_models[:4])
img = (Path(__file__).parent / "sample.jpg").read_bytes()
img, mime = ec.prepare_image(img, "image/jpeg")
t = time.time()
res = ec.analyze([(img, mime)], "", "", "초등 5학년", "로운", on_try=lambda m: print("try", m))
print("analyze seconds:", round(time.time() - t, 1))
(out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
# 음성: 첫 장은 Gemini Kore, 하나는 Supertonic
lid = ec.new_id()
items = ec.voice_items(res)
print("voice items:", [k for k, _ in items])
t = time.time()
pcm = ec._trim_pcm(ec._gemini_tts(key, tts_models, items[0][1]))
p = ec._pcm_to_file(pcm, out / "intro_kore.mp3")
print("kore seconds:", round(time.time() - t, 1), p.name, p.stat().st_size)
t = time.time()
pcm = ec._supertonic_pcm(items[1][1])
p = ec._pcm_to_file(pcm, out / "read_supertonic.mp3")
print("supertonic seconds:", round(time.time() - t, 1), p.name, p.stat().st_size)
