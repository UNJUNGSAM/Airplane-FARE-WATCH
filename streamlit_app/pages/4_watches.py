"""감시 조건 페이지 - 등록된 조건의 확인·수정·재조회·삭제."""
from __future__ import annotations

import sys
from datetime import date, timedelta
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

shared.boot("watches", "감시 조건")

db = shared.get_db()
watches = db.list_watches(active_only=False)
active_n = sum(1 for w in watches if w.active)
inactive = [w for w in watches if not w.active]
# 대시보드의 "조건 수정" 링크(/watches?edit=<id>)로 들어온 경우도 여기서 받는다.
# 예전에는 대시보드가 자체 수정 폼을 따로 갖고 있었고, 그 사본만 깨져 있었다.
_edit_param = st.query_params.get("edit")
if _edit_param:
    try:
        st.session_state["edit_watch_id"] = int(_edit_param)
    except (TypeError, ValueError):
        pass
    # clear()는 인증 토큰(?t=...)까지 지워 새로고침 시 재로그인을 요구하게 된다.
    # edit 파라미터만 제거한다.
    try:
        del st.query_params["edit"]
    except KeyError:
        pass

edit_id = st.session_state.get("edit_watch_id")

shared.page_header(
    eyebrow="Watch management",
    title="감시 조건 관리",
    desc="조건 내용을 고치거나 지금 다시 조회하고, 감시 여부를 변경하거나 삭제합니다.",
    meta_label="등록 조건",
    meta_value=f"{len(watches):,}건 · 가동 {active_n:,}건",
    cta_label="조건 등록",
    cta_href="/register",
)

with shared.util_bar():
    with shared.filter_box("watch_search"):
        sel_search = st.text_input("검색", placeholder="도시명, 공항, 라벨...", key="watch_search")

    r2, r3, r4 = st.columns([1.3, 1.6, 3.6], vertical_alignment="bottom")
    if r2.button("전체 초기화", width="stretch"):
        st.session_state["confirm_reset"] = True
        st.rerun()
    if r3.button("중지된 조건 삭제", width="stretch",
                 help="감시를 중지해 둔 조건을 한 번에 삭제합니다."):
        st.session_state["confirm_inactive"] = True
        st.rerun()
    r4.markdown(
        f'<div style="font-size:12.5px;color:#6c7585;padding-bottom:8px;">'
        f'가동 {active_n:,}건 · 중지 {len(inactive):,}건입니다.</div>',
        unsafe_allow_html=True,
    )

flash = st.session_state.pop("watch_flash", None)
if flash:
    (st.success if flash.get("ok", True) else st.error)(flash["msg"])

if st.session_state.get("confirm_reset"):
    st.error("모든 감시 조건과 가격 기록을 삭제합니다. 되돌릴 수 없습니다. 진행하시겠습니까?")
    ycol, ncol, _ = st.columns([1, 1, 4])
    if ycol.button("삭제합니다", key="reset_yes", type="primary", width="stretch"):
        def _wipe(dbase):
            dbase.delete_all_watches()
        shared.edit_with_sync(_wipe, "chore: 감시 조건 전체 초기화")
        st.session_state.pop("confirm_reset", None)
        st.session_state.pop("edit_watch_id", None)
        st.toast("모든 감시 조건을 삭제하였습니다.")
        st.rerun()
    if ncol.button("취소", key="reset_no", width="stretch"):
        st.session_state.pop("confirm_reset", None)
        st.rerun()

if st.session_state.get("confirm_inactive"):
    st.error(f"중지된 조건 {len(inactive):,}건을 삭제합니다. 진행하시겠습니까?")
    ycol, ncol, _ = st.columns([1, 1, 4])
    if ycol.button("삭제합니다", key="inactive_yes", type="primary", width="stretch"):
        def _wipe_inactive(dbase, _ids=tuple(w.id for w in inactive)):
            for _id in _ids:
                dbase.delete_watch(_id)
        shared.edit_with_sync(_wipe_inactive,
                              f"chore: 비활성 감시 조건 {len(inactive)}건 삭제")
        st.session_state.pop("confirm_inactive", None)
        st.toast(f"중지된 조건 {len(inactive):,}건을 삭제하였습니다.")
        st.rerun()
    if ncol.button("취소", key="inactive_no", width="stretch"):
        st.session_state.pop("confirm_inactive", None)
        st.rerun()

