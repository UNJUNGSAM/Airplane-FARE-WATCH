"""학습자료 페이지 - 주소 /learning_korean_essay  (독서논술 첨삭 교실)

다른 자료와 달리 고정된 HTML 이 아니라, 보호자가 올린 독후감 사진을 Gemini 가 읽고
그때그때 첨삭 수업을 만든다. 학생 이름은 '로운'으로 고정, 책 제목·글 제목은 사진에서 읽는다.
    첫 화면     사진 올리기 + 지난 수업 목록
    수업 화면   ?c=<수업 번호>  static/learning/korean_essay/lesson.html 에 결과를 넣어 전체 화면으로 보여 준다.
엔진은 essay_coach.py, 음성은 뒤에서 만들어 static/essay_voice/<수업 번호>/ 에 쓴다.
오래 두는 수업은 essay_store.py (암호화해서 저장소 streamlit_app/essay_store/ 에 보관).
    - 클로드 채팅방에 올린 사진: tools/essay_inbox/send.py → GitHub Actions(essay.yml)가 만들어 보관
    - 이 화면에서 올린 사진: Secrets 에 GITHUB_TOKEN 이 있으면 음성까지 만든 뒤 보관함에 올린다
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
import essay_store  # noqa: E402

importlib.reload(essay_store)

NAME = "로운"  # 학생 이름 고정 (보호자 요청)
GRADE = "초등 5학년"

SLUG = "korean_essay"
ITEM = study_page.find(SLUG)
SUBJ = study_page.SUBJECTS[study_page.subject_of(ITEM)]
KST = timezone(timedelta(hours=9))
TEMPLATE = study_page.STUDY_DIR / SLUG / "lesson.html"

st.set_page_config(page_title=ITEM["title"], page_icon="📘", layout="wide",
                   initial_sidebar_state="collapsed")
study_page.gate()
T = study_page.tq("&")
home = st.session_state.get(study_page.HOME_KEY, "learning") + study_page.tq()


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
        if not saved and essay_store.restore(lid):  # 보관함에 있는 수업이면 풀어서 연다
            saved = essay_coach.load_lesson(lid)
    except ValueError:
        saved = None
    if saved:
        st.markdown(study_page._FULLSCREEN_CSS, unsafe_allow_html=True)
        # 휴대폰에서는 막대에 링크가 둘이라 과목 표시를 숨겨 가로로 넘치지 않게 한다
        st.markdown("<style>@media (max-width:520px){.sb-tag{display:none}} .sb-bar{overflow:hidden}</style>",
                    unsafe_allow_html=True)
        st.markdown(top_bar(f'<a href="learning_{SLUG}{study_page.tq()}" target="_self">수업 목록</a>'),
                    unsafe_allow_html=True)
        # 만들다 멈춘 음성이 있으면 이어서. 다 만들면 보관함에 올린다(가능할 때).
        keep = essay_store.upload if (essay_store.can_upload() and not essay_store.has(lid)) else None
        essay_coach.start_voice(lid, saved["lesson"], on_done=keep)
        if keep and essay_coach.voice_done(lid, saved["lesson"]):
            try:
                essay_store.upload(lid)
            except Exception as e:  # noqa: BLE001
                print(f"[essay] 보관 실패 {lid[:6]}: {e}")
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
.stButton button[kind="primary"], .stButton button[kind="primary"] * { color: #fff !important; }
[data-testid="stFileUploaderDropzone"] { background: #fff; border-radius: 14px; }
/* 기기가 어두운 화면이어도 밝은 공책 느낌으로 */
.stApp, .stApp label, .stApp p, .stApp li, .stApp summary, .stApp [data-testid="stMarkdownContainer"] { color: #1f2328; }
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div { background: #fff !important; color: #1f2328 !important; }
[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploaderDropzone"] * { color: #1f2328; }
[data-testid="stExpander"] details { background: #fff; border-radius: 14px; }
.ec-h2 { display: flex; align-items: baseline; gap: 8px; margin: 26px 0 8px; font-size: 1.15rem; font-weight: 800; color: #1f2328; }
.ec-h2 .n { font-size: .85rem; font-weight: 600; color: #5c6370; }
.ec-list { display: grid; gap: 8px; }
.ec-item { display: grid; grid-template-columns: 4.2em minmax(0, 1fr) auto; gap: 12px; align-items: center;
           background: #fff; border: 1px solid #e3e0d8; border-radius: 14px; padding: 12px 14px;
           color: #1f2328 !important; text-decoration: none !important; }
.ec-item:hover { border-color: #a8472f; }
.ec-item:focus-visible { outline: 3px solid #a8472f; outline-offset: 2px; }
.ec-date { font-size: .8rem; font-weight: 700; color: #a8472f; line-height: 1.3; text-align: center; }
.ec-date b { display: block; font-size: 1.25rem; color: #1f2328; }
.ec-book { font-weight: 800; font-size: 1.02rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ec-sub { font-size: .86rem; color: #5c6370; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ec-go { font-size: .86rem; font-weight: 700; color: #a8472f; white-space: nowrap; }
.ec-tmp { font-size: .72rem; font-weight: 700; color: #8a6d1f; background: #f7eecf; padding: 1px 7px; border-radius: 999px; margin-left: 6px; }
.ec-empty { color: #5c6370; font-size: .95rem; padding: 6px 2px; }
</style>
""",
    unsafe_allow_html=True,
)
st.markdown(top_bar(), unsafe_allow_html=True)
st.markdown(
    f"""
<div class="ec-hero">
  <span class="ec-eyebrow">국어 · 독서논술 · 첨삭 수업</span>
  <h1>독서논술 첨삭 교실</h1>
  <p class="ec-lead">{NAME}이의 독후감 사진만 올리면 독서논술 선생님이 글을 꼼꼼히 읽고 1대1 첨삭 수업을 만들어요.
  책 제목과 글 제목은 사진에서 알아서 읽어요. 만든 수업은 아래 <b>지난 수업</b>에 쌓여 언제든 다시 볼 수 있어요.</p>
  <ol class="ec-route"><li>원문 판독</li><li>진단 평가표</li><li>강점</li><li>처방 (구성·문체·어휘·맞춤법)</li>
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
with st.expander("필요할 때만: 책 제목 · 학년 · 글 직접 입력"):
    book = st.text_input("책 제목 (비워 두면 사진에서 읽어요)", placeholder="예: 마당을 나온 암탉")
    grade = st.selectbox("학년", essay_coach.GRADES, index=essay_coach.GRADES.index(GRADE))
    typed = st.text_area("독후감 글 (사진 판독이 틀릴 때, 쓴 그대로 입력)", height=200)

go = st.button("첨삭 수업 만들기", type="primary", use_container_width=True)
st.markdown(
    '<p class="ec-note">사진 팁: 밝은 곳에서 그림자 없이, 공책 한 쪽이 화면에 꽉 차게 찍으면 판독이 정확해요. '
    '첨삭에 1분쯤 걸리고, 수업 화면이 열린 뒤에도 선생님 목소리는 장마다 차례로 준비돼요. 올린 사진은 첨삭에만 쓰고 저장하지 않아요.</p>',
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
        box.write("글씨를 판독하고 첨삭 내용을 정리하는 중이에요. 1분쯤 걸려요.")
        try:
            result = essay_coach.analyze(images, typed or "", book.strip(), grade, NAME)
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
        "lesson": result, "grade": grade, "name": NAME,
        "book": book.strip() or result.get("book_title", ""),
        "created": datetime.now(KST).isoformat(timespec="minutes"),
    })
    essay_coach.start_voice(new, result, on_done=essay_store.upload if essay_store.can_upload() else None)
    st.query_params["c"] = new
    st.rerun()


# ---------------------------------------------------------------------------
# 지난 수업 목록
# ---------------------------------------------------------------------------
def _local_lessons() -> list[dict]:
    """이 서버에만 잠깐 있는 수업 (보관함에 아직 없는 것)."""
    out = []
    if not essay_coach.VOICE_DIR.exists():
        return out
    for d in essay_coach.VOICE_DIR.iterdir():
        if d.is_dir() and not essay_store.has(d.name):
            saved = essay_coach.load_lesson(d.name) if essay_coach._ID_RE.match(d.name) else None
            if saved:
                out.append({"id": d.name, "temp": True, **essay_store.meta_of(saved)})
    return out


def _row(m: dict) -> str:
    try:
        when = datetime.fromisoformat(m.get("created", ""))
        date_html = f'{when.year}.<b>{when.month}.{when.day}</b>'
    except ValueError:
        date_html = "<b>-</b>"
    book = m.get("book") or "책 제목 없음"
    sub = " · ".join(x for x in (f'「{m["title"]}」' if m.get("title") else "", m.get("focus", "")) if x)
    tmp = '<span class="ec-tmp" title="이 사이트를 다시 시작하면 사라질 수 있어요">임시</span>' if m.get("temp") else ""
    return (
        f'<a class="ec-item" href="learning_{SLUG}?c={escape(m["id"])}{T}" target="_self">'
        f'<span class="ec-date">{date_html}</span>'
        f'<span style="min-width:0"><div class="ec-book">{escape(book)}{tmp}</div>'
        f'<div class="ec-sub">{escape(sub)}</div></span><span class="ec-go">수업 보기 &rsaquo;</span></a>'
    )


lessons = sorted(essay_store.list_saved() + _local_lessons(), key=lambda m: m.get("created", ""), reverse=True)
rows = "".join(_row(m) for m in lessons) or '<p class="ec-empty">아직 만든 수업이 없어요. 위에 사진을 올려 첫 수업을 만들어 보세요.</p>'
st.markdown(f'<div class="ec-h2">지난 수업 <span class="n">{len(lessons)}개</span></div><div class="ec-list">{rows}</div>',
            unsafe_allow_html=True)
if any(m.get("temp") for m in lessons):
    st.markdown(
        '<p class="ec-note"><b>임시</b> 표시 수업은 이 사이트가 다시 시작되면 사라질 수 있어요. '
        '클로드 프로젝트 채팅방에 사진을 올려 만든 수업은 사라지지 않고 계속 남아요.</p>',
        unsafe_allow_html=True,
    )
