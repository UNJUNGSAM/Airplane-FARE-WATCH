"""학습자료 목록 페이지 - 주소 /learning (학습자료 전용 앱에서는 첫 화면 /).

과목 메뉴를 누르면 주소 끝에 ?s=<과목> 이 붙고 그 과목 자료만 보인다.
"""
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

st.set_page_config(page_title="로운 학습자료실", page_icon=":material/menu_book:", layout="wide",
                   initial_sidebar_state="collapsed")

# 이모지 없이 글꼴·여백·카드만으로 차분하게 꾸민다.
# 크기는 모두 em 단위라서 화면 폭에 따라 .lr 글자 크기만 바꾸면 TV 에서도 비율 그대로 커진다.
st.markdown(
    """
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css");
header[data-testid='stHeader'],[data-testid='stToolbar'],[data-testid='stSidebar'],
[data-testid='stSidebarCollapsedControl'],[data-testid='stDecoration'],#MainMenu,footer{display:none!important}
.stApp{background:#f7f6f3}
[data-testid='stMainBlockContainer'],.block-container{max-width:none;padding:0!important}
.lr{--ink:#1f2328;--muted:#646870;--line:#e6e4df;--card:#fff;--soft:#efede8;--focus:#2f6f8f;
  font-size:16px;color:var(--ink);padding:0 1.5em 4em}
.lr, .lr *{font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;
  box-sizing:border-box;word-break:keep-all}
.lr a{color:inherit;text-decoration:none!important}
.lr a:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
.lr-wrap{max-width:72em;margin:0 auto}

/* 맨 위 막대 */
.lr-top{display:flex;align-items:center;justify-content:space-between;gap:1em;padding:1.25em 0;
  border-bottom:1px solid var(--line)}
.lr-brand{display:flex;align-items:center;gap:.6em;font-weight:700;font-size:1.05em;letter-spacing:-.01em}
.lr-mark{display:grid;place-items:center;width:2em;height:2em;border-radius:.55em;background:var(--ink);
  color:#fff;font-size:.85em;font-weight:800}
.lr-count{font-size:.875em;color:var(--muted)}

/* 소개 */
.lr-hero{padding:3em 0 2.25em;display:grid;grid-template-columns:minmax(0,1fr) 20em;gap:3em;align-items:end}
.lr-index{background:var(--card);border:1px solid var(--line);border-radius:1em;padding:1.1em 1.25em}
.lr-index .h{font-size:.8em;font-weight:700;color:var(--muted);margin-bottom:.6em}
.lr-index ul{list-style:none;margin:0!important;padding:0!important;display:grid;grid-template-columns:1fr 1fr;column-gap:1.25em}
.lr-index li{margin:0!important;display:flex;align-items:center;gap:.5em;padding:.4em 0;font-size:.9em;border-top:1px solid var(--soft)}
.lr-index li:nth-child(-n+2){border-top:0}
.lr-index li .dot{width:.5em;height:.5em;border-radius:50%;flex:none}
.lr-index li .c{margin-left:auto;font-size:.85em;color:var(--muted)}
.lr-index li a{display:contents}
.lr-index li a:hover{color:var(--focus)}
.lr-index li.off{color:#a3a6ab}
.lr-index li.off .dot{background:#d6d3cc!important}
.lr-eyebrow{font-size:.875em;font-weight:600;color:var(--muted);margin:0 0 .75em}
.lr-hero h1{font-size:2.4em;line-height:1.25;font-weight:750;letter-spacing:-.025em;margin:0 0 .5em;padding:0;color:var(--ink)}
.lr-hero p{font-size:1.05em;line-height:1.65;color:var(--muted);margin:0;max-width:36em}

/* 과목 메뉴: 좁은 화면에서는 메뉴만 옆으로 밀어서 본다 */
.lr-nav{position:sticky;top:0;z-index:5;background:#f7f6f3;margin:0 -1.5em;padding:.75em 1.5em;
  border-bottom:1px solid var(--line)}
.lr-tabs{display:flex;gap:.5em;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;
  max-width:72em;margin:0 auto}
.lr-tabs::-webkit-scrollbar{display:none}
a.lr-tab{flex:none;display:inline-flex;align-items:center;gap:.45em;min-height:2.75em;padding:0 1.05em;
  border-radius:999px;border:1px solid var(--line);background:var(--card);font-size:.95em;font-weight:600;
  color:#3a3e45!important;transition:background .15s,border-color .15s}
a.lr-tab:hover{border-color:#cfcbc2}
a.lr-tab .n{font-size:.85em;font-weight:500;color:var(--muted)}
a.lr-tab.on{background:var(--ink);border-color:var(--ink);color:#fff!important}
a.lr-tab.on .n{color:#c9ccd1}

/* 학교급 버튼 (초등 / 중학) */
.lr-lvs{flex:none;display:inline-flex;padding:.25em;border-radius:999px;background:var(--soft)}
.lr-lv{display:inline-flex;align-items:center;min-height:2.25em;padding:0 1em;border-radius:999px;
  font-size:.95em;font-weight:700;color:#3a3e45!important}
a.lr-lv.on{background:var(--card);box-shadow:0 1px 3px rgba(0,0,0,.08)}
.lr-lv.off{color:#a3a6ab!important;cursor:default}
.lr-sep{flex:none;width:1px;align-self:stretch;margin:.4em .25em;background:var(--line)}
.lr-tabs{align-items:center}

/* 과목별 묶음 */
.lr-sec{padding-top:2.5em}
.lr-sec-head{display:flex;align-items:baseline;gap:.6em;margin:0 0 1em}
.lr-sec-head .t{font-size:1.35em;font-weight:700;letter-spacing:-.015em;color:var(--ink)}
.lr-sec-head .dot{width:.6em;height:.6em;border-radius:50%;align-self:center}
.lr-sec-head .n{font-size:.9em;color:var(--muted)}
.lr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(17.5em,1fr));gap:1.25em}

/* 자료 카드 */
a.lr-card{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);
  border-radius:1em;overflow:hidden;transition:border-color .2s,box-shadow .2s,transform .2s}
a.lr-card:hover{border-color:#cfcbc2;box-shadow:0 .5em 1.5em rgba(0,0,0,.06);transform:translateY(-2px)}
.lr-cover{position:relative;aspect-ratio:16/8;padding:1.1em 1.25em;display:flex;flex-direction:column;
  justify-content:space-between;color:#fff;overflow:hidden}
.lr-cover::after{content:"";position:absolute;right:-2.5em;bottom:-3.5em;width:10em;height:10em;border-radius:50%;
  border:1.6em solid rgba(255,255,255,.10)}
.lr-cover .tag{font-size:.8em;font-weight:600;opacity:.9;letter-spacing:.01em}
.lr-cover .unit{position:relative;z-index:1;font-size:1.45em;font-weight:750;line-height:1.3;letter-spacing:-.02em}
.lr-body{flex:1;display:flex;flex-direction:column;padding:1.1em 1.25em 1.2em}
.lr-title{font-size:1.2em;font-weight:700;letter-spacing:-.015em;margin-bottom:.35em}
.lr-desc{font-size:.95em;line-height:1.6;color:var(--muted);flex:1}
.lr-meta{display:flex;align-items:center;justify-content:space-between;margin-top:1.1em;padding-top:.9em;
  border-top:1px solid var(--soft);font-size:.875em;color:var(--muted)}
.lr-go{font-weight:700;color:var(--ink)}

/* 공부하는 순서 */
.lr-how{margin-top:3.5em;padding:2em;background:var(--card);border:1px solid var(--line);border-radius:1em}
.lr-how .t{font-size:1.2em;font-weight:700;margin:0 0 1.25em;color:var(--ink)}
.lr-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:1.5em;margin:0!important;padding:0!important;list-style:none}
.lr-steps li{display:flex;gap:.9em;margin:0!important}
.lr-steps .no{flex:none;display:grid;place-items:center;width:2em;height:2em;border-radius:50%;
  background:var(--soft);font-weight:700;font-size:.9em}
.lr-steps b{display:block;font-size:1em;margin-bottom:.2em}
.lr-steps span{font-size:.9em;line-height:1.55;color:var(--muted)}
.lr-foot{margin-top:2.5em;font-size:.85em;color:#8a8d93;text-align:center}
.lr-empty{padding:3em 0;color:var(--muted)}

/* 아이패드 세로 이하: 과목 안내판은 숨기고 아래 과목 메뉴만 쓴다 */
@media (max-width:900px){.lr-hero{grid-template-columns:1fr}.lr-index{display:none}}
/* 아이폰 */
@media (max-width:600px){
  .lr{padding:0 1em 3em}
  .lr-nav{position:static;margin:0 -1em;padding:.75em 1em}
  .lr-tabs{flex-wrap:wrap;overflow:visible}
  .lr-sep{flex-basis:100%;height:0;margin:0;background:none}
  .lr-cover{aspect-ratio:16/6.5}
  .lr-hero h1{font-size:1.75em}
  .lr-hero{padding:2em 0 1.5em}
  .lr-hero p{font-size:1em}
  .lr-grid{grid-template-columns:1fr}
  .lr-steps{grid-template-columns:1fr;gap:1em}
  .lr-how{padding:1.5em}
}
/* PC 큰 화면 · TV: 전체를 비율 그대로 키운다 */
@media (min-width:1600px){.lr{font-size:18px}}
@media (min-width:1800px){.lr{font-size:21px}}
@media (min-width:2200px){.lr{font-size:24px}}
@media (min-width:3200px){.lr{font-size:34px}}
@media (prefers-reduced-motion:reduce){a.lr-card,a.lr-tab{transition:none}a.lr-card:hover{transform:none}}
</style>
""",
    unsafe_allow_html=True,
)

