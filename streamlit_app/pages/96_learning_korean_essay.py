"""학습자료 페이지 - 주소 /learning_korean_essay  (독서논술 첨삭 교실)

다른 자료와 달리 고정된 HTML 이 아니라, 보호자가 올린 독후감 사진을 Gemini 가 읽고
그때그때 첨삭 수업을 만든다.
    첫 화면     사진 올리기 (또는 글 입력)
    수업 화면   ?c=<수업 번호>  static/learning/korean_essay/lesson.html 에 결과를 넣어 전체 화면으로 보여 준다.
엔진은 essay_coach.py, 음성은 뒤에서 만들어 static/essay_voice/<수업 번호>/ 에 쓴다.
"""
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib  # noqa: E402
import json  # noqa: E402

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

import study_page  # noqa: E402

importlib.reload(study_page)
# essay_coach 는 다시 읽지 않는다. 뒤에서 도는 음성 작업(스레드)의 상태를 모듈이 기억하기 때문.
import essay_coach  # noqa: E402

SLUG = "korean_essay"
ITEM = study_page.find(SLUG)
SUBJ = study_page.SUBJECTS[study_page.subject_of(ITEM)]
KST = timezone(timedelta(hours=9))
TEMPLATE = study_page.STUDY_DIR / SLUG / "lesson.html"

st.set_page_config(page_title=ITEM["title"], page_icon="📘", layout="wide",
                   initial_sidebar_state="collapsed")
home = st.session_state.get(study_page.HOME_KEY, "learning")


def top_bar(extra: str = "") -> str:
    return (
        f'<div class="sb-bar"><a href="{home}" target="_self">&lsaquo; 학습자료 목록</a>{extra}'
        f'<span class="sb-space"></span><span class="sb-tag" style="background:{SUBJ["color"]}">'
        f'{escape(SUBJ["name"])} · 독서논술 · 초5 이상</span></div>'
    )


# ---------------------------------------------------------------------------
# 수업 화면
# ---------------------------------------------------------------------------
lid = st.query_params.get("c", "")
if lid:
    try:
        saved = essay_coach.load_lesson(lid)
    except ValueError:
        saved = None
    if saved:
        st.markdown(study_page._FULLSCREEN_CSS, unsafe_allow_html=True)
        st.markdown(top_bar(f'<a href="learning_{SLUG}" target="_self">새 글 첨삭</a>'), unsafe_allow_html=True)
        essay_coach.start_voice(lid, saved["lesson"])  # 만들다 멈춘 음성이 있으면 이어서
        payload = {"lesson": saved["lesson"],
                   "meta": {"id": lid, "base": f"{essay_coach.VOICE_URL}{lid}/", "audio": {},
                            "grade": saved.get("grade", ""), "name": saved.get("name", ""),
                            "book": saved.get("book", ""), "created": saved.get("created", "")}}
        data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
        components.html(TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/", data),
                        height=860, scrolling=False)
        st.stop()
    # 수업 기록이 없으면(사이트를 다시 시작하면 지워진다) 첫 화면으로
    st.query_params.clear()


# ---------------------------------------------------------------------------
# 첫 화면 (사진 올리기)
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer,
[data-testid="stSidebar"], [data-testid="stSidebarNav"], [data-testid="stSidebarCollapsedControl"]
  { display: none !important; }
