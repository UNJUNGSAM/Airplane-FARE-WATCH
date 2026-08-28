"""항공편 조회 페이지 - 감시 조건별 즉시 조회와 최근 조회 결과."""
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
_NEEDS_SHARED = "2026-08-28.3"
if getattr(shared, "SHARED_REVISION", "") < _NEEDS_SHARED:
    st.error(
        "**배포된 새 코드가 아직 적용되지 않았습니다.** "
        "**[Manage app] → [⋮] → [Reboot app]** 으로 앱을 완전히 재시작하여 주십시오."
    )
    st.stop()

shared.boot("flights", "항공편 조회")

db = shared.get_db()
watches = db.list_watches(active_only=False)

if not watches:
    shared.page_header(
        eyebrow="Flight search",
        title="항공편 조회",
        desc="조회할 감시 조건이 없습니다.",
        attached=False,
    )
    st.info("먼저 조건 등록 페이지에서 감시 조건을 만들어 주십시오.")
    st.stop()

# 선택 상태는 위젯 키로 보관하여 타이틀 바에서도 참조합니다
opts = shared.watch_options(watches)
labels = list(opts.keys())
picked = st.session_state.get("flt_watch")
if picked not in opts:
    picked = labels[0]
wid = opts[picked]
w = next(x for x in watches if x.id == wid)
d = shared.load_watch_data(db, w)
deal, stats = d["deal"], d["stats"]

shared.page_header(
    eyebrow="Flight search",
    title="항공편 조회",
    desc="선택한 감시 조건으로 즉시 조회하거나, 마지막 조회 결과를 확인합니다.",
    meta_label="마지막 조회",
    meta_value=shared.ts(w.last_checked_at),
    cta_label="구글 항공권 열기",
    cta_href=shared.flights_search_url(w),
    attached=False,
)

left, right = st.columns([1, 2.55], gap="medium")

# ---------------------------------------------------------------------------
# 좌측 필터 패널
# ---------------------------------------------------------------------------
with left:
    with st.container(key="ap_filters"):
        st.markdown('<div class="ap-panel-title">조회 대상</div>', unsafe_allow_html=True)
        st.selectbox("감시 조건", labels, key="flt_watch", label_visibility="collapsed")
        refresh = st.button("지금 조회", type="primary", width="stretch")
        if st.button("가격 추이 보기", width="stretch"):
            st.session_state["chart_watch_id"] = wid
            st.switch_page("pages/3_trend.py")

        rows = [
            ("노선", f'<span class="mono">{w.origin} → {w.destination}</span>'),
            ("일정", f'<span class="mono">{shared.schedule_text(w)}</span>'),
            ("여행 유형", "왕복" if w.trip_type == "round" else "편도"),
            ("가는 편 시간대", shared.time_window_text_w(w)),
        ]
        if w.trip_type == "round":
            rows.append(("귀국 시간대", shared.ret_window_text_w(w)))
        rows += [
            ("경유 조건", shared.stops_text(w)),
            ("인원 · 통화", f"성인 {w.adults}명 · {w.currency}"),
            ("목표가", (f'<span class="mono">{shared.num(w.target_price)}</span> {w.currency}'
                     if w.target_price else "미설정")),
            ("알림 규칙", f'하락 {w.drop_percent:.0f}% · 하위 {w.percentile:.0f}%'),
        ]
        st.markdown(
            '<div class="ap-panel-title" style="margin-top:16px;">적용 필터</div>'
            + "".join(f'<div class="ap-kv"><span>{k}</span><b>{v}</b></div>' for k, v in rows),
            unsafe_allow_html=True,
        )
        if w.trip_type == "round":
            st.markdown(
                '<div class="ap-note" style="margin-top:12px;">왕복 조건이므로 '
                '표시 가격은 왕복 총액입니다.</div>',
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# 우측 결과
# ---------------------------------------------------------------------------
if refresh:
    # 원격 최신본 위에서 조회하고 결과를 커밋한다 (클라우드 이력 유실 방지)
    base_sha = shared.sync_begin()
    db = shared.get_db()
    w = db.get_watch(wid) or w
    with st.spinner("구글 항공권을 조회하고 있습니다."):
        res = shared.check_watch(db, shared.get_provider(), shared.get_gemini(), w)
    with right:
        if res["ok"]:
            msg = f"조회를 완료하였습니다. 최저가 {res['price']:,.0f} {w.currency}입니다."
            if res["notified"]:
                msg += " 핫딜로 판정하여 텔레그램 알림을 발송하였습니다."
            note = shared.sync_note(shared.sync_commit(
                f"chore: 수동 가격 조회 [{shared.watch_code(w)}]", base_sha))
            if note:
                msg += " " + note
            (st.success if not note else st.warning)(msg)
            d = shared.load_watch_data(db, w)
            deal, stats = d["deal"], d["stats"]
        else:
            st.error(res.get("error") or "조회에 실패하였습니다.")

with right:
    figures = [
        ("현재 최저가", shared.num(stats.get("last")), w.currency),
        ("30일 최저", shared.num(stats.get("min")), w.currency),
        ("30일 평균", shared.num(stats.get("avg")), w.currency),
        ("첫 관측가", shared.num(stats.get("first")), w.currency),
    ]
    fig_html = "".join(
        f'<div class="ap-figure"><div class="k">{k}</div>'
        f'<div class="v">{v}<span class="cur">{cur}</span></div></div>'
        for k, v, cur in figures
    )
    st.markdown(
        f'<div class="ap-panel"><div class="ap-panel-h">가격 요약'
        f'<span class="n">관측 {stats.get("count", 0):,}회 · '
        f'{shared.deal_text(deal)}</span></div>'
        f'<div class="ap-figures">{fig_html}</div></div>',
        unsafe_allow_html=True,
    )

    offers = d["offers"]
    if not offers:
        st.markdown(
            '<div class="ap-panel" style="margin-top:14px;">'
            '<div class="ap-panel-h">조회 결과</div>'
            '<div class="ap-empty">조회 기록이 없습니다. 왼쪽의 '
            '<b>지금 조회</b>를 눌러 주십시오.</div></div>',
            unsafe_allow_html=True,
        )
    else:
        search_url = shared.flights_search_url(w)
        rows_html = "".join(
            shared.offer_row_html(o, w.currency, search_url, rank)
            for rank, o in enumerate(offers)
        )
        st.markdown(
            f'<div class="ap-panel" style="margin-top:14px;">'
            f'<div class="ap-panel-h">조회 결과'
            f'<span class="n">{len(offers):,}건 · '
            f'{shared.ts(offers[0]["checked_at"])}</span></div>'
            f'{rows_html}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="ap-note">가격은 조회 시점 기준이며 실제 예약 화면과 다를 수 '
            '있습니다. 각 행의 <b>구글 항공권 확인</b>에서 최종 확인하여 주십시오.</div>',
            unsafe_allow_html=True,
        )
