"""학습자료 목록 페이지 - 주소 /learning."""
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

import importlib  # noqa: E402

import study_page  # noqa: E402

# Streamlit Cloud는 페이지 스크립트만 다시 읽고 임포트된 모듈은 예전 것을 남겨 두므로
# (shared.py 와 같은 문제) 자료 목록이 바뀌어도 반영되도록 매번 다시 읽는다.
importlib.reload(study_page)

st.set_page_config(page_title="학습자료", page_icon=":material/menu_book:", layout="centered",
                   initial_sidebar_state="collapsed")

# 이모지 없이 글꼴·여백·카드만으로 차분하게 꾸민다 (아이패드 세로·가로 모두).
st.markdown(
    """
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css");
header[data-testid='stHeader'],[data-testid='stToolbar'],[data-testid='stSidebar'],
[data-testid='stSidebarCollapsedControl'],#MainMenu,footer{display:none!important}
.stApp{background:#f7f6f3}
[data-testid='stMainBlockContainer'],.block-container{max-width:720px;padding:56px 24px 64px!important}
.lr, .lr *{font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;box-sizing:border-box;word-break:keep-all}
.lr-head{margin:0 0 28px}
.lr-head h1{font-size:30px;font-weight:700;letter-spacing:-0.02em;color:#1f2328;margin:0 0 8px;padding:0}
.lr-head p{font-size:15px;color:#6b6f76;margin:0;line-height:1.6}
.lr-list{display:flex;flex-direction:column;gap:12px}
a.lr-card{display:flex;align-items:center;gap:16px;padding:20px 22px;background:#fff;
  border:1px solid #e6e4df;border-radius:14px;text-decoration:none!important;color:inherit!important;
  transition:border-color .15s,box-shadow .15s,transform .15s}
a.lr-card:hover{border-color:#cfcbc2;box-shadow:0 4px 16px rgba(0,0,0,.05);transform:translateY(-1px)}
.lr-body{flex:1;min-width:0}
.lr-sub{display:inline-block;font-size:12.5px;font-weight:600;color:#5b6b7a;background:#eef1f4;
  padding:3px 9px;border-radius:999px;margin-bottom:8px}
.lr-title{font-size:19px;font-weight:700;color:#1f2328;letter-spacing:-0.01em;margin-bottom:4px}
.lr-desc{font-size:14.5px;color:#6b6f76;line-height:1.55}
.lr-arrow{flex:none;color:#b3afa6;font-size:22px;line-height:1}
@media (max-width:600px){
  [data-testid='stMainBlockContainer'],.block-container{padding:32px 16px 48px!important}
  .lr-head h1{font-size:26px}
}
</style>
""",
    unsafe_allow_html=True,
)

pages = {p.stem.split("_learning_", 1)[-1] for p in Path(__file__).parent.glob("*_learning_*.py")}
cards = "".join(
    f'<a class="lr-card" href="learning_{escape(item["slug"])}" target="_self">'
    f'<div class="lr-body"><span class="lr-sub">{escape(item["subject"])}</span>'
    f'<div class="lr-title">{escape(item["title"])}</div>'
    f'<div class="lr-desc">{escape(item["desc"])}</div></div>'
    f'<span class="lr-arrow">&rsaquo;</span></a>'
    for item in study_page.CATALOG
    if item["slug"] in pages
)
st.markdown(
    '<div class="lr"><div class="lr-head"><h1>학습자료</h1>'
    "<p>보고 싶은 자료를 눌러 주세요. 아이패드는 가로로 보면 더 넓게 볼 수 있어요.</p></div>"
    f'<div class="lr-list">{cards}</div></div>',
    unsafe_allow_html=True,
)
