"""조건 등록 페이지 - 자연어(Gemini) 등록, 기존 조건 기반 다른 공항 복제 등록, 상세 폼 입력."""
from __future__ import annotations

import html
import re
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

import importlib
import shared
try:
    importlib.reload(shared)
except Exception:
    pass

_NEEDS_SHARED = "2026-10-02.01"
if getattr(shared, "SHARED_REVISION", "") < _NEEDS_SHARED:
    st.error(
        "**배포된 새 코드가 아직 적용되지 않았습니다.** "
        "**[Manage app] → [⋮] → [Reboot app]** 으로 앱을 완전히 재시작하여 주십시오."
    )
    st.stop()

shared.boot("register", "조건 등록")

db = shared.get_db()
registered = db.list_watches(active_only=False)


def _watch_key(origin, dest, depart, trip, ret):
    """같은 감시로 볼 조건의 식별자 (노선·날짜·유형)."""
    return shared.watch_unique_key(origin, dest, depart, trip, ret)


def _find_same(origin, dest, depart, trip, ret):
    return shared.find_duplicate_watch(registered, origin, dest, depart, trip, ret)


shared.page_header(
    eyebrow="Watch registration",
    title="감시 조건 등록",
    desc="자연어로 한 번에 등록하거나, 기존 조건을 다른 여행지로 복제하거나, 상세 항목을 직접 입력합니다.",
    meta_label="등록된 조건",
    meta_value=f"{len(registered):,}건",
    attached=False,
)

# ---------------------------------------------------------------------------
# 등록 모드 전환 탭 / 세그먼트
# ---------------------------------------------------------------------------
REG_MODES = [
    "💬 자연어 등록 (Gemini)",
    "🔄 기존 조건 복제 등록 (다른 공항 추가)",
    "📝 상세 직접 입력",
]

# 외부나 세션에서 요청된 모드가 있으면 우선 반영
req_mode = st.session_state.pop("reg_mode", None)
if req_mode and req_mode in REG_MODES:
    st.session_state["reg_mode_radio"] = req_mode

if "reg_mode_radio" not in st.session_state or st.session_state["reg_mode_radio"] not in REG_MODES:
    st.session_state["reg_mode_radio"] = REG_MODES[0]

cur_mode = st.radio(
    "등록 방식 선택",
    REG_MODES,
    key="reg_mode_radio",
    horizontal=True,
    label_visibility="collapsed",
)

st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)


