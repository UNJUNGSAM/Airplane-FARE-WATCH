"""가격 추이 페이지 - 최근 30일 최저가 이력과 판정 규칙."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent.parent
for _p in (str(HERE), str(ROOT)):
    while _p in sys.path:  # 루트가 항상 앞서도록 재정렬
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import altair as alt
import pandas as pd
import streamlit as st

import shared

# 실행 중인 shared 모듈이 이 페이지가 기대하는 버전인지 확인한다.
# (배포 직후 Streamlit이 페이지만 새로 읽고 모듈은 예전 것을 물고 있는 경우
#  원인 모를 AttributeError 대신 무엇을 해야 하는지 알려 준다)
_NEEDS_SHARED = "2026-08-28.1"
if getattr(shared, "SHARED_REVISION", "") < _NEEDS_SHARED:
    st.error(
        "**배포된 새 코드가 아직 적용되지 않았습니다.** "
        "**[Manage app] → [⋮] → [Reboot app]** 으로 앱을 완전히 재시작하여 주십시오."
    )
    st.stop()

shared.boot("trend", "가격 추이")

db = shared.get_db()
watches = db.list_watches(active_only=False)

if not watches:
    shared.page_header(
        eyebrow="Price history",
        title="가격 추이",
        desc="표시할 감시 조건이 없습니다.",
        attached=False,
    )
    st.info("먼저 조건 등록 페이지에서 감시 조건을 만들어 주십시오.")
    st.stop()

countries = sorted({shared.airport_info(w.destination)["country"] for w in watches})

shared.page_header(
    eyebrow="Price history",
    title="가격 추이",
    desc="등록된 모든 감시 조건의 가격 변동 추이와 목표가를 한눈에 확인합니다.",
    meta_label="등록 조건",
    meta_value=f"{len(watches):,}건",
)

with shared.util_bar():
    # 30일은 기본 조회 기간이라 요약에서는 '설정 안 함'으로 본다
    with shared.filter_box("trend_search", "trend_country", "trend_period",
                           neutral=("전체", "30일")):
        u1, u2, u3 = st.columns([2.5, 1.8, 2.4], vertical_alignment="bottom")
        sel_search = u1.text_input("검색", placeholder="도시명, 공항, 라벨...", key="trend_search")
        sel_country = u2.selectbox("국가", ["전체"] + countries, key="trend_country")
        sel_period = u3.radio("조회 기간", ["7일", "14일", "30일", "전체"], index=2,
                              horizontal=True, key="trend_period")

    st.markdown(
        '<div style="font-size:12.5px;color:#6c7585;padding:2px 0 4px;">'
        '점선은 설정한 목표가를 나타냅니다.</div>',
        unsafe_allow_html=True,
    )

period_days = {"7일": 7, "14일": 14, "30일": 30, "전체": 9999}.get(sel_period, 30)

# 검색·국가 필터는 shared.watch_matches 로 일원화 (페이지별 복사본 제거)
shown_watches = [w for w in watches if shared.watch_matches(w, sel_search, sel_country)]

if not shown_watches:
    st.info("선택한 필터 조건에 일치하는 감시 조건이 없습니다.")
    st.stop()

INK3, LINE, BLUE, NAVY = "#6c7585", "#dde2e9", "#1380b8", "#243050"
MONO = "IBM Plex Mono, Consolas, monospace"


def _render_trend_card(w):
    hist = db.get_history(w.id, days=period_days)
    stats = db.price_stats(w.id, days=period_days, percentile=w.percentile)
    d = shared.load_watch_data(db, w)
    deal = d["deal"]
    search_url = shared.flights_search_url(w)
    sky_url = shared.skyscanner_search_url(w)

    dest_info = shared.airport_info(w.destination)
    flag = dest_info.get("flag") or "✈️"

    with st.container(key=f"trend_card_{w.id}"):
        # 상단 타이틀 바
        h1, h2 = st.columns([3.5, 1.5], vertical_alignment="center")
        with h1:
            st.markdown(
                f'<div style="font-size:16.5px;font-weight:700;color:#131b30;margin-bottom:4px;">'
                f'<span style="font-size:16px;margin-right:2px;">{flag}</span> '
                f'<span class="mono" style="color:#1380b8;">{shared.watch_code(w)}</span> · '
                f'{w.origin} → {w.destination} · {shared.route_title(w)} '
                f'<span style="font-size:13px;color:#6c7585;font-weight:500;">({shared.schedule_text(w)})</span> '
                f'{shared.deal_badge_html(deal)}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with h2:
            st.markdown(
                f'<div style="display:flex;gap:10px;justify-content:flex-end;align-items:center;">'
                f'<a class="ap-link" href="{search_url}" target="_blank" rel="noopener">구글 항공권 ↗</a>'
                f'<a class="ap-link" href="{sky_url}" target="_blank" rel="noopener">스카이스캐너 ↗</a>'
                f'</div>',
                unsafe_allow_html=True,
            )

        if not hist:
            st.markdown(
                '<div class="ap-panel" style="padding:18px 16px;color:#6c7585;font-size:13px;">'
                '아직 가격 데이터가 충분하지 않습니다. 대시보드에서 <b>지금 다시 조회</b>를 누르시면 즉시 기록됩니다.</div>',
                unsafe_allow_html=True,
            )
            return

        df = pd.DataFrame(hist)
        df["checked_at"] = pd.to_datetime(df["checked_at"])
        df = df[["checked_at", "price"]].rename(columns={"checked_at": "시각", "price": "최저가"})

        base = alt.Chart(df).encode(
            x=alt.X("시각:T", title=None,
                    axis=alt.Axis(format="%m-%d", labelAngle=0, tickCount=6, grid=False)),
            y=alt.Y("최저가:Q", title=None,
                    scale=alt.Scale(zero=False, nice=True),
                    axis=alt.Axis(format=",.0f", tickCount=4, gridColor=LINE, gridDash=[2, 3])),
        )
        layers = [
            base.mark_area(color=BLUE, opacity=0.08),
            base.mark_line(color=BLUE, strokeWidth=2, interpolate="monotone"),
        ]
        if w.target_price:
            tdf = pd.DataFrame({"목표가": [float(w.target_price)]})
            layers.append(
                alt.Chart(tdf).mark_rule(color=NAVY, strokeDash=[6, 4], strokeWidth=1.4)
                .encode(y="목표가:Q")
            )
        last_df = df.tail(1)
        layers += [
            alt.Chart(last_df).mark_point(size=100, color=NAVY, filled=True, opacity=1)
            .encode(x="시각:T", y="최저가:Q",
                    tooltip=[alt.Tooltip("시각:T", format="%Y-%m-%d %H:%M"),
                             alt.Tooltip("최저가:Q", format=",.0f")]),
            base.mark_circle(size=60, opacity=0).encode(
                tooltip=[alt.Tooltip("시각:T", format="%Y-%m-%d %H:%M"),
                         alt.Tooltip("최저가:Q", format=",.0f")]),
        ]

        chart = (
            alt.layer(*layers)
            .properties(height=240, width="container")
            .configure_view(strokeWidth=0)
            .configure_axis(labelFont=MONO, labelColor=INK3, labelFontSize=11,
                            domainColor=LINE, tickColor=LINE)
        )

        chart_col, rule_col = st.columns([2.5, 1.0], gap="medium")
        with chart_col:
            st.altair_chart(chart, use_container_width=True)

        with rule_col:
            disc_first = deal.get("discount_first") or 0
            disc_avg = deal.get("discount_avg") or 0
            tp = deal.get("trend_pct")
            trend_cell = ('<b>비교 기준 없음</b>' if tp is None else
                          f'<b class="mono">{"▼" if tp < 0 else "▲"} {abs(tp):.1f}%</b>')
            st.markdown(
                '<div class="ap-slab" style="padding:12px 14px;">'
                f'<div class="kv"><span>판정 결과</span>'
                f'<span class="st">{shared.deal_text(deal)}</span></div>'
                f'<div class="kv"><span>직전 대비</span>{trend_cell}</div>'
                f'<div class="kv"><span>첫 관측가 대비</span>'
                f'<b class="mono">{"▼" if disc_first > 0 else "▲"} {abs(disc_first):.1f}%</b></div>'
                f'<div class="kv"><span>평균 대비</span>'
                f'<b class="mono">{"▼" if disc_avg > 0 else "▲"} {abs(disc_avg):.1f}%</b></div>'
                f'<div class="kv"><span>관측 횟수</span>'
                f'<b class="mono">{stats.get("count", 0):,}회</b></div>'
                '</div>',
                unsafe_allow_html=True,
            )

        figures = [
            ("현재가", shared.num(stats.get("last")), True),
            (f"{sel_period} 최저", shared.num(stats.get("min")), True),
            (f"{sel_period} 평균", shared.num(stats.get("avg")), True),
            ("목표가",
             shared.num(w.target_price) if w.target_price
             else '<span class="ap-figure-none">미설정</span>',
             bool(w.target_price)),
        ]
        st.markdown(
            '<div class="ap-panel" style="margin-top:6px;margin-bottom:24px;"><div class="ap-figures">'
            + "".join(
                f'<div class="ap-figure"><div class="k">{k}</div>'
                f'<div class="v">{v}'
                + (f'<span class="cur">{w.currency}</span>' if show_cur else "")
                + '</div></div>'
                for k, v, show_cur in figures
            )
            + "</div></div>",
            unsafe_allow_html=True,
        )


for w in shown_watches:
    _render_trend_card(w)

