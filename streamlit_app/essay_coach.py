"""독서논술 첨삭 교실의 엔진 (Gemini 판독·첨삭 + 선생님 음성).

학습자료 페이지(pages/96_learning_korean_essay.py)에서만 쓴다. 감시 콘솔(shared)은 임포트하지 않는다.

흐름
    1. analyze()      독후감 사진(또는 글)을 Gemini 에 보내 첨삭 수업 자료(JSON)를 받는다.
    2. save_lesson()  자료를 static/essay_voice/<수업 번호>/lesson.json 에 저장한다.
    3. start_voice()  뒤에서(스레드) 장마다 해설 음성을 만들어 같은 폴더에 mp3 로 쓴다.
                      Gemini TTS Kore → 한도에 걸리면 Supertonic 3(F1) → 그래도 안 되면 비워 둔다.
                      (비어 있으면 수업 화면이 기기 목소리로 읽는다.)
    수업 화면은 app/static/essay_voice/<수업 번호>/ 주소에서 음성과 status.json 을 읽는다.

Gemini 키: Streamlit Secrets 또는 환경 변수의 GEMINI_API_KEY.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VOICE_DIR = HERE / "static" / "essay_voice"
VOICE_URL = "app/static/essay_voice/"  # 자료 iframe 기준 상대 주소 (study_page.audio_prefix 와 같은 방식)
KEEP_DAYS = 7
API = "https://generativelanguage.googleapis.com/v1beta"

GRADES = ["초등 3학년", "초등 4학년", "초등 5학년", "초등 6학년", "중학 1학년"]

# 글 판독·첨삭에 쓸 모델. 실제로 쓸 수 있는 모델 목록을 먼저 읽어 아래 순서로 고르고,
# 목록을 못 읽으면 이 순서대로 시도한다.
FALLBACK_TEXT_MODELS = [  # 앞에 있을수록 먼저
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]
TTS_MODELS = [
    "gemini-3.1-flash-tts-preview",
    "gemini-3.1-flash-preview-tts",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]
VOICE = "Kore"
VOICE_STYLE = (
    "경력이 오래된 독서논술 학원 선생님이 학생 한 명과 마주 앉아 첨삭 수업을 하듯, "
    "차분하고 또렷하며 신뢰감 있게 읽어 주세요. 과장된 감탄 없이, 중요한 곳은 힘주어 천천히:"
)


class CoachError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 오류."""


# ---------------------------------------------------------------------------
# 키
# ---------------------------------------------------------------------------
def api_key() -> str:
    val = os.environ.get("GEMINI_API_KEY", "").strip()
    if val:
        return val
    try:
        import streamlit as st

        sec = st.secrets
        for k in ("GEMINI_API_KEY", "gemini_api_key"):
            if k in sec and str(sec[k]).strip():
                return str(sec[k]).strip()
        for k in list(sec.keys()):  # [섹션] 안에 넣은 경우
            v = sec[k]
            if hasattr(v, "keys"):
                for sk in v.keys():
                    if str(sk).upper() == "GEMINI_API_KEY" and str(v[sk]).strip():
                        return str(v[sk]).strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# 사진 정리
# ---------------------------------------------------------------------------
def prepare_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """사진을 바로 세우고 긴 변 2000px JPEG 로 줄인다. 못 열면(HEIC 등) 원본 그대로."""
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((2000, 2000))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=88)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, mime or "image/jpeg"