.stApp { background: #f6f4ef; }
html, body, .stApp, [data-testid="stMarkdownContainer"], .stButton button, input, textarea, label, select
  { font-family: "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", sans-serif !important; }
[data-testid="stMainBlockContainer"], .block-container { max-width: 820px !important; padding: 0 16px 48px !important; }
[data-testid="stElementContainer"]:has(style) { display: none !important; }
.sb-bar { display: flex; align-items: center; gap: 12px; height: 44px; margin: 0 -16px 8px; padding: 0 12px 0 4px;
          background: #fff; border-bottom: 1px solid #e6e4df; }
.sb-bar a { display: inline-flex; align-items: center; height: 44px; padding: 0 12px; font-size: 15px; font-weight: 600;
            color: #1f2328 !important; text-decoration: none !important; white-space: nowrap; }
.sb-tag { flex: none; font-size: 12.5px; font-weight: 600; color: #fff; padding: 3px 10px; border-radius: 999px; }
.sb-space { flex: 1; }
.ec-hero { display: grid; gap: 10px; padding: 18px 0 6px; }
.ec-eyebrow { font-size: .82rem; font-weight: 800; letter-spacing: .06em; color: #a8472f; }
.ec-hero h1 { font-size: clamp(1.9rem, 5vw, 2.6rem); font-weight: 800; line-height: 1.2; margin: 0; color: #1f2328; }
.ec-lead { color: #5c6370; font-size: 1.02rem; line-height: 1.7; margin: 0; }
.ec-route { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 0; padding: 0; list-style: none; counter-reset: r; }
.ec-route li { font-size: .85rem; padding: 3px 10px; border: 1px solid #e3e0d8; border-radius: 999px; color: #5c6370; background: #fff; }
.ec-route li::before { counter-increment: r; content: counter(r) " "; font-weight: 800; color: #a8472f; }
.ec-card { background: #fff; border: 1px solid #e3e0d8; border-radius: 16px; padding: 14px 18px; margin: 10px 0; color: #1f2328; line-height: 1.65; }
.ec-card b { font-weight: 800; }
.ec-card ol, .ec-card ul { margin: 6px 0 0; padding-left: 1.3em; }
.ec-warn { border-left: 5px solid #a8472f; background: #f6e8e2; }
.ec-note { font-size: .86rem; color: #5c6370; line-height: 1.6; }
.stButton button[kind="primary"] { background: #a8472f !important; border-color: #a8472f !important; border-radius: 999px !important;
  min-height: 52px; font-weight: 800 !important; font-size: 1.05rem !important; }
[data-testid="stFileUploaderDropzone"] { background: #fff; border-radius: 14px; }
/* 기기가 어두운 화면이어도 밝은 공책 느낌으로 */
.stApp, .stApp label, .stApp p, .stApp li, .stApp summary, .stApp [data-testid="stMarkdownContainer"] { color: #1f2328; }
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div { background: #fff !important; color: #1f2328 !important; }
[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploaderDropzone"] * { color: #1f2328; }
[data-testid="stExpander"] details { background: #fff; border-radius: 14px; }
</style>
""",
    unsafe_allow_html=True,
)
st.markdown(top_bar(), unsafe_allow_html=True)
st.markdown(
    """
<div class="ec-hero">
  <span class="ec-eyebrow">국어 · 독서논술 · 첨삭 수업</span>
  <h1>독서논술 첨삭 교실</h1>
  <p class="ec-lead">독후감 사진을 올리면 독서논술 선생님이 글을 꼼꼼히 읽고 1대1 첨삭 수업을 합니다.
  잘한 점은 근거를 들어 짧게, 고칠 점은 이유와 방법까지 분명하게 짚어요.
  마지막에는 같은 책으로 쓴 <b>추천 독서록 두 편</b>을 성우 선생님 목소리로 함께 읽습니다.</p>
  <ol class="ec-route"><li>원문 판독</li><li>진단 평가표</li><li>강점 2가지</li><li>처방 (구성·문체·어휘·맞춤법)</li>
  <li>고쳐 쓰기 연습</li><li>생각 질문</li><li>완성본</li><li>추천 독서록</li><li>다시 쓰기</li></ol>
</div>
""",
    unsafe_allow_html=True,
)

if not essay_coach.api_key():
    st.markdown(
        """
<div class="ec-card ec-warn"><b>보호자 확인: 이 사이트에 Gemini 키가 아직 연결되지 않았어요.</b>
<ol><li>share.streamlit.io 에서 이 학습자료 앱의 <b>⋮ → Settings → Secrets</b> 를 엽니다.</li>
<li>항공권 앱의 Secrets 에 있는 <code>GEMINI_API_KEY = "..."</code> 한 줄을 그대로 복사해 붙여 넣고 저장합니다.</li>
<li>1분쯤 뒤 이 화면을 새로 고치면 바로 쓸 수 있어요.</li></ol></div>
""",
        unsafe_allow_html=True,
    )

photos = st.file_uploader(
    "독후감 사진 (여러 장이면 순서대로 모두 올려 주세요)",
    type=["jpg", "jpeg", "png", "webp", "heic", "heif"],
    accept_multiple_files=True,
)
st.markdown(
    '<p class="ec-note">사진 팁: 밝은 곳에서 그림자 없이, 공책 한 쪽이 화면에 꽉 차게 찍으면 판독이 정확해요.</p>',
    unsafe_allow_html=True,
)
c1, c2 = st.columns(2)
with c1:
    book = st.text_input("책 제목 (선택)", placeholder="예: 마당을 나온 암탉")
with c2:
    grade = st.selectbox("학년", essay_coach.GRADES, index=2)
name = st.text_input("학생 이름 (선택, 선생님이 이름을 불러 줘요)", max_chars=10)
with st.expander("사진 대신 글을 직접 입력하기"):
    typed = st.text_area("독후감 글 (쓴 그대로, 맞춤법을 고치지 말고 입력해 주세요)", height=220)

go = st.button("첨삭 수업 시작", type="primary", use_container_width=True)
st.markdown(
    '<p class="ec-note">첨삭에 1~2분쯤 걸려요. 수업 화면이 열린 뒤에도 선생님 목소리는 장마다 차례로 준비돼요.<br>'
    '올린 사진은 첨삭에만 쓰고 저장하지 않아요. 수업 기록은 이 사이트에 며칠만 남으니, 오래 두려면 수업 화면의 <b>수업 저장</b>을 눌러 파일로 받아 두세요.</p>',
    unsafe_allow_html=True,
)

if go:
    if not essay_coach.api_key():
        st.error("Gemini 키가 연결되지 않아 첨삭을 할 수 없어요. 위의 안내대로 키를 넣어 주세요.")
        st.stop()
    if not photos and not (typed or "").strip():
        st.warning("독후감 사진을 올리거나, 글을 직접 입력해 주세요.")
        st.stop()
    with st.status("선생님이 글을 읽고 있어요", expanded=True) as box:
        images = []
        for f in photos or []:
            images.append(essay_coach.prepare_image(f.getvalue(), f.type or "image/jpeg"))
        if images:
            box.write(f"사진 {len(images)}장을 정리했어요.")
        box.write("글씨를 판독하고 첨삭 내용을 정리하는 중이에요. 1~2분쯤 걸려요.")
        try:
            result = essay_coach.analyze(images, typed or "", book.strip(), grade, name.strip())
        except essay_coach.CoachError as e:
            box.update(label="첨삭을 만들지 못했어요", state="error")
            msg = str(e)
            st.error("Gemini 키가 연결되지 않았어요." if msg == "NO_KEY" else msg)
            st.stop()
        if not result.get("readable"):
            box.update(label="글을 읽지 못했어요", state="error")
            st.warning((result.get("problem") or "사진에서 독후감 글을 찾지 못했어요.")
                       + " 더 밝고 또렷한 사진으로 다시 올리거나, 글을 직접 입력해 주세요.")
            st.stop()
        box.write("첨삭이 끝났어요. 수업 화면을 열게요.")
        box.update(label="첨삭 완료", state="complete")
    essay_coach.cleanup_old()
    new = essay_coach.new_id()
    essay_coach.save_lesson(new, {
        "lesson": result, "grade": grade, "name": name.strip(),
        "book": book.strip() or result.get("book_title", ""),
        "created": datetime.now(KST).isoformat(timespec="minutes"),
    })
    essay_coach.start_voice(new, result)
    st.query_params["c"] = new
    st.rerun()
