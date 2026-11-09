"""암호 상자: 공개 저장소에 아이 글·사진을 그대로 올리지 않으려고 쓰는 하이브리드 암호(RSA-OAEP + AES-GCM)."""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OAEP = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def seal(pub_pem: bytes, data: bytes) -> bytes:
    pub = serialization.load_pem_public_key(pub_pem)
    key, nonce = AESGCM.generate_key(256), os.urandom(12)
    box = {"k": pub.encrypt(key, OAEP), "n": nonce, "c": AESGCM(key).encrypt(nonce, data, None)}
    return json.dumps({k: base64.b64encode(v).decode() for k, v in box.items()}).encode()


def open_(priv, blob: bytes) -> bytes:
    box = {k: base64.b64decode(v) for k, v in json.loads(blob).items()}
    key = priv.decrypt(box["k"], OAEP)
    return AESGCM(key).decrypt(box["n"], box["c"], None)