# ---------------------------------------------------------------------------
# 첨삭 지침 (선생님 말투가 여기서 정해진다)
# ---------------------------------------------------------------------------
COMMON = """당신은 15년 차 초·중등 독서논술 전문 강사입니다. 독서논술 학원에서 초등 고학년 첨삭 수업을 맡고 있습니다.
학생의 독서감상문(손글씨 사진 또는 텍스트)을 판독하고, 1대1 첨삭 수업 자료를 JSON 으로 만듭니다.

[수업 태도]
- 칭찬은 근거가 분명한 것만, 짧고 구체적으로 합니다. "훌륭하다", "최고", "완벽", "대단하다", "멋지다", "정말 잘했다", "돋보인다" 같은 감탄과 느낌표는 쓰지 않습니다. 잘된 점은 "이 문장은 ~해서 효과가 있습니다"처럼 사실로 말합니다.
- 칭찬과 지적의 비율은 대략 3대 7입니다. 수업 시간 대부분은 고칠 점과 고치는 방법에 씁니다.
- 부족한 점은 돌려 말하지 말고 분명히 짚습니다. 반드시 왜 문제인지와 어떻게 고치는지를 함께 제시합니다.
- 평가 대상은 글이지 학생이 아닙니다. 다른 학생과 비교하거나 꾸짖지 않습니다.
- 말투는 학생에게 수업하는 존댓말입니다. "~입니다", "~해 봅시다", "~하세요"를 씁니다. 반말, 아기 말투, 이모지는 쓰지 않습니다.
- 전문 용어(서론·본론·결론, 주어와 서술어의 호응, 문체 통일, 근거)는 쓰되, 처음 나올 때 학년 수준으로 짧게 풀어 줍니다.
- 학생 학년에 맞는 어휘를 씁니다. 어려운 한자어로 바꾸거나 어른 문장으로 윤색하지 않습니다.
- 책 내용은 학생 글에 나온 정보와 당신이 확실히 아는 사실만 씁니다. 잘 모르는 책이면 줄거리를 지어내지 않습니다.

[판독 규칙]
- 사진 속 손글씨를 띄어쓰기와 맞춤법 오류까지 고치지 말고 그대로 옮깁니다. 줄이 아니라 문단이 바뀐 곳에서만 줄을 바꿉니다.
- 번지거나 흘려 써서 애매한 글자는 문맥상 가장 그럴듯한 글자로 추정해 [대괄호]로 표시합니다.
- 학생이 쓴 낱말을 뜻이 같은 다른 말로 바꿔 옮기지 않습니다(예: 외래어를 우리말로, 줄임말을 다른 줄임말로 바꾸지 않기). 글자 모양 그대로 옮깁니다.
- 판독이 애매한 글자를 맞춤법 오류로 단정하지 않습니다. 사진에서 분명히 틀리게 쓴 것만 오류로 지적합니다. 학생이 맞게 쓴 낱말을 틀렸다고 하면 안 됩니다.
- 사진이 여러 장이면 순서대로 이어 붙입니다. 제목·책 제목·이름이 보이면 따로 적습니다.
- 독서감상문이 아니거나 글씨를 거의 읽을 수 없으면 readable 을 false 로 하고 problem 에 이유를 적은 뒤 나머지는 비워 둡니다.


[처방 기준]
- 문단 구성: 서론(책 소개, 읽게 된 까닭, 짧은 줄거리) - 본론(인상 깊은 장면, 인물의 행동에 대한 내 생각과 그 까닭) - 결론(배운 점, 내 삶과 연결한 다짐). 학생의 실제 문장이 어디로 가야 하는지 알려 줍니다.
- 문체: 일기체(~했다)와 높임체(~했습니다)가 섞였으면 하나로 통일하게 합니다.
- 호응: 주어와 서술어가 맞지 않는 문장을 바로잡습니다.
- 어휘: 막연한 말(착하다, 나쁘다, 재미있다, 좋았다)을 상황에 맞는 정확한 말(배려심이 깊다, 이기적이다, 긴장감이 넘친다 등)로 바꾸는 대안을 줍니다.
- spelling 에는 맞춤법과 띄어쓰기만 넣습니다. 낱말을 바꾸자는 제안은 vocab 에, 문장을 고치는 것은 agreement·style 에 넣습니다.
- 규칙 설명은 한글 맞춤법(국립국어원) 기준으로 정확해야 합니다. 품사나 문법 용어가 확실하지 않으면 용어 없이 "~와 ~는 띄어 씁니다"처럼 쉽게 설명합니다.
- 띄어쓰기 오류는 원문에 있는 것을 빠짐없이 찾습니다(예: 감명 받은 → 감명받은, 생각해보자 → 생각해 보자).
- diagnosis 의 focus, rubric, 각 처방, narration 은 서로 같은 내용을 말해야 합니다. 처방에서 문제없다고 한 것을 focus 로 삼지 않습니다.
- 문제가 없는 항목은 억지로 만들지 말고 빈 배열로 둡니다. 대신 그 항목이 잘 된 이유를 diagnosis 에 한 문장으로 적습니다.

[음성 대본(narration) 규칙] 성우가 그대로 읽습니다.
- 학생에게 직접 말하는 수업 말투로 씁니다. 화면에 보이는 내용을 그대로 나열하지 말고, 핵심을 짚어 설명합니다.
- 숫자는 읽는 대로 한글로 씁니다(예: 두 가지, 세 번째 문단). 괄호, 따옴표, 화살표, 대괄호, 기호, 영어 약어를 쓰지 않습니다.
- 선생님 자신의 경력이나 "AI"를 말하지 않습니다.
- 학생 이름이 주어지면 "OO 학생" 또는 "OO이가 쓴 이 문장은"처럼 자연스럽게 부르되 존댓말을 지킵니다.
- 각 대본은 한국어 250~450자입니다(practice 는 120자 안팎). 짧게 요약하지 말고, 화면의 핵심 내용을 실제 수업처럼 풀어 설명합니다.
- 처방 대본(structure, style, vocab, spelling)은 학생 글의 실제 문장이나 낱말을 하나 이상 짚어 말하고, 왜 틀렸는지와 고친 모습을 함께 말합니다.
- 숫자 낱말은 바르게 씁니다(네 가지, 세 문단, 다섯 개). 글자 수 같은 큰 숫자는 대본에서 말하지 않습니다.
- 대본에서도 "훌륭하다", "대단하다", "멋지다", "최고", "완벽" 같은 감탄은 쓰지 않습니다.
"""

