"""설정 페이지 - 연동 상태와 동작 방식 안내."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent.parent
for _p in (str(HERE), str(ROOT)):
    while _p in sys.path:  # 루트가 항상 앞서도록 재정렬
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import streamlit as st

import shared

# 실행 중인 shared 모듈이 이 페이지가 기대하는 버전인지 확인한다.
# (배포 직후 Streamlit이 페이지만 새로 읽고 모듈은 예전 것을 물고 있는 경우
#  원인 모를 AttributeError 대신 무엇을 해야 하는지 알려 준다)
_NEEDS_SHARED = "2026-08-28.2"
if getattr(shared, "SHARED_REVISION", "") < _NEEDS_SHARED:
    st.error(
        "**배포된 새 코드가 아직 적용되지 않았습니다.** "
        "**[Manage app] → [⋮] → [Reboot app]** 으로 앱을 완전히 재시작하여 주십시오."
    )
    st.stop()

shared.boot("settings", "설정")

# ---------------------------------------------------------------------------
# 브라우저 UI에서 직접 키 입력 (이번 세션에만 적용되는 임시 오버라이드)
# ---------------------------------------------------------------------------
cfg = shared.config

_ready_all = cfg.gemini_ready() and cfg.telegram_ready()
with st.expander("⚙️ 이 브라우저 세션에서만 키를 임시로 적용하기", expanded=not _ready_all):
    st.markdown(
        '<div style="font-size:13px;color:#4a5568;margin-bottom:12px;">'
        '아래 입력값은 <b>지금 이 브라우저 세션에서만</b> 사용됩니다. 창을 닫거나 앱이 재시작하면 사라지므로, '
        '상시 운영에는 Streamlit Cloud의 <b>Secrets</b> 또는 로컬 <code>.env</code>를 사용하여 주십시오. '
        '(보안상 이미 저장된 키는 이 칸에 다시 표시하지 않습니다.)</div>',
        unsafe_allow_html=True,
    )

    def _ph(key: str) -> str:
        return "이미 설정됨 - 바꿀 때만 입력" if cfg.get_secret(key) else "미설정 - 여기에 붙여넣기"

    with st.form("quick_keys_form", border=False):
        k1, k2 = st.columns(2)
        in_gemini = k1.text_input("Gemini API 키 (AIza...)", value="", type="password",
                                  placeholder=_ph("GEMINI_API_KEY"),
                                  help="https://aistudio.google.com/apikey 에서 발급받은 키")
        in_tg_tok = k2.text_input("텔레그램 봇 토큰 (123456:ABC...)", value="", type="password",
                                  placeholder=_ph("TELEGRAM_BOT_TOKEN"),
                                  help="@BotFather에게 발급받은 토큰")

        k3, k4 = st.columns(2)
        in_tg_cid = k3.text_input("텔레그램 Chat ID (숫자)", value="",
                                  placeholder=_ph("TELEGRAM_CHAT_ID"),
                                  help="getUpdates에서 확인한 숫자 ID")
        in_gh_repo = k4.text_input("GitHub 저장소 (아이디/저장소명)", value="",
                                   placeholder=_ph("GITHUB_REPO") + " (예: UNJUNGSAM/Airplane-FARE-WATCH)",
                                   help="예: UNJUNGSAM/Airplane-FARE-WATCH")

        in_gh_tok = st.text_input("GitHub Classic 토큰 (선택, ghp_...)", value="", type="password",
                                  placeholder=_ph("GITHUB_TOKEN"),
                                  help="GitHub Personal Access Token (classic, repo 권한)")

        b1, b2 = st.columns([3, 1])
        btn_save = b1.form_submit_button("💾 이 세션에 임시 적용", type="primary", width="stretch")
        btn_clear = b2.form_submit_button("임시값 해제", width="stretch")

    if btn_save:
        applied = []
        for label, key, raw in (
            ("Gemini", "GEMINI_API_KEY", in_gemini),
            ("텔레그램 토큰", "TELEGRAM_BOT_TOKEN", in_tg_tok),
            ("텔레그램 Chat ID", "TELEGRAM_CHAT_ID", in_tg_cid),
            ("GitHub 저장소", "GITHUB_REPO", in_gh_repo),
            ("GitHub 토큰", "GITHUB_TOKEN", in_gh_tok),
        ):
            if raw.strip():
                cfg.set_session_override(key, raw)
                applied.append(label)
        if applied:
            st.success("이번 세션에 적용하였습니다: " + ", ".join(applied))
            st.rerun()
        else:
            st.info("입력된 값이 없습니다.")

    if btn_clear:
        cfg.clear_session_overrides()
        st.success("세션 임시값을 모두 해제하였습니다.")
        st.rerun()

eng = shared.engine_state()

shared.page_header(
    eyebrow="Settings",
    title="연동 상태 및 동작 방식",
    desc="감시 파이프라인이 사용하는 외부 연동의 설정 여부를 확인합니다.",
    meta_label="운영 상태",
    meta_value=eng["label"],
    attached=False,
)


def status_panel(name: str, ok: bool, ok_text: str, ng_text: str, rows: list[tuple]) -> str:
    dot = "dot-ok" if ok else "dot-warn"
    badge = ("ok", ok_text) if ok else ("warn", ng_text)
    body = "".join(f'<div class="ap-kv"><span>{k}</span><b>{v}</b></div>' for k, v in rows)
    return (f'<div class="ap-panel"><div class="ap-panel-h">{name}'
            f'<span class="ap-badge {badge[0]}"><span class="ap-dot {dot}"></span>'
            f'{badge[1]}</span></div><div class="ap-panel-b">{body}</div></div>')


c1, c2, c3 = st.columns(3, gap="medium")
with c1:
    st.markdown(
        status_panel(
            "Gemini", shared.config.gemini_ready(), "연동", "미설정",
            [("모델", f'<span class="mono">{shared.config.GEMINI_MODEL}</span>'),
             ("API 키", f'<span class="mono">'
                      f'{shared.mask(shared.config.GEMINI_API_KEY)}</span>'),
             ("용도", "자연어 조건 분석 · 알림 요약")],
        ),
        unsafe_allow_html=True,
    )
    if shared.config.gemini_ready():
        if st.button("Gemini 호출 테스트", key="test_gemini", width="stretch"):
            with st.spinner("Gemini API 호출을 테스트하고 있습니다..."):
                try:
                    res = shared.get_gemini().parse_watch_query("서울 도쿄 10월 1일")
                    st.success("Gemini API 연동이 정상 작동합니다!")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Gemini 호출 실패: {exc}")

with c2:
    st.markdown(
        status_panel(
            "Telegram", shared.config.telegram_ready(), "연동", "미설정",
            [("봇 토큰", f'<span class="mono">'
                      f'{shared.mask(shared.config.TELEGRAM_BOT_TOKEN)}</span>'),
             ("Chat ID", f'<span class="mono">'
                        f'{shared.config.TELEGRAM_CHAT_ID or "미설정"}</span>'),
             ("용도", "핫딜 판정 시 즉시 알림")],
        ),
        unsafe_allow_html=True,
    )
    if shared.config.telegram_ready():
        if st.button("텔레그램 테스트 메시지 발송", key="test_telegram", type="primary", width="stretch"):
            with st.spinner("텔레그램으로 테스트 메시지를 전송하고 있습니다..."):
                ok, msg = shared.notifier.send_test_message()
            if ok:
                st.success(msg)
                st.toast("텔레그램 메시지 발송 완료!")
            else:
                st.error(msg)

with c3:
    st.markdown(
        status_panel(
            "GitHub 동기화", shared.github_sync.ready(), "연동", "로컬 모드",
            [("저장소", f'<span class="mono">'
                     f'{shared.config.GITHUB_REPO or "미설정"}</span>'),
             ("브랜치", f'<span class="mono">'
                     f'{shared.config.GITHUB_BRANCH or "-"}</span>'),
             ("토큰", f'<span class="mono">'
                    f'{shared.mask(shared.config.GITHUB_TOKEN)}</span>')],
        ),
        unsafe_allow_html=True,
    )



if not shared.github_sync.ready():
    st.info(
        "GitHub 동기화가 설정되지 않아 로컬 모드로 동작합니다. 클라우드 배포 시 조건 변경을 "
        "자동 감시에 반영하려면 저장소 토큰 설정이 필요합니다."
    )

if not shared.auth_enabled():
    st.error(
        "**접근 비밀번호가 설정되지 않았습니다.** 지금은 이 주소를 아는 누구나 감시 조건을 "
        "추가·삭제하고 텔레그램 발송까지 시킬 수 있습니다. Secrets에 "
        "`APP_PASSWORD` 를 추가하여 주십시오."
    )

with st.expander("🔍 연동 상태 진단 도우미 (클릭하여 확인)"):
    info = cfg.runtime_info()
    st.markdown("**0. 지금 실행 중인 설정 모듈:**")
    st.code(
        f"config 리비전 : {info['revision']}\n"
        f"config 파일   : {info['file']}\n"
        f"작업 디렉터리 : {info['cwd']}"
    )
    st.caption(
        "리비전이 저장소의 최신 값과 다르면 Streamlit Cloud가 예전 코드를 메모리에 물고 있는 것입니다. "
        "[Manage app] → [⋮] → [Reboot app]으로 완전히 재시작하여 주십시오."
    )

    st.markdown("**1. Streamlit Secrets에 등록된 키 목록:**")
    sec_keys = []
    try:
        if hasattr(st, "secrets") and st.secrets is not None:
            sec_keys = list(st.secrets.keys())
    except Exception as e:  # noqa: BLE001
        sec_keys = [f"조회 에러: {e}"]

    if not sec_keys:
        st.warning(
            "현재 Streamlit Secrets가 비어 있습니다. [Manage app] → [⋮] → [Settings] → "
            "[Secrets]에 입력 후 [Save]를 눌러주세요."
        )
    elif shared.auth_enabled():
        # 비밀번호로 보호된 상태에서만 키 이름을 그대로 보여준다
        st.success(f"현재 인식된 Secrets 키 목록: `{', '.join(str(k) for k in sec_keys)}`")
    else:
        st.info(f"Secrets {len(sec_keys)}개를 인식하였습니다. "
                "키 이름은 비밀번호(APP_PASSWORD) 설정 후에 표시합니다.")

    st.markdown("**2. 각 항목별 실제 감지 여부와 출처:**")
    lines = []
    for key, optional in (
        ("GEMINI_API_KEY", False),
        ("GEMINI_MODEL", True),
        ("TELEGRAM_BOT_TOKEN", False),
        ("TELEGRAM_CHAT_ID", False),
        ("GITHUB_REPO", True),
        ("GITHUB_TOKEN", True),
        ("APP_PASSWORD", True),
    ):
        val = cfg.get_secret(key)
        if val:
            # 모델명은 비밀이 아니라 그대로, Chat ID도 식별을 위해 그대로 보여준다
            shown = str(val) if key in ("TELEGRAM_CHAT_ID", "GEMINI_MODEL") else shared.mask(val)
            lines.append(f"• {key}: 연동 완료 ({shown}) ← {cfg.secret_source(key)}")
        else:
            default = shared.config_default(key)
            if default:
                lines.append(f"• {key}: 미설정 - 기본값 사용 ({default})")
            else:
                lines.append(f"• {key}: {'미설정 (선택)' if optional else '미인식 (None)'}")
    st.code("\n".join(lines))


# ---------------------------------------------------------------------------
shared.section("동작 방식")

steps = [
    ("01", "자동 수집",
     f"GitHub Actions가 {shared.CHECK_INTERVAL_TEXT}마다 monitor.py를 실행하여 "
     "모든 감시 조건의 구글 항공권 최저가와 상위 항공편을 기록합니다."),
    ("02", "판정",
     "규칙 엔진이 목표가 도달·첫 관측가 대비 하락·하위 백분위 세 가지를 검사합니다."),
    ("03", "알림",
     "하나라도 충족하면 텔레그램으로 즉시 발송하고 알림 기록에 남깁니다."),
    ("04", "반영",
     "갱신된 DB는 저장소에 커밋되며, 콘솔에서 조건을 변경하면 다음 주기부터 적용합니다."),
]
st.markdown(
    '<div class="ap-panel">'
    + "".join(
        f'<div class="ap-row" style="grid-template-columns:56px 150px minmax(0,1fr);">'
        f'<div class="ap-rank">{no}</div>'
        f'<div style="font-size:13.5px;font-weight:600;color:#131b30;">{title}</div>'
        f'<div class="ap-sub" style="margin-top:0;">{body}</div></div>'
        for no, title, body in steps
    )
    + "</div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
shared.section("구글 항공권 가격 추적과의 차이")

compare = [
    ("추적 단위", "노선 1개 · 날짜 1개", "여러 목적지와 시간대 조합을 동시에"),
    ("시간대 필터", "미지원", "지원 (예: 20시 이후, 오전 출발)"),
    ("경유 필터", "지원", "지원 (직항만 · 1회 경유까지)"),
    ("가격 기록", "제공사 기준", "조건별 전용 이력 (차트 · 할인율)"),
    ("판정 기준", "제공사 기준", "목표가 · 하락률 · 백분위 직접 설정"),
    ("알림 수단", "이메일", "텔레그램 즉시 발송"),
]
st.markdown(
    '<div class="ap-panel"><table class="ap-simple"><thead><tr>'
    '<th style="width:180px;">항목</th><th>구글 가격 추적</th>'
    '<th>본 감시 콘솔</th></tr></thead><tbody>'
    + "".join(
        f'<tr><td style="font-weight:600;color:#131b30;">{k}</td>'
        f'<td>{a}</td><td>{b}</td></tr>'
        for k, a, b in compare
    )
    + "</tbody></table></div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
shared.section("문제 해결")

with st.expander("자주 발생하는 문제와 조치"):
    st.markdown(
        """
- **Gemini 503 오류** — 구글 서버 일시 혼잡입니다. 자동 재시도와 대체 모델 전환을
  수행하며, 계속 실패하면 30초 후 다시 시도하여 주십시오.
- **텔레그램 알림 미수신** — 생성한 봇과 먼저 대화를 시작하였는지 확인하여 주십시오.
- **조회 결과 없음** — 제공사가 일시적으로 요청을 차단할 수 있습니다. 3회 재시도하며,
  지속되면 감시 주기를 늘려 주십시오.
- **자동 감시 중단** — 공개 저장소는 60일간 활동이 없으면 스케줄이 정지됩니다.
  Actions 탭에서 다시 활성화하여 주십시오.
"""
    )
