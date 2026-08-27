"""조건 등록 페이지 - 자연어(Gemini) 등록과 상세 폼 입력."""
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

import pandas as pd
import streamlit as st

import shared

shared.boot("register", "조건 등록")

db = shared.get_db()
registered = db.list_watches(active_only=False)

shared.page_header(
    eyebrow="Watch registration",
    title="감시 조건 등록",
    desc="자연어로 한 번에 등록하거나, 상세 폼에서 항목별로 입력합니다.",
    meta_label="등록된 조건",
    meta_value=f"{len(registered):,}건",
    attached=False,
)

# ---------------------------------------------------------------------------
# 자연어 등록 (상단 감성 배너)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="background: linear-gradient(135deg, rgba(36,48,80,0.88), rgba(19,128,184,0.85)), url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80') center/cover no-repeat;
                border-radius: 10px; padding: 14px 20px; color: #ffffff; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
      <div>
        <div style="font-size:14.5px;font-weight:700;letter-spacing:-.01em;">🌴 여행지 다중 감시 · AI 스마트 등록</div>
        <div style="font-size:12px;color:#e1edf8;margin-top:3px;">"9월말 다낭이나 나트랑 직항 밤비행기 35만원 이하"처럼 문장으로 편하게 등록하세요.</div>
      </div>
      <div style="font-size:26px;opacity:0.9;">✈️</div>
    </div>
    """,
    unsafe_allow_html=True,
)

shared.section("자연어 등록 (Gemini)")

st.caption("목적지가 여러 곳이거나 시간대·직항 조건이 있어도 한 번에 등록할 수 있습니다.")

nl_text = st.text_area(
    "원하는 일정을 문장으로 입력하십시오",
    placeholder=(
        "예) 9월 23일 오후 8시 이후 또는 9월 24일 오전 출발, "
        "다낭·나트랑·푸꾸옥 직항 중 가격이 내려가면 알려 주십시오"
    ),
    height=92,
)
if st.button("Gemini로 분석", type="primary"):
    if not nl_text.strip():
        st.warning("분석할 내용을 입력하여 주십시오.")
    elif not shared.get_gemini().available:
        st.error("GEMINI_API_KEY가 설정되지 않았습니다. 아래 상세 폼을 이용하여 주십시오.")
    else:
        try:
            drafts = shared.get_gemini().parse_watch_query(nl_text)
            st.session_state["nl_drafts"] = drafts
            shared.prefill_form(drafts[0])
            if len(drafts) > 1:
                st.success(f"분석을 완료하였습니다. 감시 조건 {len(drafts):,}건을 확인하였습니다.")
            else:
                d0 = drafts[0]
                st.success(
                    f"분석을 완료하였습니다. {d0['origin']} → {d0['destination']} "
                    f"({d0['depart_date']}) 결과를 아래 폼에 반영하였습니다."
                )
        except Exception as exc:  # noqa: BLE001
            st.error(f"자연어 분석에 실패하였습니다. ({exc})")
            st.info(
                "Gemini 서버가 일시적으로 혼잡할 수 있습니다. 자동 재시도와 대체 모델 전환을 "
                "수행하였으나 실패하였습니다. 30초 후 다시 시도하시거나 아래 상세 폼을 "
                "이용하여 주십시오."
            )

# --- 분석 결과 미리보기 (세션 유지) ---
drafts = st.session_state.get("nl_drafts")
if drafts:
    if len(drafts) > 1:
        st.markdown(
            f'<div class="ap-note" style="margin-bottom:8px;">분석 결과 '
            f'총 <b>{len(drafts):,}건</b>의 일정이 생성되었습니다. 등록할 조건을 선택하여 주십시오.</div>',
            unsafe_allow_html=True,
        )

        selected_indices = []
        for idx, d in enumerate(drafts):
            stops_str = {None: "경유 무관", 0: "직항만", 1: "1회경유"}.get(d.get("max_stops"), "무관")
            dep_win = shared.time_window_parts(d.get("dep_hour_from"), d.get("dep_hour_to"))
            ret_info = ""
            if d.get("trip_type") == "round" and d.get("return_date"):
                ret_win = shared.time_window_parts(d.get("ret_hour_from"), d.get("ret_hour_to"))
                ret_info = f" ~ 오는 날 {d['return_date']} ({ret_win})"

            checked = st.checkbox(
                f"**{d['label']}** : {d['origin']} → {d['destination']} | 가는 날 {d['depart_date']} ({dep_win}){ret_info} | {stops_str}",
                value=True,
                key=f"draft_check_{idx}",
            )
            if checked:
                selected_indices.append(idx)

        bcol1, bcol2, _ = st.columns([1.6, 1, 3.4])
        selected_drafts = [drafts[i] for i in selected_indices]
        if bcol1.button(
            f"선택한 {len(selected_drafts):,}건 등록",
            key="bulk_register",
            type="primary",
            width="stretch",
            disabled=not selected_drafts,
        ):
            def _bulk(dbase, _drafts=tuple(selected_drafts)):
                for d in _drafts:
                    dbase.add_watch(shared.draft_to_watch(d))

            shared.edit_with_sync(_bulk, f"feat: 자연어로 감시 조건 {len(selected_drafts)}건 일괄 추가")
            st.session_state.pop("nl_drafts", None)
            st.toast(f"조건 {len(selected_drafts):,}건을 등록하였습니다.")
            st.rerun()

        if bcol2.button("목록 지우기", key="clear_drafts", width="stretch"):
            st.session_state.pop("nl_drafts", None)
            st.rerun()

        st.caption("개별 상세 수정이 필요하면 아래 상세 폼을 이용하여 주십시오. (첫 번째 조건이 폼에 반영되어 있습니다)")
    else:
        st.caption("분석 결과가 아래 상세 폼에 반영되어 있습니다. 확인 후 등록하여 주십시오.")

# ---------------------------------------------------------------------------
# 상세 폼
# ---------------------------------------------------------------------------
shared.section("상세 입력")

airport_choices = shared.get_airport_choices()

# 출발 / 도착 공항 기본값 계산
cur_origin_code = st.session_state.get("f_origin", "ICN")
cur_origin_choice = shared.choice_from_code(cur_origin_code)
origin_idx = airport_choices.index(cur_origin_choice) if cur_origin_choice in airport_choices else len(airport_choices) - 1

cur_dest_code = st.session_state.get("f_dest", "DAD")
cur_dest_choice = shared.choice_from_code(cur_dest_code)
dest_idx = airport_choices.index(cur_dest_choice) if cur_dest_choice in airport_choices else len(airport_choices) - 1

with st.form("register_form", border=True):
    fcol1, fcol2 = st.columns(2)
    label = fcol1.text_input("라벨 (구분용 이름)", key="f_label", placeholder="예) 골든위크 다낭")
    currency = fcol2.selectbox("통화", shared.CURRENCIES, key="f_currency")

    # 공항 선택
    acol1, acol2 = st.columns(2)
    origin_sel = acol1.selectbox(
        "출발 공항 (도시명 또는 공항 검색)",
        airport_choices,
        index=origin_idx,
        key="f_origin_sel",
        help="한글 도시명이나 IATA 3자리 코드로 검색하여 선택하세요.",
    )
    dest_sel = acol2.selectbox(
        "도착 공항 (도시명 또는 공항 검색)",
        airport_choices,
        index=dest_idx,
        key="f_dest_sel",
        help="한글 도시명이나 IATA 3자리 코드로 검색하여 선택하세요.",
    )

    # 직접 입력 선택 시 노출
    direct_orig = ""
    direct_dest = ""
    if origin_sel.startswith("DIRECT") or dest_sel.startswith("DIRECT"):
        dcol1, dcol2 = st.columns(2)
        if origin_sel.startswith("DIRECT"):
            direct_orig = dcol1.text_input("출발 공항 IATA 3글자 직접 입력", value=cur_origin_code if cur_origin_choice == "DIRECT · 직접 입력" else "", key="f_orig_direct").upper().strip()
        if dest_sel.startswith("DIRECT"):
            direct_dest = dcol2.text_input("도착 공항 IATA 3글자 직접 입력", value=cur_dest_code if cur_dest_choice == "DIRECT · 직접 입력" else "", key="f_dest_direct").upper().strip()

    fcol5, fcol6 = st.columns(2)
    trip = fcol5.radio("여행 유형", ["편도", "왕복"], horizontal=True, key="f_trip",
                       help="왕복이면 가는 날·오는 날 두 날짜로 검색하며 가격은 왕복 총액입니다.")
    adults = fcol6.number_input("성인 인원", min_value=1, max_value=9, key="f_adults")

    fcol7, fcol8 = st.columns(2)
    depart = fcol7.date_input("가는 날", min_value=date.today(), key="f_depart")
    ret = fcol8.date_input(
        "오는 날 (왕복만)",
        min_value=date.today() + timedelta(days=1),
        key="f_return",
        disabled=(trip == "편도"),
    )

    tcol1, tcol2, tcol3 = st.columns(3)
    dep_from_s = tcol1.selectbox(
        "출발 시간 (이후 포함)", shared.HOUR_OPTIONS, key="f_depfrom",
        help="이 시간부터 출발하는 항공편만 감시합니다. (예: 오후 8시 이후 → 20시)",
    )
    dep_to_s = tcol2.selectbox(
        "출발 시간 (까지 포함)", shared.HOUR_OPTIONS, key="f_depto",
        help="이 시간에 출발하는 항공편까지 포함합니다. 23시 선택 시 23:00~23:59도 포함됩니다.",
    )
    stops_s = tcol3.selectbox(
        "경유 조건", shared.STOP_OPTIONS, key="f_stops",
        help="직항만 감시하거나 1회 경유까지 허용할 수 있습니다.",
    )

    rtcol1, rtcol2 = st.columns(2)
    ret_from_s = rtcol1.selectbox(
        "귀국 출발 시간 (이후 포함)", shared.HOUR_OPTIONS, key="f_retfrom",
        disabled=(trip == "편도"),
        help="왕복일 때 귀국편이 이 시간부터 출발하도록 필터링합니다. (예: 오후 귀국 → 12시)",
    )
    ret_to_s = rtcol2.selectbox(
        "귀국 출발 시간 (까지 포함)", shared.HOUR_OPTIONS, key="f_retto",
        disabled=(trip == "편도"),
        help="예: 새벽 2시 이전 귀국 → 제한없음 ~ 02시",
    )

    target = st.number_input(
        "목표가 (0 입력 시 하락률·백분위 규칙만 적용)",
        min_value=0.0,
        step=10000.0,
        key="f_target",
        help="이 가격 이하로 내려가면 즉시 알림을 발송합니다.",
    )

    with st.expander("고급 알림 규칙"):
        acol1, acol2, acol3 = st.columns(3)
        drop_pct = acol1.slider(
            "첫 관측가 대비 하락률 (%)", 5, 50, 15, key="f_drop",
            help="첫 확인 가격 대비 이만큼 내려가면 알림을 발송합니다.",
        )
        pctile = acol2.slider(
            "하위 백분위 (%)", 1, 30, 10, key="f_pctile",
            help="최근 30일 이력에서 이 백분위 안에 들면 알림을 발송합니다. (10회 이상 관측 후 적용)",
        )
        cooldown = acol3.slider(
            "알림 쿨다운 (시간)", 1, 24, 6, key="f_cooldown",
            help="같은 조건의 재알림 최소 간격입니다.",
        )

    submitted = st.form_submit_button("감시 시작", type="primary", width="stretch")

if submitted:
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
    else:
        watch = shared.draft_to_watch({
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
        })
        watch.drop_percent = float(drop_pct)
        watch.percentile = float(pctile)
        watch.cooldown_hours = float(cooldown)
        shared.edit_with_sync(lambda d: d.add_watch(watch),
                              f"feat: 감시 조건 추가 [{watch.label or watch.route_label}]")
        st.success(f"감시 조건을 등록하였습니다. ({watch.label or watch.route_label})")
        st.info(
            f"GitHub Actions가 {shared.CHECK_INTERVAL_TEXT}마다 가격을 확인합니다. "
            "항공편 조회 페이지에서 즉시 조회도 가능합니다."
        )
        for k in ("f_label", "f_origin", "f_dest", "f_target", "nl_drafts", "f_origin_choice", "f_dest_choice"):
            st.session_state.pop(k, None)
