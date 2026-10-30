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

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

STUDY_DIR = Path(__file__).resolve().parent / "static" / "learning"

# 목록 페이지(/learning)에 보이는 순서대로 적는다.
CATALOG: list[dict[str, str]] = [
    {
        "slug": "science_heat",
        "title": "열 탐구 노트",
        "subject": "초5 과학",
        "desc": "3. 열과 우리 생활 · 온도, 온도계, 열의 이동, 전도·대류·단열",
    },
    {
        "slug": "social_goryeo",
        "title": "고려 문화 탐험노트",
        "subject": "초등 사회",
        "desc": "고려청자, 팔만대장경, 직지, 불교문화, 벽란도, 생활 모습",
    },
]

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
         height: 100vh !important; height: 100dvh !important; }
</style>
"""


def find(slug: str) -> dict[str, str]:
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
    components.html(load_html(slug), height=900, scrolling=False)