SYSTEM_COACH = COMMON + """
[할 일] 첨삭 순서: 원문 판독 → 진단(평가표) → 강점 2가지 → 처방(문단 구성, 문체·호응, 어휘, 맞춤법·띄어쓰기) → 생각을 키우는 질문 → 완성본 → 공책 한 줄 코멘트.

[출력 JSON 형식] 아래 키를 모두 채웁니다. 문자열 안의 문단 구분은 \\n\\n 입니다.
{
 "readable": true,
 "problem": "",
 "student_name": "사진이나 입력에서 확인된 이름, 없으면 빈칸",
 "book_title": "책 제목 (모르면 빈칸)",
 "book_author": "지은이 (확실할 때만)",
 "essay_title": "학생이 붙인 글 제목 (없으면 빈칸)",
 "transcription": "원문 그대로",
 "uncertain": ["판독이 애매했던 부분과 추정한 글자 설명"],
 "char_count": 원문 글자 수(숫자),
 "diagnosis": {
   "overall": "총평 한두 문장",
   "focus": "이번 첨삭에서 가장 먼저 고칠 한 가지",
   "rubric": [
     {"area": "내용 이해", "level": "우수|보통|보완", "note": "근거 한 문장"},
     {"area": "생각의 깊이", "level": "...", "note": "..."},
     {"area": "글의 구성", "level": "...", "note": "..."},
     {"area": "표현과 표기", "level": "...", "note": "..."}
   ]
 },
 "strengths": [
   {"title": "강점 이름", "quote": "학생 글에서 그대로 인용한 문장", "why": "왜 잘된 것인지 한두 문장"}
 ],
 "structure": {
   "diagnosis": "지금 글의 구성 진단",
   "parts": [
     {"part": "서론", "role": "이 문단이 할 일", "from_text": "학생 글에서 여기에 들어갈 문장 요약 또는 인용", "missing": "더 써야 할 것 (없으면 빈칸)"},
     {"part": "본론", "role": "...", "from_text": "...", "missing": "..."},
     {"part": "결론", "role": "...", "from_text": "...", "missing": "..."}
   ]
 },
 "style": {"diagnosis": "문체 진단", "fixes": [{"before": "원문 문장", "after": "고친 문장", "why": "이유"}]},
 "agreement": [{"before": "원문 문장", "after": "고친 문장", "why": "주어와 서술어가 어떻게 어긋났는지"}],
 "vocab": [{"before": "원문의 낱말이나 표현", "after": "대안 표현", "context": "고친 문장 예", "why": "이유"}],
 "spelling": [{"before": "원문 표기", "after": "바른 표기", "rule": "짧은 규칙 설명"}],
 "practice": [
   {"kind": "맞춤법|어휘|호응|문체|구성", "sentence": "학생 글의 문장을 글자 그대로", "question": "무엇을 고르는지 한 문장", "options": ["보기1", "보기2", "보기3"], "answer": 정답 번호(0부터), "explain": "해설 한 문장"}
 ],
 "think_question": {"question": "책의 핵심 문제를 학생의 실제 생활(학교, 친구, 가족)과 잇는 열린 질문 하나", "hint": "생각을 시작하는 실마리 한 문장"},
 "final_version": "최종 추천 완성본. 학생의 생각·감상·어조를 그대로 두고 문단 나누기, 맞춤법·띄어쓰기, 문체 통일, 호응, 위 vocab 에서 제안한 낱말 바꾸기만 반영합니다. 학생이 쓰지 않은 새 생각, 감정, 줄거리를 덧붙이지 않고, 학생이 쓴 내용의 뜻을 바꾸지 않습니다.",
 "comments": {"praise": "[칭찬형] 공책 하단 1~2줄", "question": "[질문형] 칭찬과 생각 확장 질문 1~2줄"},
 "parent_note": ["보호자에게: 다음 지도 포인트 (2~3개)"],
 "task": {
   "title": "다시 쓰기 과제 이름",
   "instruction": "무엇을 어떻게 다시 쓰는지",
   "frames": ["문장 틀 1 (예: 내가 가장 인상 깊었던 장면은 ~이다.)", "문장 틀 2", "문장 틀 3"],
   "checklist": ["다음 독서록을 쓸 때 스스로 점검할 항목 5개"]
 },
 "narration": {
   "intro": "(250자 안팎) 인사, 오늘 다룰 책과 글, 수업 순서, 오늘의 핵심 과제 예고",
   "read": "(200자 안팎) 원문을 그대로 옮긴 까닭, 대괄호 표시 뜻, 글의 분량과 첫인상을 사실대로",
   "diag": "(350자 안팎) 평가표 네 항목을 하나씩 짚어 단계와 근거를 말하고, 가장 먼저 고칠 것을 분명히",
   "strength": "(300자 안팎) 강점 두 가지를 학생 문장을 인용하며 왜 효과가 있는지 설명",
   "structure": "(400자 안팎) 지금 구성의 문제, 서론·본론·결론 각각에 학생의 어느 문장이 가고 무엇을 더 써야 하는지",
   "style": "(400자 안팎) 섞인 문체를 실제 문장으로 보여 주고 어느 쪽으로 통일하는지, 호응이 어긋난 문장과 고친 문장",
   "vocab": "(350자 안팎) 막연한 낱말 각각을 왜 바꾸는지, 어떤 말로 바꾸면 무엇이 더 정확해지는지",
   "spelling": "(350자 안팎) 틀린 표기마다 바른 표기와 규칙을 짧게. 다음에 스스로 점검하는 방법",
   "practice": "(120자 안팎) 연습 문제 안내. 직접 푸는 활동",
   "question": "(250자 안팎) 질문을 읽어 주고, 어떻게 생각을 펼치면 좋은지 실마리",
   "final": "(350자 안팎) 완성본에서 무엇이 어떻게 달라졌는지 문단·문체·어휘·표기 순서로",
   "task": "(250자 안팎) 다시 쓰기 과제 방법과 점검표 쓰는 법",
   "end": "(250자 안팎) 오늘 배운 것 요약, 다음 독서록에서 꼭 지킬 두 가지"
 }
}
- strengths 는 정확히 2개, practice 는 학생 글의 실제 문제로 4~6개입니다. practice 의 보기는 서로 비슷해 보여 생각해야 고를 수 있게 만들고, 정답이 늘 같은 자리에 오지 않게 합니다.
- comments 는 공책에 손으로 적을 짧은 문장입니다. 느낌표와 과장된 칭찬 없이 구체적으로 씁니다.
"""