if not watches:
    st.markdown(
        '<div class="ap-panel"><div class="ap-panel-h">감시 조건</div>'
        '<div class="ap-empty">등록된 조건이 없습니다. 조건 등록 페이지를 '
        '이용하여 주십시오.</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ---------------------------------------------------------------------------
# 조건 수정 폼
# ---------------------------------------------------------------------------
def render_edit_form(w) -> None:
    """등록된 조건 1건의 수정 폼. 저장 시 변경 필드만 갱신합니다."""
    today = date.today()
    # DB에 깨진 날짜가 들어 있어도 폼이 죽지 않도록 방어한다 (대시보드와 동일 규칙)
    cur_depart = shared.safe_date(w.depart_date) or today
    cur_return = shared.safe_date(w.return_date)
    k = f"e{w.id}_"

    airport_choices = shared.get_airport_choices()
    orig_choice = shared.choice_from_code(w.origin)
    dest_choice = shared.choice_from_code(w.destination)
    orig_idx = airport_choices.index(orig_choice) if orig_choice in airport_choices else len(airport_choices) - 1
    dest_idx = airport_choices.index(dest_choice) if dest_choice in airport_choices else len(airport_choices) - 1

    with st.form(f"edit_form_{w.id}", border=True):
        st.markdown(
            f'<div class="ap-panel-title">{shared.watch_code(w)} 조건 수정</div>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        label = c1.text_input("라벨 (구분용 이름)", value=w.label, key=k + "label")
        currency = c2.selectbox("통화", shared.CURRENCIES,
                                index=shared.currency_index(w.currency), key=k + "cur")

        c3, c4 = st.columns(2)
        origin_sel = c3.selectbox("출발 공항 (도시명 또는 공항 검색)", airport_choices, index=orig_idx, key=k + "orig_sel")
        dest_sel = c4.selectbox("도착 공항 (도시명 또는 공항 검색)", airport_choices, index=dest_idx, key=k + "dest_sel")

        direct_orig = ""
        direct_dest = ""
        if origin_sel.startswith("DIRECT") or dest_sel.startswith("DIRECT"):
            d1, d2 = st.columns(2)
            if origin_sel.startswith("DIRECT"):
                direct_orig = d1.text_input("출발 공항 IATA 3글자 직접 입력", value=w.origin if orig_choice == "DIRECT · 직접 입력" else "", key=k + "orig_direct").upper().strip()
            if dest_sel.startswith("DIRECT"):
                direct_dest = d2.text_input("도착 공항 IATA 3글자 직접 입력", value=w.destination if dest_choice == "DIRECT · 직접 입력" else "", key=k + "dest_direct").upper().strip()

        c5, c6 = st.columns(2)
        trip = c5.radio("여행 유형", ["편도", "왕복"], horizontal=True,
                        index=1 if w.trip_type == "round" else 0, key=k + "trip")
        adults = c6.number_input("성인 인원", min_value=1, max_value=9,
                                 value=max(1, int(w.adults)), key=k + "adults")

        c7, c8 = st.columns(2)
        depart = c7.date_input("가는 날", value=cur_depart,
                               min_value=min(cur_depart, today), key=k + "depart")
        ret = c8.date_input(
            "오는 날 (왕복만)",
            value=cur_return or (cur_depart + timedelta(days=1)),
            min_value=min(cur_return or cur_depart, today),
            key=k + "return",
            disabled=(trip == "편도"),
        )

        t1, t2, t3 = st.columns(3)
        dep_from_s = t1.selectbox("출발 시간 (이후 포함)", shared.HOUR_OPTIONS,
                                  index=shared.hour_index(w.dep_hour_from), key=k + "df")
        dep_to_s = t2.selectbox("출발 시간 (까지 포함)", shared.HOUR_OPTIONS,
                                index=shared.hour_index(w.dep_hour_to), key=k + "dt")
        stops_s = t3.selectbox("경유 조건", shared.STOP_OPTIONS,
                               index=shared.stops_index(w.max_stops), key=k + "st")

        r1c, r2c = st.columns(2)
        ret_from_s = r1c.selectbox("귀국 출발 시간 (이후 포함)", shared.HOUR_OPTIONS,
                                   index=shared.hour_index(w.ret_hour_from),
                                   disabled=(trip == "편도"), key=k + "rf")
        ret_to_s = r2c.selectbox("귀국 출발 시간 (까지 포함)", shared.HOUR_OPTIONS,
                                 index=shared.hour_index(w.ret_hour_to),
                                 disabled=(trip == "편도"), key=k + "rt")

        target = st.number_input(
            "목표가 (0 입력 시 하락률·백분위 규칙만 적용)", min_value=0.0, step=10000.0,
            value=float(w.target_price or 0), key=k + "target",
        )

        with st.expander("고급 알림 규칙"):
            a1, a2, a3 = st.columns(3)
            drop_pct = a1.slider("첫 관측가 대비 하락률 (%)", 5, 50,
                                 int(w.drop_percent), key=k + "drop")
            pctile = a2.slider("하위 백분위 (%)", 1, 30,
                               int(w.percentile), key=k + "pct")
            cooldown = a3.slider("알림 쿨다운 (시간)", 1, 24,
                                 int(w.cooldown_hours), key=k + "cd")

        o1, o2 = st.columns(2)
        do_check = o1.checkbox("저장 후 바로 조회", value=True, key=k + "check")
        reset_base = o2.checkbox(
            "알림·판정 기준 초기화", value=False, key=k + "reset",
            help="노선이나 일정을 바꾼 경우, 하락률 판정 기준(첫 관측가)과 "
                 "재알림 기준(직전 알림가)을 함께 비웁니다.",
        )
        submitted = st.form_submit_button("변경 사항 저장", type="primary", width="stretch")

    if st.button("수정 취소", key=f"cancel_{w.id}"):
        st.session_state.pop("edit_watch_id", None)
        st.rerun()

    if not submitted:
        return

    origin = direct_orig if origin_sel.startswith("DIRECT") else shared.code_from_choice(origin_sel)
    dest = direct_dest if dest_sel.startswith("DIRECT") else shared.code_from_choice(dest_sel)

    dep_from_v = shared.hour_value(dep_from_s)
    dep_to_v = shared.hour_value(dep_to_s)
    ret_from_v = shared.hour_value(ret_from_s)
    ret_to_v = shared.hour_value(ret_to_s)
    errors = shared.validate_watch_input(origin, dest, trip, depart, ret,
                                         dep_from_v, dep_to_v, ret_from_v, ret_to_v)
    if errors:
        for e in errors:
            st.error(e)
        return

    fields = {
        "label": label.strip(),
        "origin": origin,
        "destination": dest,
        "trip_type": "round" if trip == "왕복" else "one-way",
        "depart_date": depart.isoformat(),
        "return_date": ret.isoformat() if (trip == "왕복" and ret) else None,
        "adults": int(adults),
        "currency": currency,
        "target_price": float(target) if target > 0 else None,
        "dep_hour_from": dep_from_v,
        "dep_hour_to": dep_to_v,
        "ret_hour_from": ret_from_v if trip == "왕복" else None,
        "ret_hour_to": ret_to_v if trip == "왕복" else None,
        "max_stops": shared.stops_value(stops_s),
        "drop_percent": float(drop_pct),
        "percentile": float(pctile),
        "cooldown_hours": float(cooldown),
    }
    if reset_base:
        fields["first_seen_price"] = None
        fields["last_notified_price"] = None  # 재알림 억제 기준도 함께 초기화

    shared.edit_with_sync(
        lambda dbase, _id=w.id, _f=fields: dbase.update_watch_fields(_id, **_f),
        f"feat: 감시 조건 수정 [{shared.watch_code(w)}]",
    )

    msg = f"{shared.watch_code(w)} 조건을 저장하였습니다."
    ok = True
    if do_check:
        # 원격 최신본(방금 저장한 수정 포함) 위에서 조회하고, 결과도 커밋한다.
        # 로컬에만 기록하면 클라우드에서는 다음 재배포 때 이력이 사라진다.
        base_sha = shared.sync_begin()
        fresh_db = shared.get_db()
        fresh = fresh_db.get_watch(w.id)
        if fresh is None:
            ok = False
            msg += " 다만 조건을 다시 읽지 못해 조회는 건너뛰었습니다."
        else:
            with st.spinner("변경한 조건으로 조회하고 있습니다."):
                res = shared.check_watch(fresh_db, shared.get_provider(),
                                         shared.get_gemini(), fresh)
            if res["ok"]:
                msg += f" 최저가는 {res['price']:,.0f} {fresh.currency}입니다."
                if res["notified"]:
                    msg += " 핫딜로 판정하여 텔레그램 알림을 발송하였습니다."
                note = shared.sync_note(shared.sync_commit(
                    f"chore: 수동 가격 조회 [{shared.watch_code(fresh)}]", base_sha))
                if note:
                    msg += " " + note
            else:
                ok = False
                msg += f" 다만 조회에 실패하였습니다. ({res.get('error') or '원인 불명'})"

    st.session_state["watch_flash"] = {"ok": ok, "msg": msg}
    st.session_state.pop("edit_watch_id", None)
    st.rerun()


# ---------------------------------------------------------------------------
# 조건 상태 · 실행
# ---------------------------------------------------------------------------
def render_status(w, d) -> None:
    deal, stats = d["deal"], d["stats"]
    info_col, act_col = st.columns([2.4, 1], gap="medium")

    with info_col:
        rows = [
            ("노선", f'<span class="mono">{w.route_label}</span>'),
            ("일정", f'<span class="mono">{shared.schedule_text(w)}</span>'),
            ("출발 시간대", shared.time_window_text_w(w)),
            ("귀국 시간대", shared.ret_window_text_w(w)
             if w.trip_type == "round" else "-"),
            ("경유 조건", shared.stops_text(w)),
            ("인원 · 통화", f"성인 {w.adults}명 · {w.currency}"),
            ("목표가", (f'<span class="mono">{shared.num(w.target_price)}</span> '
                     f'{w.currency}') if w.target_price else "미설정"),
            ("첫 관측가", f'<span class="mono">{shared.num(w.first_seen_price)}</span>'),
            ("현재가", f'<span class="mono">{shared.num(stats.get("last"))}</span>'
                    f' · 관측 {stats.get("count", 0):,}회'),
            ("최근 확인", f'<span class="mono">{shared.ts(w.last_checked_at)}</span>'),
            ("마지막 알림", f'<span class="mono">'
                        f'{shared.ts(w.last_notified_at, dash="발송 없음")}</span>'),
            ("알림 규칙", f'하락 {w.drop_percent:.0f}% · 하위 {w.percentile:.0f}% · '
                      f'쿨다운 {w.cooldown_hours:.0f}시간'),
        ]
        st.markdown(
            "".join(f'<div class="ap-kv"><span>{k}</span><b>{v}</b></div>'
                    for k, v in rows)
            + shared.flight_time_html(d.get("offers") or [], w),
            unsafe_allow_html=True,
        )

    with act_col:
        st.markdown(
            f'<div class="ap-panel-title">상태</div>'
            f'<div style="margin-bottom:12px;">{shared.deal_badge_html(deal)}</div>',
            unsafe_allow_html=True,
        )
        if st.button("지금 다시 조회", key=f"check_{w.id}", type="primary", width="stretch"):
            # 원격 최신본 위에서 조회하고 결과를 커밋한다 (클라우드 이력 유실 방지)
            base_sha = shared.sync_begin()
            fresh_db = shared.get_db()
            fresh = fresh_db.get_watch(w.id) or w
            with st.spinner("구글 항공권을 조회하고 있습니다."):
                res = shared.check_watch(fresh_db, shared.get_provider(),
                                         shared.get_gemini(), fresh)
            if res["ok"]:
                msg = f"최저가는 {res['price']:,.0f} {fresh.currency}입니다."
                if res["notified"]:
                    msg += " 핫딜로 판정하여 텔레그램 알림을 발송하였습니다."
                elif res.get("error"):
                    msg += f" ({res['error']})"
                note = shared.sync_note(shared.sync_commit(
                    f"chore: 수동 가격 조회 [{shared.watch_code(fresh)}]", base_sha))
                if note:
                    msg += " " + note
                st.session_state["watch_flash"] = {"ok": True, "msg": msg}
            else:
                st.session_state["watch_flash"] = {
                    "ok": False,
                    "msg": res.get("error") or "확인에 실패하였습니다.",
                }
            st.rerun()

        if st.button("조건 수정", key=f"edit_{w.id}", width="stretch"):
            st.session_state["edit_watch_id"] = w.id
            st.rerun()

        if st.button("조건 복제 (새로 등록)", key=f"clone_{w.id}", width="stretch", help="이 조건의 설정을 복사하여 새 감시 조건을 만듭니다."):
            shared.prefill_form({
                "label": f"{w.label} (복사본)" if w.label else "",
                "origin": w.origin,
                "destination": w.destination,
                "trip_type": w.trip_type,
                "depart_date": w.depart_date,
                "return_date": w.return_date,
                "adults": w.adults,
                "currency": w.currency,
                "target_price": w.target_price,
                "dep_hour_from": w.dep_hour_from,
                "dep_hour_to": w.dep_hour_to,
                "ret_hour_from": w.ret_hour_from,
                "ret_hour_to": w.ret_hour_to,
                "max_stops": w.max_stops,
            })
            st.switch_page("pages/2_register.py")

        st.link_button("구글 항공권 열기", shared.flights_search_url(w), width="stretch")

        new_active = st.toggle("감시 활성화", value=w.active, key=f"toggle_{w.id}")
        if new_active != w.active:
            shared.edit_with_sync(
                lambda d_, _id=w.id, _a=new_active: d_.set_active(_id, _a),
                f"chore: 감시 {'활성' if new_active else '중지'} [{shared.watch_code(w)}]")
            st.rerun()

        if st.button("조건 삭제", key=f"del_{w.id}", width="stretch"):
            shared.edit_with_sync(lambda d_, _id=w.id: d_.delete_watch(_id),
                                  f"chore: 감시 조건 삭제 [{shared.watch_code(w)}]")
            st.session_state.pop("edit_watch_id", None)
            st.toast(f"{shared.watch_code(w)} 조건을 삭제하였습니다.")
            st.rerun()


shared.section("조건 목록")

# 검색 필터는 shared.watch_matches 로 일원화 (페이지별 복사본 제거)
filtered_watches = [w for w in watches if shared.watch_matches(w, sel_search)]

if not filtered_watches:
    st.info("검색 조건에 일치하는 감시 조건이 없습니다.")
else:
    for w in filtered_watches:
        d = shared.load_watch_data(db, w)
        editing = (edit_id == w.id)
        header = (f"{shared.watch_code(w)}  ·  {w.origin}-{w.destination}  ·  "
                  f"{shared.route_title(w)}  ·  {'가동' if w.active else '중지'} · "
                  f"{shared.deal_text(d['deal'])}" + ("   [수정 중]" if editing else ""))
        with st.expander(header, expanded=editing):
            if editing:
                render_edit_form(w)
            else:
                render_status(w, d)