pages = {p.stem.split("_learning_", 1)[-1] for p in Path(__file__).parent.glob("*_learning_*.py")}
items = [item for item in study_page.CATALOG if item["slug"] in pages]

# 학교급(초등/중학)을 먼저 고르고, 그 안에서 과목을 고른다. 주소: ?l=<학교급>&s=<과목>
count_by_level = {key: sum(item["level"] == key for item in items) for key in study_page.LEVELS}
level = st.query_params.get("l", "")
if level not in study_page.LEVELS:
    level = next((key for key, n in count_by_level.items() if n), "elem")
level_items = [item for item in items if item["level"] == level]

# 자료가 있는 과목만 메뉴에 보인다 (SUBJECTS 순서대로). 과목 안에서는 학년·학기 순.
by_subject: dict[str, list[dict]] = {}
for key in study_page.SUBJECTS:
    found = [item for item in level_items if study_page.subject_of(item) == key]
    if found:
        by_subject[key] = sorted(found, key=lambda item: (item["grade"], item["term"]))

picked = st.query_params.get("s", "")
if picked not in by_subject:
    picked = ""


def card(item: dict) -> str:
    subj = study_page.SUBJECTS[study_page.subject_of(item)]
    meta = f'{item["slides"]}장 · 해설 약 {item["minutes"]}분' if item.get("slides") else ""
    return (
        f'<a class="lr-card" href="learning_{escape(item["slug"])}" target="_self">'
        f'<div class="lr-cover" style="background:{subj["color"]}">'
        f'<span class="tag">{escape(subj["name"])} · {escape(study_page.grade_label(item))}</span>'
        f'<span class="unit">{escape(item["unit"])}</span></div>'
        f'<div class="lr-body"><div class="lr-title">{escape(item["title"])}</div>'
        f'<div class="lr-desc">{escape(item["desc"])}</div>'
        f'<div class="lr-meta"><span>{meta}</span><span class="lr-go">학습 시작 &rsaquo;</span></div>'
        "</div></a>"
    )