# ===========================================================================
# 1. 자연어 등록 (Gemini)
# ===========================================================================
if cur_mode == "💬 자연어 등록 (Gemini)":
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, rgba(36,48,80,0.90), rgba(19,128,184,0.88)), url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80') center/cover no-repeat;
                    border-radius: 12px; padding: 16px 22px; color: #ffffff; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 12px rgba(19,27,48,.10);">
          <div>
            <div style="font-size:15px;font-weight:700;letter-spacing:-.01em;">🌴 여행지 다중 감시 · AI 스마트 등록</div>
            <div style="font-size:12.5px;color:#e1edf8;margin-top:4px;">"9월말 다낭이나 나트랑 직항 밤비행기 35만원 이하"처럼 문장으로 편하게 등록하세요.</div>
          </div>
          <div style="font-size:30px;opacity:0.95;">✈️</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    shared.section("자연어 등록 (Gemini)")
    st.caption("목적지가 여러 곳이거나 시간대·직항 조건이 있어도 한 번에 등록할 수 있습니다.")

    # 추천 예시 칩 버튼 (빠른 입력 편의성)
    st.markdown("<div style='font-size:11.5px;font-weight:600;color:#6c7585;margin-bottom:4px;'>💡 클릭하여 추천 예시 문장 바로 넣기:</div>", unsafe_allow_html=True)
    ec1, ec2, ec3 = st.columns(3)
    if ec1.button("🌴 다낭/나트랑 밤비행기 35만원", key="ex_btn_1", use_container_width=True):
        st.session_state["nl_text_input"] = "9월 25일 이후 다낭이나 나트랑 직항 밤비행기 35만원 이하 왕복"
        st.rerun()
    if ec2.button("🗼 황금연휴 도쿄/후쿠오카 왕복", key="ex_btn_2", use_container_width=True):
        st.session_state["nl_text_input"] = "10월 3일 출발 10월 7일 귀국 도쿄 또는 후쿠오카 직항 왕복"
        st.rerun()
    if ec3.button("🐘 방콕 직항 40만원 이하", key="ex_btn_3", use_container_width=True):
        st.session_state["nl_text_input"] = "11월 15일 출발 11월 19일 귀국 방콕 직항 40만원 이하"
        st.rerun()

    nl_text = st.text_area(
        "원하는 일정을 문장으로 입력하십시오",
        placeholder=(
            "예) 9월 23일 오후 8시 이후 또는 9월 24일 오전 출발, "
            "다낭·나트랑·푸꾸옥 직항 중 가격이 내려가면 알려 주십시오"
        ),
        height=88,
        key="nl_text_input",
    )
    if st.button("Gemini로 분석", type="primary", key="nl_analyze_btn", width="stretch"):
        if not nl_text.strip():
            st.warning("분석할 내용을 입력하여 주십시오.")
        elif not shared.get_gemini().available:
            st.error("GEMINI_API_KEY가 설정되지 않았습니다. 상세 직접 입력 또는 복제 등록을 이용하여 주십시오.")
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
                        f"({d0['depart_date']}) 결과를 확인 후 아래에서 등록하여 주십시오."
                    )
            except Exception as exc:  # noqa: BLE001
                st.error(f"자연어 분석에 실패하였습니다. ({exc})")
                st.info(
                    "Gemini 서버가 일시적으로 혼잡할 수 있습니다. 자동 재시도와 대체 모델 전환을 "
                    "수행하였으나 실패하였습니다. 30초 후 다시 시도하시거나 상세 직접 입력을 "
                    "이용하여 주십시오."
                )

    # --- 분석 결과 미리보기 (세션 유지) ---
    drafts = st.session_state.get("nl_drafts")
    if drafts:
        st.markdown(
            f'<div class="ap-note" style="margin-top:14px; margin-bottom:8px;">분석 결과 '
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
            fresh, skipped, seen = [], [], set()
            for d in selected_drafts:
                key = _watch_key(d["origin"], d["destination"], d["depart_date"],
                                 d.get("trip_type") or "one-way", d.get("return_date"))
                dup = _find_same(*key[:4], key[4])
                if dup is not None or key in seen:
                    skipped.append(d.get("label") or f"{d['origin']}→{d['destination']}")
                else:
                    seen.add(key)
                    fresh.append(d)

            if fresh:
                def _bulk(dbase, _drafts=tuple(fresh)):
                    for d in _drafts:
                        dbase.add_watch(shared.draft_to_watch(d))

                shared.edit_with_sync(_bulk, f"feat: 자연어로 감시 조건 {len(fresh)}건 일괄 추가")
                st.session_state["last_added_watch_code"] = f"{fresh[0]['origin']}→{fresh[0]['destination']}"
                st.session_state["last_added_watch_draft"] = fresh[0]

            st.session_state.pop("nl_drafts", None)
            msg = f"조건 {len(fresh):,}건을 등록하였습니다."
            if skipped:
                msg += f" (이미 등록되어 건너뜀: {', '.join(skipped)})"
            st.toast(msg)
            st.rerun()

        if bcol2.button("목록 지우기", key="clear_drafts", width="stretch"):
            st.session_state.pop("nl_drafts", None)
            st.rerun()

    # 등록 후 안내 배너 (같은 일정으로 다른 여행지 복제 추천)
    if "last_added_watch_code" in st.session_state and registered:
        last_code = st.session_state.get("last_added_watch_code")
        st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
        cbox1, cbox2 = st.columns([3.5, 1.5], vertical_alignment="center")
        with cbox1:
            st.markdown(
                f"💡 **방금 등록한 조건({last_code})과 동일한 일정으로 다른 여행지도 감시하시겠습니까?**<br>"
                "<span style='font-size:12px;color:#6c7585;'>여행 기간, 출발 시간대, 직항 여부를 그대로 복사해 나트랑, 방콕, 후쿠오카 등을 원클릭 등록할 수 있습니다.</span>",
                unsafe_allow_html=True,
            )
        with cbox2:
            if st.button("🔄 다른 여행지로 복제 등록", type="primary", use_container_width=True, key="btn_goto_clone"):
                st.session_state["reg_mode"] = "🔄 기존 조건 복제 등록 (다른 공항 추가)"
                st.rerun()


# ===========================================================================
# 2. 기존 조건 복제 등록 (다른 공항 일괄 추가)
# ===========================================================================
elif cur_mode == "🔄 기존 조건 복제 등록 (다른 공항 추가)":
    shared.section("기존 조건으로 다른 여행지(공항) 일괄 등록")
    st.caption("이미 등록된 일정·시간대·경유·인원 조건을 그대로 가져와, 다른 국가나 여행지(공항)만 손쉽게 일괄 추가합니다.")

    if not registered:
        shared.render_empty_state(
            title="등록된 감시 조건이 없습니다",
            desc="복제할 기준 조건이 없습니다. 먼저 '자연어 등록' 또는 '상세 직접 입력'으로 첫 조건을 등록해 주세요.",
            icon="🛫",
            cta_label="💬 자연어 등록으로 이동",
            cta_page="pages/2_register.py",
        )
    else:
        # 기준 조건 선택
        clone_id = st.session_state.pop("clone_watch_id", None) or st.session_state.get("selected_clone_watch_id")

        sorted_watches = sorted(registered, key=lambda w: w.id or 0, reverse=True)
        watch_map: dict[str, Any] = {}
        default_idx = 0
        for idx, w in enumerate(sorted_watches):
            dest_info = shared.airport_info(w.destination)
            desc = (
                f"[{shared.watch_code(w)}] {w.origin} → {w.destination} ({dest_info['city']} {dest_info['flag']}) | "
                f"{shared.schedule_text(w)} | "
                f"{w.label or '라벨 없음'}"
            )
            watch_map[desc] = w
            if clone_id and w.id == clone_id:
                default_idx = idx

        selected_desc = st.selectbox(
            "복제할 기준 조건 선택",
            options=list(watch_map.keys()),
            index=default_idx,
            help="이 조건의 여행 기간, 출발/귀국 시간대, 인원, 경유 조건이 복제 대상에 그대로 적용됩니다.",
            key="clone_base_select",
        )
        base_w = watch_map[selected_desc]
        st.session_state["selected_clone_watch_id"] = base_w.id

        # 기준 조건 요약 카드 (고품질 글래스 카드 뷰)
        base_dest_info = shared.airport_info(base_w.destination)
        dep_win = shared.time_window_parts(base_w.dep_hour_from, base_w.dep_hour_to)
        ret_win = shared.time_window_parts(base_w.ret_hour_from, base_w.ret_hour_to) if base_w.trip_type == "round" else "-"
        stops_str = shared.stops_text(base_w)
        target_str = f"{base_w.target_price:,.0f} {base_w.currency}" if base_w.target_price else "하락률 규칙만 적용"

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #f8fbfe 0%, #edf4fc 100%);
                        border: 1px solid #c9d8ea; border-radius: 12px; padding: 16px 20px;
                        margin-top: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(19,27,48,0.04);">
              <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #dbe6f3; padding-bottom:10px; margin-bottom:12px;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="background:var(--navy); color:#fff; font-size:11px; font-weight:700; padding:3px 8px; border-radius:4px; font-family:var(--font-mono);">
                    기준 조건
                  </span>
                  <span style="font-size:16px; font-weight:700; color:var(--ink);">
                    {base_w.origin} → {base_w.destination} ({base_dest_info['city']} {base_dest_info['flag']})
                  </span>
                </div>
                <div style="font-size:12.5px; font-weight:600; color:#475569; background:#fff; padding:3px 10px; border-radius:12px; border:1px solid #dbe6f3;">
                  🏷️ {html.escape(base_w.label or '라벨 미지정')}
                </div>
              </div>
              <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px; font-size:12.5px;">
                <div>📅 <b>일정:</b> <span class="mono" style="color:var(--navy);font-weight:600;">{shared.schedule_text(base_w)}</span></div>
                <div>✈️ <b>유형:</b> {'왕복' if base_w.trip_type == 'round' else '편도'} · 성인 {base_w.adults}명</div>
                <div>⏰ <b>가는편 시간:</b> {dep_win}</div>
                <div>⏰ <b>오는편 시간:</b> {ret_win}</div>
                <div>🔄 <b>경유 필터:</b> {stops_str}</div>
                <div>🎯 <b>목표가:</b> <span class="mono" style="font-weight:600;">{target_str}</span></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --------------------------------------------------------
        # 1. 대상 공항 선택
        # --------------------------------------------------------
        st.markdown("##### 1. 새로 추가할 도착 여행지(공항) 선택")

        # 빠른 추천 프리셋 버튼 (2행 그리드로 가독성 및 터치 영역 강화)
        st.caption("⚡ **원클릭 빠른 프리셋 추가** (버튼을 누르면 아래 선택 목록에 즉시 추가됩니다):")
        presets = shared.get_popular_region_presets()
        preset_items = list(presets.items())

        # 4열 그리드로 정돈
        pr_cols = st.columns(4)
        for pidx, (pname, pcodes) in enumerate(preset_items):
            col_target = pr_cols[pidx % 4]
            short_name = pname.split(" (")[0]
            if col_target.button(short_name, key=f"preset_btn_{pidx}", use_container_width=True):
                cur_selected = list(st.session_state.get("clone_dest_multisel", []))
                added_count = 0
                for c in pcodes:
                    if c != base_w.destination:
                        ch = shared.choice_from_code(c)
                        if ch not in cur_selected and not ch.startswith("DIRECT"):
                            cur_selected.append(ch)
                            added_count += 1
                st.session_state["clone_dest_multisel"] = cur_selected
                st.toast(f"'{short_name}' 공항들을 목록에 추가하였습니다.")
                st.rerun()

        # 전체 공항 선택 옵션
        all_choices = [c for c in shared.get_airport_choices() if not c.startswith("DIRECT")]
        base_choice = shared.choice_from_code(base_w.destination)
        avail_choices = [c for c in all_choices if c != base_choice and not c.startswith(base_w.origin)]

        selected_dest_choices = st.multiselect(
            "도착 공항 다중 선택 (여러 곳 선택 가능)",
            options=avail_choices,
            default=st.session_state.get("clone_dest_multisel", []),
            key="clone_dest_multisel",
            placeholder="추가할 공항 또는 도시명을 검색하여 선택하세요 (예: 나트랑, 방콕, 후쿠오카, 타이베이...)",
        )

        direct_input = st.text_input(
            "목록에 없는 IATA 3자리 공항 코드가 있다면 쉼표(,)로 직접 입력 (선택)",
            placeholder="예) CNX, USM",
            key="clone_direct_dest",
            help="쉼표로 구분하여 여러 공항 코드를 입력할 수 있습니다.",
        )

        dest_codes: list[str] = []
        for ch in selected_dest_choices:
            code = shared.code_from_choice(ch)
            if code and code not in dest_codes and code != base_w.destination:
                dest_codes.append(code)

        if direct_input.strip():
            for raw in direct_input.split(","):
                c = raw.strip().upper()
                if re.fullmatch(r"[A-Z]{3}", c) and c not in dest_codes and c != base_w.destination and c != base_w.origin:
                    dest_codes.append(c)

        # --------------------------------------------------------
        # 2. 복제 옵션 설정
        # --------------------------------------------------------
        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
        st.markdown("##### 2. 복제 옵션 설정")
        ocol1, ocol2 = st.columns(2)

        with ocol1:
            price_mode = st.radio(
                "목표가 적용 방식",
                options=["기준 조건과 동일하게 유지", "목표가 없이 하락률/백분위만 적용", "새 목표가 일괄 지정"],
                index=0 if base_w.target_price else 1,
                key="clone_price_mode",
            )
            custom_target = 0.0
            if price_mode == "새 목표가 일괄 지정":
                custom_target = st.number_input(
                    f"일괄 목표가 ({base_w.currency})",
                    min_value=0.0,
                    step=10000.0,
                    value=float(base_w.target_price or 0.0),
                    key="clone_custom_target",
                )

        with ocol2:
            label_rule = st.radio(
                "라벨(이름) 자동 생성 방식",
                options=["도시명에 맞게 자동 스마트 치환 (추천)", "직접 접두사 지정", "도시명만 간결하게"],
                index=0,
                key="clone_label_rule",
                help="스마트 치환: '추석 다낭' 기준이면 '추석 나트랑', '추석 방콕'으로 자동 변경됩니다.",
            )
            custom_prefix = ""
            if label_rule == "직접 접두사 지정":
                custom_prefix = st.text_input(
                    "라벨 접두사",
                    value=base_w.label or "여행",
                    key="clone_custom_prefix",
                )

        # --------------------------------------------------------
        # 3. 등록 예정 목록 및 일괄 등록
        # --------------------------------------------------------
        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
        if dest_codes:
            st.markdown(f"##### 3. 등록 예정 감시 조건 목록 ({len(dest_codes):,}건)")

            candidates_to_add: list[shared.WatchCondition] = []
            preview_rows = []

            for dcode in dest_codes:
                dinfo = shared.airport_info(dcode)
                city_str = f"{dinfo['city']} {dinfo['flag']}"

                if label_rule == "도시명에 맞게 자동 스마트 치환 (추천)":
                    cloned_label = shared.suggest_cloned_label(base_w.label, base_w.origin, base_w.destination, dcode)
                elif label_rule == "직접 접두사 지정":
                    cloned_label = f"{custom_prefix.strip()} · {dinfo['city']}"
                else:
                    cloned_label = f"{dinfo['city']} 감시"

                if price_mode == "기준 조건과 동일하게 유지":
                    tp = base_w.target_price
                elif price_mode == "목표가 없이 하락률/백분위만 적용":
                    tp = None
                else:
                    tp = float(custom_target) if custom_target > 0 else None

                dup = shared.find_duplicate_watch(
                    registered,
                    base_w.origin,
                    dcode,
                    base_w.depart_date,
                    base_w.trip_type,
                    base_w.return_date,
                )

                status = "✅ 등록 가능" if dup is None else f"⚠️ 이미 등록됨 ({shared.watch_code(dup)})"
                price_display = f"{tp:,.0f} {base_w.currency}" if tp else "하락률 규칙만"

                preview_rows.append({
                    "노선": f"{base_w.origin} → {dcode}",
                    "여행지": city_str,
                    "라벨": cloned_label,
                    "목표가": price_display,
                    "상태": status,
                    "valid": dup is None,
                })

                if dup is None:
                    new_watch = shared.clone_watch_for_destination(
                        base=base_w,
                        new_dest=dcode,
                        new_label=cloned_label,
                        new_target_price=tp,
                    )
                    candidates_to_add.append(new_watch)

            df_preview = pd.DataFrame([
                {
                    "노선": r["노선"],
                    "여행지": r["여행지"],
                    "라벨": r["라벨"],
                    "목표가": r["목표가"],
                    "상태": r["상태"],
                }
                for r in preview_rows
            ])
            st.dataframe(df_preview, use_container_width=True, hide_index=True)

            valid_count = len(candidates_to_add)
            skipped_count = len(dest_codes) - valid_count

            if skipped_count > 0:
                st.warning(f"선택한 {len(dest_codes)}곳 중 {skipped_count}곳은 이미 동일한 조건으로 등록되어 있어 자동으로 제외됩니다.")

            b1, b2, _ = st.columns([2.2, 1.2, 2.6])
            if b1.button(
                f"선택한 {valid_count:,}개 공항에 같은 조건으로 일괄 등록",
                type="primary",
                use_container_width=True,
                disabled=(valid_count == 0),
                key="btn_execute_clone",
            ):
                if candidates_to_add:
                    def _bulk_clone(dbase, _watches=tuple(candidates_to_add)):
                        for w in _watches:
                            dbase.add_watch(w)

                    shared.edit_with_sync(
                        _bulk_clone,
                        f"feat: [{base_w.destination}] 기준 {len(candidates_to_add)}개 공항 감시 조건 일괄 복제 등록",
                    )
                    st.session_state.pop("clone_dest_multisel", None)
                    st.session_state.pop("clone_direct_dest", None)
                    st.toast(f"감시 조건 {len(candidates_to_add):,}건을 성공적으로 등록하였습니다!")
                    st.success(
                        f"🎉 **{len(candidates_to_add):,}건의 감시 조건이 성공적으로 추가되었습니다.** "
                        f"GitHub Actions 크론이 자동으로 가격을 추적하며, [조건 관리](/watches)에서 확인할 수 있습니다."
                    )
                    st.rerun()

            if b2.button("선택 비우기", use_container_width=True, key="btn_clear_clone"):
                st.session_state.pop("clone_dest_multisel", None)
                st.session_state.pop("clone_direct_dest", None)
                st.rerun()

        else:
            st.info("👆 위에서 새로 추가할 여행지 공항을 1개 이상 선택해 주십시오. (위의 빠른 프리셋 버튼을 누르면 원클릭으로 채워집니다)")


# ===========================================================================
# 3. 상세 폼 직접 입력
# ===========================================================================
elif cur_mode == "📝 상세 직접 입력":
    shared.section("상세 입력")
    st.caption("항목별로 조건을 직접 지정하여 등록합니다. 여러 도착 공항을 함께 등록할 수도 있습니다.")

    airport_choices = shared.get_airport_choices()

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
            "도착 공항 (주 목적지)",
            airport_choices,
            index=dest_idx,
            key="f_dest_sel",
            help="한글 도시명이나 IATA 3자리 코드로 검색하여 선택하세요.",
        )

        direct_orig = ""
        direct_dest = ""
        if origin_sel.startswith("DIRECT") or dest_sel.startswith("DIRECT"):
            dcol1, dcol2 = st.columns(2)
            if origin_sel.startswith("DIRECT"):
                direct_orig = dcol1.text_input("출발 공항 IATA 3글자 직접 입력", value=cur_origin_code if cur_origin_choice == "DIRECT · 직접 입력" else "", key="f_orig_direct").upper().strip()
            if dest_sel.startswith("DIRECT"):
                direct_dest = dcol2.text_input("도착 공항 IATA 3글자 직접 입력", value=cur_dest_code if cur_dest_choice == "DIRECT · 직접 입력" else "", key="f_dest_direct").upper().strip()

        # 추가 도착 공항 (동일 일정 함께 등록)
        extra_choices = [c for c in airport_choices if not c.startswith("DIRECT") and c != dest_sel and not c.startswith("ICN")]
        extra_dests = st.multiselect(
            "추가 도착 공항 (선택: 동일 일정으로 함께 등록할 다른 여행지가 있다면 선택)",
            options=extra_choices,
            key="f_extra_dests",
            help="선택한 공항들도 같은 일정과 조건으로 함께 일괄 등록됩니다.",
        )

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
        _trip_v = "round" if trip == "왕복" else "one-way"
        _dup = _find_same(origin, dest, depart.isoformat(), _trip_v,
                          ret.isoformat() if (trip == "왕복" and ret) else None)
        if _dup is not None:
            errors.append(
                f"같은 노선·날짜의 조건이 이미 있습니다: {shared.watch_code(_dup)} "
                f"({_dup.label or _dup.route_label}). 조건 관리에서 수정하여 주십시오."
            )
        if errors:
            for e in errors:
                st.error(e)
        else:
            watches_to_add: list[shared.WatchCondition] = []

            # 1) 주 조건 생성
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
            watches_to_add.append(watch)

            # 2) 추가 도착 공항들도 복제 생성
            for ech in extra_dests:
                ecode = shared.code_from_choice(ech)
                if ecode and ecode != dest:
                    edup = _find_same(origin, ecode, depart.isoformat(), _trip_v,
                                      ret.isoformat() if (trip == "왕복" and ret) else None)
                    if edup is None:
                        c_watch = shared.clone_watch_for_destination(
                            base=watch,
                            new_dest=ecode,
                        )
                        watches_to_add.append(c_watch)

            def _bulk_add(d, _ws=tuple(watches_to_add)):
                for w in _ws:
                    d.add_watch(w)

            shared.edit_with_sync(_bulk_add, f"feat: 감시 조건 {len(watches_to_add)}건 추가 [{watch.label or watch.route_label}]")
            st.success(f"감시 조건 {len(watches_to_add):,}건을 성공적으로 등록하였습니다!")
            st.info(
                f"GitHub Actions가 {shared.CHECK_INTERVAL_TEXT}마다 가격을 확인합니다. "
                "항공편 조회 페이지에서 즉시 조회도 가능합니다."
            )
            for k in ("f_label", "f_origin", "f_dest", "f_target", "nl_drafts", "f_origin_choice", "f_dest_choice", "f_extra_dests"):
                st.session_state.pop(k, None)
            st.rerun()
