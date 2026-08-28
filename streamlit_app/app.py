"""항공권 가격 감시 콘솔 - 대시보드 (진입점).

멀티페이지 앱의 메인 스크립트입니다. 상단 헤더의 탭으로 각 페이지를 이동하며,
Streamlit Cloud 배포 시 Main file path 를 streamlit_app/app.py 로 지정하십시오.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
# ROOT가 HERE보다 먼저 검색되어야 `import app`이 루트의 app/ 패키지를 가리킵니다
for _p in (str(HERE), str(ROOT)):
    while _p in sys.path:  # 루트가 항상 앞서도록 재정렬
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import streamlit as st

import shared

# 실행 중인 shared 모듈이 이 페이지가 기대하는 버전인지 확인한다.
# (배포 직후 Streamlit이 페이지만 새로 읽고 모듈은 예전 것을 물고 있는 경우
#  원인 모를 AttributeError 대신 무엇을 해야 하는지 알려 준다)
_NEEDS_SHARED = "2026-08-28.3"
if getattr(shared, "SHARED_REVISION", "") < _NEEDS_SHARED:
    st.error(
        "**배포된 새 코드가 아직 적용되지 않았습니다.** "
        "**[Manage app] → [⋮] → [Reboot app]** 으로 앱을 완전히 재시작하여 주십시오."
    )
    st.stop()

shared.boot("home", "대시보드")

db = shared.get_db()
watches = db.list_watches(active_only=False)

shared.page_header(
    eyebrow="Dashboard",
    title="감시 현황",
    desc=f"등록된 감시 조건 {len(watches):,}건의 최근 가격과 판정 결과를 표시합니다.",
    meta_label="최근 감시 시각",
    meta_value=shared.last_check_text(watches),
    cta_label="조건 등록",
    cta_href="/register",
)

# ---------------------------------------------------------------------------
# 유틸리티 바 - 목록 필터 · 전체 재조회
# ---------------------------------------------------------------------------
countries = sorted({shared.airport_info(w.destination)["country"] for w in watches})
with shared.util_bar():
    # 검색·필터는 접어 둔다 (모바일에서 입력칸만으로 화면을 다 차지하던 문제)
    with shared.filter_box("dash_search", "dash_country", "dash_state"):
        f1, f2, f3 = st.columns([2.2, 1.6, 1.4], vertical_alignment="bottom")
        sel_search = f1.text_input("검색", placeholder="도시명, 공항, 라벨...", key="dash_search")
        sel_country = f2.selectbox("국가", ["전체"] + countries, key="dash_country")
        sel_state = f3.selectbox("감시 상태", ["전체", "가동", "중지"], key="dash_state")

    f4, f5 = st.columns([1.8, 3.0], vertical_alignment="bottom")
    recheck = f4.button(
        "전체 다시 조회", width="stretch",
        disabled=not any(w.active for w in watches),
        help="가동 중인 모든 조건의 가격을 지금 다시 조회합니다.",
    )
    f5.markdown(
        f'<div style="font-size:11.5px;color:#8a94a6;padding-bottom:6px;text-align:right;">'
        f'자동 감시: GitHub Actions {shared.CHECK_INTERVAL_TEXT} 주기</div>',
        unsafe_allow_html=True,
    )

if recheck:
    # 원격 최신 DB 위에서 조회하고 결과를 커밋한다. 클라우드의 로컬 파일은
    # 재배포 때마다 저장소 내용으로 교체되므로, 커밋하지 않으면 수동 조회
    # 이력이 통째로 사라진다.
    base_sha = shared.sync_begin()
    db = shared.get_db()
    active_watches = [w for w in db.list_watches(active_only=True)]
    total_w = len(active_watches)
    prog_bar = st.progress(0, text=f"가동 중인 조건 {total_w}건 조회를 시작합니다...")
    ok_cnt, noti_cnt = 0, 0
    provider = shared.get_provider()
    gemini = shared.get_gemini()
    for idx, w in enumerate(active_watches):
        prog_bar.progress(
            (idx + 1) / max(1, total_w),
            text=f"조회 중 ({idx+1}/{total_w}): {w.origin}→{w.destination} ({w.label or w.route_label})"
        )
        res = shared.check_watch(db, provider, gemini, w)
        if res.get("ok"):
            ok_cnt += 1
        if res.get("notified"):
            noti_cnt += 1
    prog_bar.empty()
    sync = shared.sync_commit("chore: 수동 전체 가격 조회", base_sha) if ok_cnt else "local"
    st.session_state["dash_cycle"] = {
        "total": total_w, "ok": ok_cnt, "notified": noti_cnt, "sync": sync,
    }
    st.rerun()

cycle = st.session_state.pop("dash_cycle", None)
if cycle:
    msg = (f"전체 {cycle['total']:,}건 중 {cycle['ok']:,}건을 조회하였습니다."
           f" 핫딜 알림 {cycle['notified']:,}건을 발송하였습니다.")
    note = shared.sync_note(cycle.get("sync", "local"))
    if note:
        msg += " " + note
    (st.success if cycle["ok"] == cycle["total"] and not note else st.warning)(msg)

# ---------------------------------------------------------------------------
# 데이터 적재
# ---------------------------------------------------------------------------
data = {w.id: shared.load_watch_data(db, w) for w in watches}
notis = db.list_notifications(limit=200)

active_n = sum(1 for w in watches if w.active)
best_n = sum(1 for d in data.values() if d["deal"]["level"] == "best")
checked_n = shared.today_checked(watches)

# 검색·국가 필터는 페이지마다 같은 규칙이어야 하므로 shared.watch_matches 하나로 통일한다
# (기존에는 app / 3_trend / 4_watches 에 같은 함수가 세 벌 복사되어 있었다)
shown = [
    w for w in watches
    if shared.watch_matches(w, sel_search, sel_country)
    and (sel_state == "전체"
         or (sel_state == "가동" and w.active)
         or (sel_state == "중지" and not w.active))
]

shared.tiles([
    {"label": "감시 중인 조건", "value": f"{active_n:,}", "unit": "건",
     "sub": f"등록 전체 {len(watches):,}건"},
    {"label": "최저가 구간", "value": f"{best_n:,}", "unit": "건",
     "sub": "최근 30일 이력 기준"},
    {"label": "누적 알림 발송", "value": f"{len(notis):,}", "unit": "건",
     "sub": "텔레그램 발송 기록"},
    {"label": "오늘 확인", "value": f"{checked_n:,}/{active_n:,}", "unit": "건",
     "sub": f"감시 주기 {shared.CHECK_INTERVAL_TEXT}"},
])

# ---------------------------------------------------------------------------
# 본문 (감시 조건 표 - 각 행 클릭 시 그 자리에서 상세 항공편 펼침)
# ---------------------------------------------------------------------------
flash = st.session_state.pop("dash_watch_flash", None)
if flash:
    (st.success if flash.get("ok", True) else st.error)(flash["msg"])

if not watches:
    table_body = (
        '<div class="ap-panel"><div class="ap-panel-h">감시 조건</div>'
        '<div class="ap-empty">등록된 감시 조건이 없습니다. '
        '상단의 <b>조건 등록</b>에서 첫 조건을 추가하여 주십시오.</div></div>'
    )
elif not shown:
    table_body = (
        '<div class="ap-panel"><div class="ap-panel-h">감시 조건</div>'
        '<div class="ap-empty">선택한 조건에 해당하는 항목이 없습니다. '
        '필터를 조정하여 주십시오.</div></div>'
    )
else:
    groups: dict[str, list] = {}
    for w in shown:
        groups.setdefault(shared.airport_info(w.destination)["country"], []).append(w)

    parts = [
        f'<div class="ap-panel-h">감시 조건'
        f'<span class="n">{len(shown):,} / {len(watches):,}</span></div>',
        shared.watch_table_header(),
    ]
    for country, ws in sorted(groups.items(), key=lambda kv: kv[0]):
        parts.append(f'<div class="ap-group">{html.escape(country)}'
                     f'<span class="n">{len(ws):,}건</span></div>')
        parts += [shared.watch_expandable_row_html(w, data[w.id]) for w in ws]
    table_body = f'<div class="ap-table">{"".join(parts)}</div>'


def left_content():
    # 조건 수정 폼은 '조건 관리' 페이지 한 곳에만 둔다.
    # 예전에는 여기에 사본이 하나 더 있었고, 그 사본만 존재하지 않는 메서드를
    # 호출해 저장할 때마다 죽었다. 이제는 /watches?edit=<id> 로 넘긴다.
    legacy_edit = st.query_params.get("edit")
    if legacy_edit:
        try:  # 세션에 실어 보낸다 (페이지 전환 시 쿼리 파라미터는 보장되지 않음)
            st.session_state["edit_watch_id"] = int(legacy_edit)
        except (TypeError, ValueError):
            pass
        try:  # 인증 토큰(?t=)은 남겨 두고 edit 만 지운다
            del st.query_params["edit"]
        except KeyError:
            pass
        st.switch_page("pages/4_watches.py")

    st.markdown(
        f'<div style="font-size:12.5px;color:#6c7585;margin-bottom:8px;font-weight:600;">'
        f'💡 감시 조건 행(노선, 일정, 가격 등)을 <b>클릭</b>하면 최근 항공편 목록과 가격 요약이 그 자리에서 펼쳐집니다.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(table_body, unsafe_allow_html=True)


recent = notis[:5]
if recent:
    noti_rows = "".join(
        f'<div class="ap-noti"><div class="t mono">{shared.ts(n["sent_at"])}</div>'
        f'<div class="l">{html.escape(str(n["label"] or "-"))}</div>'
        f'<div class="p"><span class="mono">{shared.num(n["price"])}</span>'
        f' · {html.escape(str(n["reason"] or "-"))}</div></div>'
        for n in recent
    )
    noti_panel = (f'<div class="ap-panel"><div class="ap-panel-h">최근 알림'
                  f'<span class="n">{len(notis):,}건</span></div>'
                  f'<div class="ap-panel-b">{noti_rows}</div></div>')
else:
    noti_panel = ('<div class="ap-panel"><div class="ap-panel-h">최근 알림</div>'
                  '<div class="ap-empty">발송된 알림이 없습니다. 핫딜로 판정되면 '
                  '텔레그램으로 발송한 뒤 이곳에 기록합니다.</div></div>')

eng = shared.engine_state()


def _state(ok: bool, on: str = "연동", off: str = "미설정") -> str:
    dot = "dot-ok" if ok else "dot-idle"
    return f'<span class="st"><span class="ap-dot {dot}"></span>{on if ok else off}</span>'


slab = (
    '<div class="ap-slab"><h4>감시 엔진 상태</h4>'
    f'<div class="kv"><span>운영 상태</span>'
    f'<span class="st"><span class="ap-dot {eng["dot"]}"></span>{eng["label"]}</span></div>'
    f'<div class="kv"><span>감시 주기</span><b class="mono">{shared.CHECK_INTERVAL_TEXT}</b></div>'
    f'<div class="kv"><span>오늘 확인</span>'
    f'<b class="mono">{checked_n:,} / {active_n:,}건</b></div>'
    f'<div class="kv"><span>최근 감시 시각</span>'
    f'<b class="mono">{shared.last_check_text(watches)}</b></div>'
    f'<div class="kv"><span>텔레그램 알림</span>{_state(eng["telegram"])}</div>'
    f'<div class="kv"><span>GitHub 동기화</span>{_state(eng["github"])}</div>'
    f'<div class="kv"><span>Gemini 분석</span>{_state(eng["gemini"])}</div>'
    '</div>'
)

# 여행 테마 핫딜 비주얼 카드
travel_card = """
<div style="background: linear-gradient(rgba(19,27,48,0.35), rgba(19,27,48,0.88)), url('https://images.unsplash.com/photo-1436491865332-7a61a109cc05?auto=format&fit=crop&w=600&q=80') center/cover no-repeat;
            border-radius: 12px; padding: 18px 16px; color: #ffffff; box-shadow: 0 4px 12px rgba(19,27,48,.12); margin-bottom: 12px;">
  <div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#44beaf;font-family:var(--font-mono);">
    TRAVEL INSIGHT ✈️
  </div>
  <div style="font-size:15px;font-weight:700;margin-top:5px;line-height:1.3;color:#ffffff;">
    설레는 여행의 시작,<br>최저가 타이밍을 잡으세요!
  </div>
  <div style="font-size:12px;color:#d8e2f0;margin-top:6px;line-height:1.4;">
    직항·선호 시간대 필터를 모두 통과한 진짜 특가만 텔레그램으로 바로 알려드립니다.
  </div>
</div>
"""

# 2열 레이아웃 배치
col_main, col_rail = st.columns([2.7, 1.0], gap="medium")
with col_main:
    left_content()

with col_rail:
    st.markdown(travel_card, unsafe_allow_html=True)
    st.markdown(noti_panel, unsafe_allow_html=True)
    st.markdown(slab, unsafe_allow_html=True)