SYSTEM_MODEL = COMMON + """
[할 일] 이 학생이 읽은 책으로 학생이 읽고 따라 배울 "추천 독서록" 두 편을 새로 씁니다. 학생 글을 고치는 것이 아니라 선생님이 쓴 예시 글입니다.
- 학생 글에서 책 제목과 내용을 확인합니다. 학생이 다룬 장면과 주제를 살리되, 더 깊은 생각과 근거, 정돈된 문단 구성을 보여 줍니다.
- 같은 학년 우수작 수준의 어휘와 문장으로 씁니다. 어른 평론처럼 쓰지 않습니다.
- 본문은 그 자체로 완성된 한 편의 글입니다. 학생 이름, 학년, "학생은 ~라고 썼지만" 같은 첨삭 말은 넣지 않습니다. 글쓴이는 이름 없는 "나"입니다(편지글도 이름을 밝히지 않습니다).
- 정석 독후감은 "~다"체(해라체)로 끝까지 통일합니다. 편지글은 편지 말투로 씁니다. 맞춤법과 띄어쓰기는 틀림없이 씁니다.
- 잘 모르는 책이면 학생 글에 나온 내용만으로 씁니다. 줄거리를 지어내지 않습니다.

[출력 JSON 형식]
{
 "book_title": "책 제목",
 "model_essays": [
   {"form": "정석 독후감", "title": "제목", "text": "같은 책으로 쓴 모범 독후감. 같은 학년 우수작 수준, 서론-본론-결론, 650~900자", "points": ["이 글에서 배울 점 3개"], "highlight": ["본문에 그대로 있는 배울 만한 구절 3~4개"]},
   {"form": "편지글 또는 주장하는 서평 중 이 책에 어울리는 형식", "title": "제목", "text": "400~700자", "points": ["배울 점 3개"], "highlight": ["구절 2~3개"]}
 ],
 "narration": {
   "model1": "추천 독서록 1을 읽기 전에 선생님이 하는 소개 두세 문장. 이 글에서 무엇을 눈여겨 들을지",
   "model2": "추천 독서록 2 소개 두세 문장. 형식이 어떻게 다른지"
 }
}
- model_essays 는 정확히 2편입니다. highlight 의 구절은 text 안에 글자 그대로 있어야 합니다.
"""


def _user_prompt(book: str, grade: str, name: str, typed: str, n_images: int, job: str) -> str:
    lines = [f"학생 학년: {grade}"]
    if name:
        lines.append(f"학생 이름: {name}")
    if book:
        lines.append(f"책 제목(보호자 입력): {book}")
    if n_images:
        lines.append(f"첨부한 학생 독후감 사진 {n_images}장을 읽고 {job}")
    if typed:
        lines.append("아래는 학생 글을 그대로 옮겨 적은 것입니다. 이 글을 원문으로 삼으세요."
                     if not n_images else "아래는 보호자가 덧붙인 글입니다. 사진과 함께 참고하세요.")
        lines.append("----- 학생 글 -----\n" + typed.strip())
    if not n_images:
        lines.append(f"위 학생 글을 읽고 {job}")
    lines.append("출력은 지정한 JSON 하나만.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 모델 고르기
# ---------------------------------------------------------------------------
def _get(url: str, timeout: int = 20) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def _post(url: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


_MODEL_CACHE: dict[str, tuple[float, list[str], list[str]]] = {}


def _models(key: str) -> tuple[list[str], list[str]]:
    """(글 모델, 음성 모델) 을 좋은 순서로. 한 시간 동안 기억한다."""
    hit = _MODEL_CACHE.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1], hit[2]
    try:
        listed = _get(f"{API}/models?pageSize=1000&key={key}").get("models", [])
    except Exception:
        return FALLBACK_TEXT_MODELS, TTS_MODELS
    names = [m["name"].split("/", 1)[1] for m in listed
             if "generateContent" in m.get("supportedGenerationMethods", [])]

    def rank(n: str) -> tuple:
        m = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-(flash|pro)(-lite)?(-preview)?(?:-\d\d-\d\d)?", n)
        if not m:
            return ()
        ver = float(m.group(1))
        kind = 0 if (m.group(2) == "flash" and not m.group(3)) else (1 if m.group(2) == "pro" else 2)
        return (kind, -ver, 1 if m.group(4) else 0, n)

    # 검증된 모델을 먼저 쓴다. (2026-11 시험: 3.8·3.7 flash 는 무료 키에서 2분 넘게 응답이 없었고 3.6 flash 는 30초 안팎)
    text = [n for n in FALLBACK_TEXT_MODELS if n in names]
    text += sorted((n for n in names if rank(n) and n not in text), key=rank)
    tts = [n for n in TTS_MODELS if n in names]
    tts += sorted((n for n in names if "tts" in n and n not in tts), reverse=True)
    text, tts = text or FALLBACK_TEXT_MODELS, tts or TTS_MODELS
    _MODEL_CACHE[key] = (time.time(), text, tts)
    return text, tts


# ---------------------------------------------------------------------------
# 첨삭
# ---------------------------------------------------------------------------
def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1], strict=False)
        raise