def section(title: str, found: list[dict], color: str = "") -> str:
    dot = f'<span class="dot" style="background:{color}"></span>' if color else ""
    return (
        f'<section class="lr-sec"><div class="lr-sec-head">{dot}'
        f'<span class="t">{escape(title)}</span><span class="n">{len(found)}개</span></div>'
        f'<div class="lr-grid">{"".join(card(item) for item in found)}</div></section>'
    )


# 지금 학교급의 과목 전체를 보여 주는 안내판 (자료가 없는 과목은 '준비 중'으로 흐리게).
def index_row(key: str, subj: dict) -> str:
    dot = f'<span class="dot" style="background:{subj["color"]}"></span>'
    if key not in by_subject:
        return f'<li class="off">{dot}{escape(subj["name"])}<span class="c">준비 중</span></li>'
    return (
        f'<li><a href="?l={level}&s={key}" target="_self">{dot}{escape(subj["name"])}'
        f'<span class="c">{len(by_subject[key])}개</span></a></li>'
    )


index = "".join(
    index_row(key, subj) for key, subj in study_page.SUBJECTS.items() if level in subj["levels"]
)

# 학교급 버튼: 자료가 없는 학교급은 '준비 중'으로 흐리게 (누를 수 없음).
levels = "".join(
    f'<a class="lr-lv{" on" if key == level else ""}" href="?l={key}" target="_self">{escape(name)}</a>'
    if count_by_level[key]
    else f'<span class="lr-lv off" title="준비 중">{escape(name)}</span>'
    for key, name in study_page.LEVELS.items()
)

