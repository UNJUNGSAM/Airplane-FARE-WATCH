"""학습자료 페이지 공통 코드.

항공권 감시 콘솔과는 별개다. shared(감시 콘솔)를 임포트하지 않으므로 감시 콘솔 코드가 바뀌어도
영향을 받지 않는다. 대신 학습자료만의 비밀번호 문(gate)이 있다 (아래 '비밀번호' 부분).

자료 한 개 = static/learning/<slug>/ 폴더 하나 (slug = 과목_주제, 영문 소문자)
    index.html      자료 본문 (그대로 넣은 HTML)
    audio/*.mp3     해설 음성 (있을 때만)

새 자료를 추가하는 법
    1. static/learning/<slug>/ 에 index.html 과 audio/ 를 넣는다.
    2. 아래 CATALOG 에 한 줄 추가한다.
    3. pages/9N_learning_<slug>.py 를 기존 파일과 똑같이 만든다 (주소: /learning_<slug>).
    학습자료 전용 앱(study_app.py)에는 위 세 단계만으로 자동으로 나타난다.

과목 이름: korean(국어) math(수학) social(사회) science(과학) english(영어)
           music(음악) art(미술) pe(체육) ethics(도덕) practical(실과)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import date
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

STUDY_DIR = Path(__file__).resolve().parent / "static" / "learning"

# 학교급. 목록 화면 맨 앞의 초등/중학 버튼이 이 순서로 나온다.
LEVELS: dict[str, str] = {"elem": "초등", "middle": "중학"}

# 과목 카테고리. 목록 화면의 과목 메뉴가 이 순서로 나온다.
# color 는 과목별 표지 색 (차분한 톤), levels 는 그 과목이 있는 학교급.
_BOTH = ("elem", "middle")
SUBJECTS: dict[str, dict] = {
    "korean": {"name": "국어", "color": "#b5523b", "levels": _BOTH},
    "math": {"name": "수학", "color": "#3f5f9e", "levels": _BOTH},
    "social": {"name": "사회", "color": "#2d6a5a", "levels": _BOTH},
    "history": {"name": "역사", "color": "#8a5a3c", "levels": ("middle",)},
    "science": {"name": "과학", "color": "#2f6f8f", "levels": _BOTH},
    "english": {"name": "영어", "color": "#6a4c93", "levels": _BOTH},
    "ethics": {"name": "도덕", "color": "#7a6248", "levels": _BOTH},
    "practical": {"name": "실과", "color": "#5d6b4a", "levels": ("elem",)},
    "tech": {"name": "기술·가정", "color": "#5d6b4a", "levels": ("middle",)},
    "info": {"name": "정보", "color": "#3d6f73", "levels": ("middle",)},
    "music": {"name": "음악", "color": "#9a5a7a", "levels": _BOTH},
    "art": {"name": "미술", "color": "#a8722a", "levels": _BOTH},
    "pe": {"name": "체육", "color": "#4f7a3a", "levels": _BOTH},
}

# 목록 페이지에 보이는 순서대로 적는다. 과목은 slug 앞부분(과목_주제)에서 정해진다.
#   level   학교급 (LEVELS 의 키: elem 초등, middle 중학)
#   grade   학년 (숫자), term 학기 (1 또는 2)
#   unit    교과서 단원 이름
#   desc    다루는 내용 한 줄
#   slides  화면 장 수, minutes 해설 음성 길이(분, 대략)
CATALOG: list[dict] = [
    {
        "slug": "science_heat",
        "title": "열 탐구 노트",
        "level": "elem",
        "grade": 5,
        "term": 2,
        "unit": "3. 열과 우리 생활",
        "desc": "온도와 온도계, 열의 이동, 전도·대류·단열을 생활 속 예로 익혀요.",
        "slides": 18,
        "minutes": 10,
    },
    {
        "slug": "social_goryeo",
        "title": "고려 문화 탐험노트",
        "level": "elem",
        "grade": 5,
        "term": 2,
        "unit": "유적과 유물로 살펴본 옛사람들의 생활",
        "desc": "고려청자, 팔만대장경, 직지, 불교문화, 벽란도, 생활 모습을 살펴봐요.",
        "slides": 18,
        "minutes": 13,
    },
    {
        "slug": "english_time",
        "title": "시간 전치사 탐구 노트",
        "level": "elem",
        "grade": 5,
        "term": 2,
        "unit": "Unit 11. Prepositions of Time",
        "desc": "at·on·in을 시간의 크기로 구별하고, When과 What time으로 묻고 답해요.",
        "slides": 16,
        "minutes": 7,
    },
    {
        "slug": "english_place",
        "title": "장소 전치사 탐구 노트",
        "level": "elem",
        "grade": 5,
        "term": 2,
        "unit": "Unit 12. Prepositions of Place",
        "desc": "in·on·under·next to 등 위치를 말하는 전치사와 There is / There are를 익혀요.",
        "slides": 16,
        "minutes": 8,
    },
    {
        "slug": "math_decimal",
        "title": "소수의 곱셈 맞춤 노트",
        "level": "elem",
        "grade": 5,
        "term": 2,
        "unit": "4. 소수의 곱셈",
        "desc": "로운이의 실수 습관 4가지(소수점 자릿수, 문장제, 수 카드, 마무리 계산)를 쌍둥이 문제로 고쳐요.",
        "slides": 17,
        "minutes": 7,
    },
    {
        # 고정 자료가 아니라, 보호자가 올린 독후감 사진을 Gemini 가 읽고 그때그때 첨삭 수업을 만든다.
        # 본문은 pages/96_learning_korean_essay.py + essay_coach.py, 화면 틀은 static/learning/korean_essay/lesson.html
        "slug": "korean_essay",
        "title": "독서논술 첨삭 교실",
        "level": "elem",
        "grade": 5,
        "term": 2,
        "unit": "독서감상문 쓰기 · 초5 이상",
        "desc": "독후감 사진을 올리면 원문 판독, 진단, 처방, 완성본까지 1대1로 첨삭하고 추천 독서록 두 편을 함께 읽어요.",
        "slides": 15,
        "minutes": 10,
    },
]


def grade_label(item: dict, short: bool = False) -> str:
    """학년·학기 표시. short=True 면 '초5-2', 아니면 '초등 5학년 2학기'."""
    level = LEVELS[item["level"]]
    if short:
        return f'{level[0]}{item["grade"]}-{item["term"]}'
    return f'{level} {item["grade"]}학년 {item["term"]}학기'


def subject_of(item: dict) -> str:
    """자료의 과목 키 (slug 의 앞부분)."""
    return item["slug"].split("_", 1)[0]


# 학습자료 페이지에서는 Streamlit 기본 화면 요소를 모두 걷어내고
# 자료가 화면 전체를 쓰게 한다 (아이패드 세로·가로 모두).
_FULLSCREEN_CSS = """
<style>
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer,
[data-testid="stSidebar"], [data-testid="stSidebarNav"],
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapseButton"]
  { display: none !important; }
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"]
  { overflow: hidden !important; }
