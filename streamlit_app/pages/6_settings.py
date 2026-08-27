"""설정 페이지 - 연동 상태와 동작 방식 안내."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent.parent
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

import shared

shared.boot("settings", "설정")

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