tabs = [("", "전체", len(level_items))] + [
    (key, study_page.SUBJECTS[key]["name"], len(found)) for key, found in by_subject.items()
]
nav = f'<div class="lr-lvs" role="group" aria-label="학교급">{levels}</div><span class="lr-sep"></span>' + "".join(
    f'<a class="lr-tab{" on" if key == picked else ""}" href="?l={level}{"&s=" + key if key else ""}" target="_self">'
    f'{escape(name)}<span class="n">{n}</span></a>'
    for key, name, n in tabs
)

level_name = study_page.LEVELS[level]
if not level_items:
    body = '<p class="lr-empty">아직 올라온 자료가 없어요.</p>'
elif picked:
    subj = study_page.SUBJECTS[picked]
    body = section(subj["name"], by_subject[picked], subj["color"])
else:
    # 전체: 과목 순서대로 한 격자에 모아 빈칸 없이 보여 준다.
    body = section(f"{level_name} 전체 자료", [item for found in by_subject.values() for item in found])

st.markdown(
    '<div class="lr">'
    '<div class="lr-wrap"><div class="lr-top">'
    '<div class="lr-brand"><span class="lr-mark">로</span>로운 학습자료실</div>'
    f'<span class="lr-count">자료 {len(items)}개</span></div>'
    '<div class="lr-hero"><div><p class="lr-eyebrow">수행평가 대비 학습자료</p>'
    "<h1>그림과 해설로<br>차근차근 익혀요</h1>"
    "<p>한 장씩 넘기며 그림을 보고, 선생님 목소리 해설을 듣고, 마지막에 연습문제로 확인해요. "
    "아이패드는 가로로 보면 더 넓게 볼 수 있어요.</p></div>"
    f'<div class="lr-index"><div class="h">{level_name} 과목별 자료</div><ul>{index}</ul></div></div></div>'
    f'<nav class="lr-nav" aria-label="과목"><div class="lr-tabs">{nav}</div></nav>'
    f'<div class="lr-wrap">{body}'
    '<div class="lr-how"><div class="t">이렇게 공부해요</div><ol class="lr-steps">'
    '<li><span class="no">1</span><div><b>자료 고르기</b><span>과목을 누르고 공부할 단원을 골라요.</span></div></li>'
    '<li><span class="no">2</span><div><b>보고 듣기</b><span>그림을 보며 해설을 듣고, 다음 장으로 넘겨요.</span></div></li>'
    '<li><span class="no">3</span><div><b>확인하기</b><span>연습문제로 배운 내용을 스스로 점검해요.</span></div></li>'
    "</ol></div>"
    '<p class="lr-foot">로운 학습자료실</p></div></div>',
    unsafe_allow_html=True,
)
