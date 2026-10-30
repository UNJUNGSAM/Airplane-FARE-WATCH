"""학습자료 페이지 공통 코드.

항공권 감시 콘솔과는 별개다. shared(감시 콘솔)를 임포트하지 않으므로
비밀번호 없이 누구나 열 수 있고, 감시 콘솔 코드가 바뀌어도 영향을 받지 않는다.

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

from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

STUDY_DIR = Path(__file__).resolve().parent / "static" / "learning"

# 과목 카테고리. 목록 화면의 과목 메뉴가 이 순서로 나온다 (자료가 있는 과목만 보인다).
# color 는 과목별 표지 색 (차분한 톤).
SUBJECTS: dict[str, dict[str, str]] = {
    "korean": {"name": "국어", "color": "#b5523b"},
    "math": {"name": "수학", "color": "#3f5f9e"},
    "social": {"name": "사회", "color": "#2d6a5a"},
    "science": {"name": "과학", "color": "#2f6f8f"},
    "english": {"name": "영어", "color": "#6a4c93"},
    "music": {"name": "음악", "color": "#9a5a7a"},
    "art": {"name": "미술", "color": "#a8722a"},
    "pe": {"name": "체육", "color": "#4f7a3a"},
    "ethics": {"name": "도덕", "color": "#7a6248"},
    "practical": {"name": "실과", "color": "#5d6b4a"},
}

# 목록 페이지에 보이는 순서대로 적는다. 과목은 slug 앞부분(과목_주제)에서 정해진다.
#   grade   학년 (예: "5학년", 모르면 "초등")
#   unit    교과서 단원 이름
#   desc    다루는 내용 한 줄
#   slides  화면 장 수, minutes 해설 음성 길이(분, 대략)
CATALOG: list[dict] = [
    {
        "slug": "science_heat",
        "title": "열 탐구 노트",
        "grade": "5학년",
        "unit": "3. 열과 우리 생활",
        "desc": "온도와 온도계, 열의 이동, 전도·대류·단열을 생활 속 예로 익혀요.",
        "slides": 18,
        "minutes": 10,
    },
    {
        "slug": "social_goryeo",
        "title": "고려 문화 탐험노트",
        "grade": "초등",
        "unit": "고려의 문화",
        "desc": "고려청자, 팔만대장경, 직지, 불교문화, 벽란도, 생활 모습을 살펴봐요.",
        "slides": 18,
        "minutes": 13,
    },
]


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


def show(slug: str) -> None:
    """학습자료 한 개를 화면 가득 보여 준다."""
    item = find(slug)
    st.set_page_config(
        page_title=item["title"],
        page_icon="📘",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(_FULLSCREEN_CSS, unsafe_allow_html=True)
    subj = SUBJECTS[subject_of(item)]
    home = st.session_state.get(HOME_KEY, "learning")
    st.markdown(
        # 자료 제목은 자료 안에 이미 있으므로 막대에는 돌아가기 링크와 과목만 둔다.
        f'<div class="sb-bar"><a href="{home}" target="_self">&lsaquo; 학습자료 목록</a><span class="sb-space"></span>'
        f'<span class="sb-tag" style="background:{subj["color"]}">{escape(subj["name"])} · {escape(item["grade"])}</span></div>',
        unsafe_allow_html=True,
    )
    components.html(load_html(slug), height=860, scrolling=False)