def _gen_config(model: str, thinking: bool) -> dict:
    cfg: dict[str, Any] = {"responseMimeType": "application/json", "temperature": 0.4,
                           "maxOutputTokens": 16000}
    if thinking:
        # 생각을 길게 하면 3분이 넘게 걸린다. 첨삭은 짧게 생각해도 충분하다.
        if re.match(r"gemini-([3-9]|\d\d)", model):
            cfg["thinkingConfig"] = {"thinkingLevel": "low"}
        elif "2.5" in model:
            cfg["thinkingConfig"] = {"thinkingBudget": 1024}
    return cfg


def _stream(model: str, key: str, body: dict, read_timeout: int = 75) -> str:
    """streamGenerateContent(SSE)로 받아 글자를 모은다. 오래 걸려도 중간에 끊기지 않는다."""
    req = urllib.request.Request(
        f"{API}/models/{model}:streamGenerateContent?alt=sse&key={key}",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    chunks: list[str] = []
    reason = ""
    with urllib.request.urlopen(req, timeout=read_timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                print(f"[essay] SSE 줄을 못 읽음: {line[:120]!r}", flush=True)
                continue
            cand = (ev.get("candidates") or [{}])[0]
            for part in cand.get("content", {}).get("parts", []) or []:
                if part.get("text") and not part.get("thought"):
                    chunks.append(part["text"])
            reason = cand.get("finishReason") or reason
    text = "".join(chunks)
    print(f"[essay] {model} 받은 조각 {len(chunks)}개, 글자 {len(text)}, 끝난 이유 {reason}, 끝부분 {text[-60:]!r}", flush=True)
    # 끝난 이유가 없으면 중간에 끊긴 것이다 (2026-11 시험: 일부 모델에서 스트림이 몇 초 만에 끊김)
    if not text.strip() or reason not in ("STOP", "MAX_TOKENS"):
        raise ValueError(f"응답이 끊김 finishReason={reason} 길이={len(text)} 앞부분={text[:80]!r}")
    return text


def _ask(key: str, models: list[str], system: str, parts: list[dict], deadline: float) -> dict:
    """모델을 차례로 바꿔 가며 JSON 을 받는다."""
    last = ""
    for model in models[:4]:
        for thinking in (True, False):
            if time.time() > deadline:
                raise CoachError(f"첨삭이 너무 오래 걸려 멈췄어요. 잠시 뒤 다시 해 주세요. ({last[:120]})")
            body = {"systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": _gen_config(model, thinking)}
            t0 = time.time()
            try:
                got = _parse_json(_stream(model, key, body))
                print(f"[essay] {model} thinking={thinking} ok {time.time() - t0:.0f}s", flush=True)
                return got
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                last = f"{model}: {e.code} {detail}"
                print(f"[essay] {last[:200]}", flush=True)
                if e.code in (400, 401, 403) and "API key" in detail:
                    raise CoachError("Gemini 키가 맞지 않아요. Streamlit Secrets 의 GEMINI_API_KEY 를 확인해 주세요.")
                if e.code == 400 and thinking:
                    continue  # 이 모델이 모르는 설정이 있다 -> 기본 설정으로 다시
                if e.code in (500, 503) and thinking:
                    time.sleep(3)
                    continue  # 잠깐 붐빈다 -> 한 번 더
                break
            except (json.JSONDecodeError, ValueError) as e:
                last = f"{model}: 결과를 읽지 못함 ({e})"
                print(f"[essay] {last} {time.time() - t0:.0f}s", flush=True)
                break
            except Exception as e:  # 시간 초과·연결 끊김
                last = f"{model}: {type(e).__name__} {e}"
                print(f"[essay] {last} {time.time() - t0:.0f}s", flush=True)
                break
    if "429" in last:
        raise CoachError("오늘 Gemini 사용 한도를 다 썼어요. 내일(한국 시간 오후 5시 이후) 다시 해 주세요.")
    raise CoachError(f"첨삭을 만들지 못했어요. 잠시 뒤 다시 해 주세요. ({last[:160]})")


def analyze(images: list[tuple[bytes, str]], typed: str = "", book: str = "",
            grade: str = "초등 5학년", name: str = "") -> dict:
    """독후감을 판독·첨삭한다. 첨삭과 추천 독서록을 동시에 요청해 기다리는 시간을 줄인다. 실패하면 CoachError."""
    key = api_key()
    if not key:
        raise CoachError("NO_KEY")
    if not images and not typed.strip():
        raise CoachError("독후감 사진을 올리거나 글을 입력해 주세요.")
    img_parts = [{"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}
                 for data, mime in images]
    coach_parts = [{"text": _user_prompt(book, grade, name, typed, len(images),
                                         "첨삭 수업 자료를 만들어 주세요.")}] + img_parts
    model_parts = [{"text": _user_prompt(book, grade, name, typed, len(images),
                                         "같은 책으로 추천 독서록 두 편을 써 주세요.")}] + img_parts
    text_models, _ = _models(key)
    deadline = time.time() + 280
    box: dict[str, Any] = {}

    def side() -> None:
        try:
            box["model"] = _ask(key, text_models, SYSTEM_MODEL, model_parts, deadline)
        except Exception as e:  # 추천 독서록이 없어도 첨삭은 보여 준다
            box["model_err"] = e

    th = threading.Thread(target=side, daemon=True)
    th.start()
    coach = _ask(key, text_models, SYSTEM_COACH, coach_parts, deadline)
    th.join(timeout=max(5, deadline - time.time()))
    extra = box.get("model") if isinstance(box.get("model"), dict) else {}
    merged = dict(coach)
    merged["model_essays"] = extra.get("model_essays") or coach.get("model_essays") or []
    nar = dict(coach.get("narration") or {})
    for k, v in (extra.get("narration") or {}).items():
        nar.setdefault(k, v)
    merged["narration"] = nar
    if not merged.get("book_title") and extra.get("book_title"):
        merged["book_title"] = extra["book_title"]
    out = normalize(merged)
    # 추천 독서록 대본 = 선생님 소개 + 본문 전체 (본문을 두 번 쓰게 하지 않으려고 여기서 붙인다)
    for i, m in enumerate(out["model_essays"], 1):
        intro = out["narration"].get(f"model{i}", "")
        title = f"제목은 {m['title']}입니다. " if m["title"] else ""
        out["narration"][f"model{i}"] = clean_speech(f"{intro} {title}{m['text']}")
    return out


def _s(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ("" if v is None else str(v))


def _list(v: Any) -> list:
    return v if isinstance(v, list) else []


def normalize(d: dict) -> dict:
    """빠진 키를 채워 화면이 어떤 결과에도 깨지지 않게 한다."""
    if not isinstance(d, dict):
        raise ValueError("JSON 객체가 아님")
    out: dict[str, Any] = {k: _s(d.get(k)) for k in
                           ("problem", "student_name", "book_title", "book_author", "essay_title",
                            "transcription", "final_version")}
    out["readable"] = d.get("readable") is not False and bool(out["transcription"])
    out["uncertain"] = [_s(x) for x in _list(d.get("uncertain")) if _s(x)]
    diag = d.get("diagnosis") if isinstance(d.get("diagnosis"), dict) else {}
    out["diagnosis"] = {
        "overall": _s(diag.get("overall")), "focus": _s(diag.get("focus")),
        "rubric": [{"area": _s(r.get("area")), "level": _s(r.get("level")) or "보통", "note": _s(r.get("note"))}
                   for r in _list(diag.get("rubric")) if isinstance(r, dict) and _s(r.get("area"))],
    }
    out["strengths"] = [{"title": _s(x.get("title")), "quote": _s(x.get("quote")), "why": _s(x.get("why"))}
                        for x in _list(d.get("strengths")) if isinstance(x, dict)][:3]
    st_ = d.get("structure") if isinstance(d.get("structure"), dict) else {}
    out["structure"] = {"diagnosis": _s(st_.get("diagnosis")),
                        "parts": [{k: _s(p.get(k)) for k in ("part", "role", "from_text", "missing")}
                                  for p in _list(st_.get("parts")) if isinstance(p, dict)]}
    sty = d.get("style") if isinstance(d.get("style"), dict) else {}
    out["style"] = {"diagnosis": _s(sty.get("diagnosis")),
                    "fixes": [{k: _s(f.get(k)) for k in ("before", "after", "why")}
                              for f in _list(sty.get("fixes")) if isinstance(f, dict) and _s(f.get("before"))]}
    out["agreement"] = [{k: _s(f.get(k)) for k in ("before", "after", "why")}
                        for f in _list(d.get("agreement")) if isinstance(f, dict) and _s(f.get("before"))]
    out["vocab"] = [{k: _s(f.get(k)) for k in ("before", "after", "context", "why")}
                    for f in _list(d.get("vocab")) if isinstance(f, dict) and _s(f.get("before"))]
    out["spelling"] = [{k: _s(f.get(k)) for k in ("before", "after", "rule")}
                       for f in _list(d.get("spelling")) if isinstance(f, dict) and _s(f.get("before"))]
    prac = []
    for p in _list(d.get("practice")):
        if not isinstance(p, dict):
            continue
        opts = [_s(o) for o in _list(p.get("options")) if _s(o)]
        try:
            ans = int(p.get("answer"))
        except (TypeError, ValueError):
            continue
        if len(opts) >= 2 and 0 <= ans < len(opts):
            prac.append({"kind": _s(p.get("kind")), "sentence": _s(p.get("sentence")),
                         "question": _s(p.get("question")), "options": opts, "answer": ans,
                         "explain": _s(p.get("explain"))})
    out["practice"] = prac[:6]
    tq = d.get("think_question") if isinstance(d.get("think_question"), dict) else {}
    out["think_question"] = {"question": _s(tq.get("question")), "hint": _s(tq.get("hint"))}
    cm = d.get("comments") if isinstance(d.get("comments"), dict) else {}
    out["comments"] = {"praise": _s(cm.get("praise")), "question": _s(cm.get("question"))}
    out["parent_note"] = [_s(x) for x in _list(d.get("parent_note")) if _s(x)]
    tk = d.get("task") if isinstance(d.get("task"), dict) else {}
    out["task"] = {"title": _s(tk.get("title")), "instruction": _s(tk.get("instruction")),
                   "frames": [_s(x) for x in _list(tk.get("frames")) if _s(x)],
                   "checklist": [_s(x) for x in _list(tk.get("checklist")) if _s(x)]}
    out["model_essays"] = [
        {"form": _s(m.get("form")), "title": _s(m.get("title")), "text": _s(m.get("text")),
         "points": [_s(x) for x in _list(m.get("points")) if _s(x)],
         "highlight": [_s(x) for x in _list(m.get("highlight")) if _s(x)]}
        for m in _list(d.get("model_essays")) if isinstance(m, dict) and _s(m.get("text"))][:2]
    nar = d.get("narration") if isinstance(d.get("narration"), dict) else {}
    out["narration"] = {str(k): clean_speech(_s(v)) for k, v in nar.items() if _s(v)}
    try:
        out["char_count"] = int(d.get("char_count") or len(re.sub(r"\s", "", out["transcription"])))
    except (TypeError, ValueError):
        out["char_count"] = len(re.sub(r"\s", "", out["transcription"]))
    return out


def clean_speech(t: str) -> str:
    """성우가 소리 내어 읽기 어려운 기호를 걷어 낸다."""
    t = re.sub(r"[\[\]{}<>«»「」『』\"“”‘’*#_~`|]", "", t)
    t = t.replace("→", ", ").replace("·", ", ").replace("…", ". ")
    t = re.sub(r"\(([^)]*)\)", r", \1,", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# 수업 저장·불러오기
# ---------------------------------------------------------------------------
_ID_RE = re.compile(r"^[0-9a-f]{20}$")


def new_id() -> str:
    return uuid.uuid4().hex[:20]


def lesson_dir(lid: str) -> Path:
    if not _ID_RE.match(lid or ""):
        raise ValueError("bad id")
    return VOICE_DIR / lid


def save_lesson(lid: str, data: dict) -> None:
    d = lesson_dir(lid)
    d.mkdir(parents=True, exist_ok=True)
    _write_atomic(d / "lesson.json", json.dumps(data, ensure_ascii=False).encode())


def load_lesson(lid: str) -> dict | None:
    try:
        return json.loads((lesson_dir(lid) / "lesson.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def cleanup_old() -> None:
    if not VOICE_DIR.exists():
        return
    limit = time.time() - KEEP_DAYS * 86400
    for d in VOICE_DIR.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 음성 (뒤에서 만든다)
# ---------------------------------------------------------------------------
SLIDE_ORDER = ["intro", "read", "diag", "strength", "structure", "style", "vocab", "spelling",
               "practice", "question", "final", "model1", "model2", "task", "end"]


def voice_items(data: dict) -> list[tuple[str, str]]:
    nar = data.get("narration", {})
    return [(k, nar[k]) for k in SLIDE_ORDER if nar.get(k)]


def _pcm_to_file(pcm: bytes, dest_mp3: Path, rate: int = 24000) -> Path:
    """mp3(lameenc 가 있으면) 또는 wav 로 저장하고 실제 파일 경로를 돌려준다."""
    try:
        import lameenc

        enc = lameenc.Encoder()
        enc.set_bit_rate(64)
        enc.set_in_sample_rate(rate)
        enc.set_channels(1)
        enc.set_quality(5)
        mp3 = enc.encode(pcm) + enc.flush()
        _write_atomic(dest_mp3, bytes(mp3))
        return dest_mp3
    except Exception:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
        dest = dest_mp3.with_suffix(".wav")
        _write_atomic(dest, buf.getvalue())
        return dest


def _trim_pcm(pcm: bytes, rate: int = 24000) -> bytes:
    """앞뒤의 긴 무음을 잘라 낸다 (Gemini 음성은 앞에 무음이 붙는 일이 있다)."""
    try:
        import numpy as np

        a = np.frombuffer(pcm, dtype="<i2")
        loud = np.nonzero(np.abs(a) > 500)[0]
        if len(loud) == 0:
            return pcm
        s = max(0, loud[0] - int(rate * 0.12))
        e = min(len(a), loud[-1] + int(rate * 0.3))
        return a[s:e].tobytes()
    except Exception:
        return pcm


class _Quota(Exception):
    pass


def _gemini_tts(key: str, models: list[str], text: str) -> bytes:
    body = {
        "contents": [{"parts": [{"text": f"{VOICE_STYLE}\n{text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}},
        },
    }
    quota = False
    for model in models:
        for attempt in range(3):
            try:
                res = _post(f"{API}/models/{model}:generateContent?key={key}", body, timeout=150)
                part = res["candidates"][0]["content"]["parts"][0]
                return base64.b64decode(part["inlineData"]["data"])
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    # 분당 제한이면 잠깐 쉬면 풀린다. 두 번 연속이면 하루 한도로 본다.
                    if attempt < 1:
                        time.sleep(25)
                        continue
                    quota = True
                    break
                if e.code in (500, 503) and attempt < 2:
                    time.sleep(4 * (attempt + 1))
                    continue
                break
            except (KeyError, IndexError):
                break
            except Exception:
                if attempt < 1:
                    continue
                break
    if quota:
        raise _Quota
    raise RuntimeError("tts failed")


_SUPERTONIC = None
_SUPERTONIC_LOCK = threading.Lock()


def _supertonic_pcm(text: str) -> bytes:
    """공개 AI 성우 Supertonic 3 (F1, 한도 없음). 설치돼 있지 않으면 ImportError."""
    global _SUPERTONIC
    import numpy as np
    from supertonic import TTS

    with _SUPERTONIC_LOCK:
        if _SUPERTONIC is None:
            _SUPERTONIC = TTS(auto_download=True)
        tts = _SUPERTONIC
        wav, _ = tts.synthesize(text=text, voice_style=tts.get_voice_style(voice_name="F1"),
                                total_steps=10, speed=1.0, lang="ko")
    wav = np.asarray(wav, dtype=np.float32).reshape(-1)
    sr = getattr(tts, "sample_rate", None) or 44100
    if sr != 24000:
        idx = np.linspace(0, len(wav) - 1, int(len(wav) * 24000 / sr))
        wav = np.interp(idx, np.arange(len(wav)), wav)
    return (np.clip(wav, -1, 1) * 32767).astype("<i2").tobytes()


def _status_write(d: Path, status: dict) -> None:
    _write_atomic(d / "status.json", json.dumps(status, ensure_ascii=False).encode())


def read_status(lid: str) -> dict:
    try:
        return json.loads((lesson_dir(lid) / "status.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


_RUNNING: set[str] = set()
_RUN_LOCK = threading.Lock()


def start_voice(lid: str, data: dict) -> None:
    """해설 음성을 뒤에서 만든다. 이미 돌고 있거나 다 만든 수업이면 아무것도 안 한다."""
    d = lesson_dir(lid)
    items = voice_items(data)
    status = read_status(lid)
    if status.get("done") and all(k in status.get("files", {}) for k, _ in items):
        return
    with _RUN_LOCK:
        if lid in _RUNNING:
            return
        _RUNNING.add(lid)
    threading.Thread(target=_voice_worker, args=(lid, d, items), daemon=True).start()


def _voice_worker(lid: str, d: Path, items: list[tuple[str, str]]) -> None:
    try:
        key = api_key()
        _, tts_models = _models(key) if key else ([], [])
        status = read_status(lid) or {}
        files: dict[str, str] = status.get("files", {})
        engine: dict[str, str] = status.get("engine", {})
        failed: list[str] = []
        status = {"done": False, "files": files, "engine": engine, "failed": failed,
                  "pending": [k for k, _ in items if k not in files]}
        _status_write(d, status)
        gemini_ok = bool(key)
        for k, text in items:
            if k in files:
                continue
            pcm = None
            if gemini_ok:
                try:
                    pcm = _trim_pcm(_gemini_tts(key, tts_models, text))
                    engine[k] = "kore"
                except _Quota:
                    gemini_ok = False
                except Exception:
                    pcm = None
            if pcm is None:
                try:
                    pcm = _supertonic_pcm(text)
                    engine[k] = "supertonic"
                except Exception:
                    pcm = None
            if pcm:
                path = _pcm_to_file(pcm, d / f"{k}.mp3")
                files[k] = path.name
            else:
                failed.append(k)
            status["pending"] = [x for x, _ in items if x not in files and x not in failed]
            _status_write(d, status)
            if engine.get(k) == "kore":
                time.sleep(3)  # 무료 키의 분당 요청 제한을 넘지 않도록
        status["done"] = True
        status["pending"] = []
        _status_write(d, status)
    finally:
        with _RUN_LOCK:
            _RUNNING.discard(lid)
