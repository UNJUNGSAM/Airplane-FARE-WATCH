"""학습자료 목록 페이지 - 주소 /study."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

import study_page  # noqa: E402

st.set_page_config(page_title="학습자료", page_icon="📘", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(
    "<style>header[data-testid='stHeader'],[data-testid='stToolbar'],"
    "[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
    "#MainMenu,footer{display:none!important}</style>",
    unsafe_allow_html=True,
)

st.title("📘 학습자료")
st.caption("보고 싶은 자료를 눌러 주세요. 아이패드에서는 가로로 보면 더 넓게 볼 수 있어요.")

pages = {p.stem.split("_study_", 1)[-1]: p for p in Path(__file__).parent.glob("*_study_*.py")}
for item in study_page.CATALOG:
    page = pages.get(item["slug"])
    if page is None:
        continue
    with st.container(border=True):
        st.page_link(f"pages/{page.name}", label=f"**{item['title']}**", icon="👉")
        st.caption(f"{item['subject']} · {item['desc']}")