[data-testid="stMainBlockContainer"], .block-container
  { padding: 0 !important; max-width: none !important; }
[data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stElementContainer"]:has(> .stHtml),
[data-testid="stElementContainer"]:has(style) { display: none !important; }
iframe { display: block; width: 100% !important; border: 0;
         height: calc(100vh - 44px) !important; height: calc(100dvh - 44px) !important; }
.sb-bar { display: flex; align-items: center; gap: 12px; height: 44px; padding: 0 12px 0 4px;
          background: #fff; border-bottom: 1px solid #e6e4df;
          font-family: "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", sans-serif; }
.sb-bar a { display: inline-flex; align-items: center; height: 44px; padding: 0 12px; font-size: 15px;
            font-weight: 600; color: #1f2328 !important; text-decoration: none !important; white-space: nowrap; }
.sb-bar a:focus-visible { outline: 3px solid #2f6f8f; outline-offset: -3px; }
.sb-tag { flex: none; font-size: 12.5px; font-weight: 600; color: #fff; padding: 3px 10px; border-radius: 999px; }
.sb-space { flex: 1; }
.stMarkdown:has(.sb-bar), [data-testid="stMarkdownContainer"]:has(.sb-bar) { margin: 0 !important; }
</style>
"""

# 자료 화면 맨 위 막대의 '학습자료' 링크가 가는 곳.
# 항공권 앱에서는 목록이 /learning 이고, 학습자료 전용 앱(study_app.py)에서는 첫 화면이다.
HOME_KEY = "_study_home"


def find(slug: str) -> dict:
    for item in CATALOG:
        if item["slug"] == slug:
            return item
    raise KeyError(f"CATALOG 에 없는 학습자료입니다: {slug}")


def audio_prefix(slug: str) -> str:
    """음성 파일 주소의 앞부분.

    자료는 srcdoc iframe 안에서 돌므로 'audio/x.mp3' 같은 상대 주소가
    페이지 주소 기준으로 풀린다. Streamlit 정적 파일 경로(app/static/...)로 바꿔 준다.
    앞에 '/'를 붙이지 않아야 Streamlit Cloud 처럼 하위 경로에서 돌 때도 맞게 풀린다.
    """
    return f"app/static/learning/{slug}/audio/"


def load_html(slug: str) -> str:
    html = (STUDY_DIR / slug / "index.html").read_text(encoding="utf-8")
    prefix = audio_prefix(slug)
    return html.replace("'audio/", f"'{prefix}").replace('"audio/', f'"{prefix}')


# ---------------------------------------------------------------------------
# 비밀번호 (학습자료 전체)
# ---------------------------------------------------------------------------
# 비밀번호는 8144. 저장소가 공개라 글자 그대로 두지 않고 해시만 둔다.
# Secrets 에 STUDY_PASSWORD 를 넣으면 그 값이 대신 비밀번호가 된다.
_PW_HASH = "0c94f7a7a7d4e9306eebeb16207d59c3b7f4c5d731b453c3193ae5d29e8bd40f"  # sha256("rowoon-study:" + 비밀번호)
_OK = "_study_ok"
_COOKIE = "rowoon_study"
_TOKEN_DAYS = 60  # 한 번 들어오면 이 기기에서는 약 두 달 동안 다시 묻지 않는다


def _secret(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        if name in st.secrets:
            return str(st.secrets[name]).strip()
        for k in list(st.secrets.keys()):  # [섹션] 안에 넣은 경우
            v = st.secrets[k]
            if hasattr(v, "keys") and name in v:
                return str(v[name]).strip()
    except Exception:  # noqa: BLE001 - Secrets 가 없는 로컬 실행
        pass
    return ""


def _check_pw(pw: str) -> bool:
    pw = (pw or "").strip()
    custom = _secret("STUDY_PASSWORD")
    if custom:
        return hmac.compare_digest(pw, custom)
    return hmac.compare_digest(hashlib.sha256(f"rowoon-study:{pw}".encode()).hexdigest(), _PW_HASH)


def _token(period: int) -> str:
    """접속 표(토큰). 공개 저장소에 없는 값(Gemini 키 등)으로 서명해 아무나 만들 수 없게 한다."""
    basis = "|".join([_secret("STUDY_PASSWORD") or _PW_HASH, _secret("GEMINI_API_KEY"), _secret("APP_PASSWORD")])
    return hmac.new(basis.encode(), f"rowoon-study:{period}".encode(), hashlib.sha256).hexdigest()[:24]


def _period(day: date | None = None) -> int:
    return (day or date.today()).toordinal() // _TOKEN_DAYS


def _token_ok(tok: str | None) -> bool:
    if not tok:
        return False
    now = _period()
    return any(hmac.compare_digest(str(tok), _token(now - off)) for off in (0, 1))


def tq(sep: str = "?") -> str:
    """앱 안의 HTML 링크 뒤에 붙일 접속 표 (새로 고쳐도 다시 묻지 않게)."""
    tok = st.session_state.get(_OK)
    return f"{sep}k={tok}" if isinstance(tok, str) and tok else ""


# 학습자료 전용 앱(study_app.py)에서만 비밀번호를 묻는다. 항공권 앱 안의 학습자료 페이지는 그대로 둔다.
GATE_KEY = "_study_gate"


def gate() -> None:
    """비밀번호를 넣기 전에는 자료를 보여 주지 않는다. set_page_config 다음에 부른다."""
    if not st.session_state.get(GATE_KEY):
        return
    tok = st.session_state.get(_OK)
    if not tok:
        for cand in (st.query_params.get("k"), _cookie()):
            if _token_ok(cand):
                tok = cand
                break
    if tok:
        st.session_state[_OK] = tok
        if st.query_params.get("k") != tok:
            try:
                st.query_params["k"] = tok
            except Exception:  # noqa: BLE001
                pass
        return
    _login()
    st.stop()


def _cookie() -> str:
    try:
        return st.context.cookies.get(_COOKIE, "") or ""
    except Exception:  # noqa: BLE001 - 구버전
        return ""


def _login() -> None:
    st.markdown(
        """
<style>
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer,
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
.stApp { background: #f7f6f3; }
.stApp, .stApp input, .stApp button { font-family: "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", sans-serif !important; }
[data-testid="stMainBlockContainer"], .block-container { max-width: 400px !important; padding: 16vh 16px 40px !important; }
.lg-mark { display: grid; place-items: center; width: 52px; height: 52px; margin: 0 auto 14px; border-radius: 14px;
           background: #1f2328; color: #fff; font-weight: 800; font-size: 20px; }
.lg-t { text-align: center; font-size: 22px; font-weight: 800; color: #1f2328; }
.lg-s { text-align: center; font-size: 14px; color: #646870; margin: 6px 0 18px; }
.stApp input { background: #fff !important; color: #1f2328 !important; font-size: 20px !important; letter-spacing: .3em; text-align: center; }
.stFormSubmitButton button { min-height: 48px; border-radius: 999px !important; background: #1f2328 !important; border-color: #1f2328 !important; }
.stFormSubmitButton button, .stFormSubmitButton button * { color: #fff !important; font-weight: 800 !important; font-size: 16px !important; }
[data-testid="stElementContainer"]:has(iframe[height="0"]) { display: none !important; }
</style>
<div class="lg-mark">로</div><div class="lg-t">로운 학습자료실</div>
<div class="lg-s">비밀번호를 넣어 주세요.</div>
""",
        unsafe_allow_html=True,
    )
    with st.form("study_login", border=False):
        pw = st.text_input("비밀번호", type="password", label_visibility="collapsed", placeholder="비밀번호",
                           max_chars=20)
        ok = st.form_submit_button("들어가기", type="primary", use_container_width=True)
    if not ok:
        return
    if not _check_pw(pw):
        st.error("비밀번호가 맞지 않아요.")
        return
    tok = _token(_period())
    st.session_state[_OK] = tok
    st.query_params["k"] = tok  # 항공권 앱의 ?t= 와 겹치지 않게 k 를 쓴다
    # 이 기기에 접속 표를 쿠키로 남긴다 (아이패드 홈 화면 앱에서도 다시 묻지 않게).
    # 쿠키가 저장된 뒤 화면을 다시 불러오면 자료가 열린다.
    days = _TOKEN_DAYS
    components.html(
        "<script>try{var d=window.parent.document;"
        f"d.cookie={json.dumps(f'{_COOKIE}={tok}; path=/; max-age={days * 86400}; SameSite=Lax')}"
        "+(location.protocol==='https:'?'; Secure':'');}catch(e){}"
        "setTimeout(function(){try{window.parent.location.reload();}catch(e){}},150);</script>",
        height=0,
    )
    st.markdown('<div class="lg-s">들어가는 중이에요…</div>', unsafe_allow_html=True)
    if st.button("화면이 그대로면 여기를 눌러 주세요", use_container_width=True):
        st.rerun()


def show(slug: str) -> None:
    """학습자료 한 개를 화면 가득 보여 준다."""
    item = find(slug)
    st.set_page_config(
        page_title=item["title"],
        page_icon="📘",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    gate()
    st.markdown(_FULLSCREEN_CSS, unsafe_allow_html=True)
    subj = SUBJECTS[subject_of(item)]
    home = st.session_state.get(HOME_KEY, "learning") + tq()
    st.markdown(
        # 자료 제목은 자료 안에 이미 있으므로 막대에는 돌아가기 링크와 과목만 둔다.
        f'<div class="sb-bar"><a href="{home}" target="_self">&lsaquo; 학습자료 목록</a><span class="sb-space"></span>'
        f'<span class="sb-tag" style="background:{subj["color"]}">{escape(subj["name"])} · {escape(grade_label(item, short=True))}</span></div>',
        unsafe_allow_html=True,
    )
    components.html(load_html(slug), height=860, scrolling=False)
