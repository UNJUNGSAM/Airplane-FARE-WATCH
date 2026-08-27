"""알림 기록 페이지 - 발송된 핫딜 알림 이력."""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent.parent
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd
import streamlit as st

import shared

shared.boot("alerts", "알림 기록")

db = shared.get_db()
notis = db.list_notifications(limit=200)
routes = sorted({str(n["label"] or "-") for n in notis})

shared.page_header(
    eyebrow="Alert log",
    title="알림 발송 기록",
    desc="핫딜로 판정하여 텔레그램으로 발송한 알림의 이력입니다.",
    meta_label="최근 발송",
    meta_value=shared.ts(notis[0]["sent_at"]) if notis else "기록 없음",
)

with shared.util_bar():
    a1, a2, a3, a4 = st.columns([2, 2.2, 1.8, 2], vertical_alignment="bottom")
    sel_route = a1.selectbox("노선 필터", ["전체"] + routes, key="alert_route")
    sel_kw = a2.text_input("판정 사유/키워드 검색", placeholder="예: 목표가, 하락, 백분위...", key="alert_kw")

    df_export = pd.DataFrame(notis) if notis else pd.DataFrame()
    if not df_export.empty:
        csv_data = df_export.to_csv(index=False).encode("utf-8-sig")
        a3.download_button(
            "CSV 다운로드",
            data=csv_data,
            file_name="flight_alerts_log.csv",
            mime="text/csv",
            width="stretch",
        )
    a4.markdown(
        f'<div style="font-size:12.5px;color:#6c7585;padding-bottom:8px;">'
        f'최근 {len(notis):,}건을 표시합니다.</div>',
        unsafe_allow_html=True,
    )

if not notis:
    st.markdown(
        '<div class="ap-panel"><div class="ap-panel-h">알림 기록</div>'
        '<div class="ap-empty">발송된 알림이 없습니다. 핫딜로 판정되면 텔레그램으로 '
        '발송한 뒤 이곳에 기록합니다.</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

kw = (sel_kw or "").strip().lower()
shown = [
    n for n in notis
    if (sel_route == "전체" or str(n["label"] or "-") == sel_route)
    and (not kw or kw in str(n.get("reason") or "").lower() or kw in str(n.get("label") or "").lower())
]

rows = "".join(
    f'<tr><td class="mono">{shared.ts(n["sent_at"])}</td>'
    f'<td><b>{html.escape(str(n["label"] or "-"))}</b></td>'
    f'<td class="num mono" style="font-weight:600;color:#131b30;">{shared.num(n["price"])}</td>'
    f'<td>{html.escape(str(n["reason"] or "-"))}</td></tr>'
    for n in shown
)
st.markdown(
    f'<div class="ap-panel"><div class="ap-panel-h">알림 기록'
    f'<span class="n">{len(shown):,}건</span></div>'
    f'<table class="ap-simple"><thead><tr>'
    f'<th style="width:160px;">발송 시각</th><th style="width:200px;">노선</th>'
    f'<th class="num" style="width:120px;">가격</th>'
    f'<th>판정 사유</th></tr></thead>'
    f'<tbody>{rows}</tbody></table></div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="ap-note">누적 {len(notis):,}건의 알림을 텔레그램으로 발송하였습니다. '
    '판정 기준은 조건별 목표가·하락률·백분위 규칙을 따릅니다.</div>',
    unsafe_allow_html=True,
)

