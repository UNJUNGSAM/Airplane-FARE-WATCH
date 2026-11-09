"""실제 사진으로 첨삭 시험 (Actions). 사진과 결과는 암호화된 채로만 저장소를 오간다.
1) 이 실행이 일회용 키를 만들어 공개 키를 로그에 찍는다.
2) 요청자가 그 키로 사진을 암호화해 img.enc 로 올릴 때까지 기다린다.
3) 첨삭 결과를 requester.pub 로 암호화해 result.enc 로 올린다. 일회용 비밀 키는 실행이 끝나면 사라진다."""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "streamlit_app"))
import box  # noqa: E402
import essay_coach as ec  # noqa: E402

branch = os.environ["BRANCH"]
priv = rsa.generate_private_key(public_exponent=65537, key_size=3072)
pub = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
GIT_ID = ["-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
# 진행 중인 실행의 로그는 바로 읽을 수 없어서, 일회용 공개 키를 브랜치에 올린다 (공개 키라 괜찮다)
(HERE / "runner.pub").write_bytes(pub)
subprocess.run(["git", "add", str(HERE / "runner.pub")], check=True)
subprocess.run(["git", *GIT_ID, "commit", "-qm", "chore: 일회용 공개 키 [skip ci]"], check=True)
subprocess.run(["git", "push", "-q", "origin", f"HEAD:{branch}"], check=True)
blob = None
for _ in range(90):
    time.sleep(10)
    subprocess.run(["git", "fetch", "-q", "origin", branch], check=True)
    r = subprocess.run(["git", "show", f"origin/{branch}:tools/private_test/img.enc"], capture_output=True)
    if r.returncode == 0:
        blob = r.stdout
        break
if not blob:
    sys.exit("사진이 오지 않음")
req = json.loads(box.open_(priv, blob))
img, mime = ec.prepare_image(base64.b64decode(req["image"]), "image/jpeg")
t = time.time()
try:
    res = ec.analyze([(img, mime)], "", req.get("book", ""), req.get("grade", "초등 5학년"), req.get("name", ""))
    out = {"ok": True, "seconds": round(time.time() - t, 1), "result": res}
except Exception as e:
    out = {"ok": False, "seconds": round(time.time() - t, 1), "error": str(e)}
print("seconds", out["seconds"], "ok", out["ok"], flush=True)
sealed = box.seal((HERE / "requester.pub").read_bytes(), json.dumps(out, ensure_ascii=False).encode())
subprocess.run(["git", "fetch", "-q", "origin", branch], check=True)
subprocess.run(["git", "checkout", "-q", f"origin/{branch}"], check=True)
(HERE / "result.enc").write_bytes(sealed)
subprocess.run(["git", "add", str(HERE / "result.enc")], check=True)
subprocess.run(["git", *GIT_ID, "commit", "-qm", "chore: 암호화된 첨삭 시험 결과 [skip ci]"], check=True)
subprocess.run(["git", "push", "-q", "origin", f"HEAD:{branch}"], check=True)
# rerun 1794235382
# rerun2
# rerun3
