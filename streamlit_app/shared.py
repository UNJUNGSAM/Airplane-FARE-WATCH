"""감시 콘솔 페이지들이 공유하는 공통 코드.

디자인 시스템(콘솔 UI), 캐시 리소스, GitHub 동기화, UI 헬퍼를 포함한다.
데이터·판정 로직은 app/ 패키지에 있으며 이 모듈은 표현 계층만 담당한다.
"""
from __future__ import annotations

import html
import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
# ROOT가 HERE보다 먼저 검색되어야 `import app`이 루트의 app/ 패키지를 가리킵니다
for _p in (str(_HERE), str(_ROOT)):
    while _p in sys.path:  # 루트가 항상 앞서도록 재정렬
        sys.path.remove(_p)
    sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Streamlit 모듈 감시 범위 확장 (중요)
#
# Streamlit의 LocalSourcesWatcher는 "메인 스크립트 폴더(streamlit_app/) 하위"이거나
# "PYTHONPATH 안에 있는" 모듈만 감시하고, 그 파일이 바뀔 때만 sys.modules에서
# 지워 다시 임포트한다. app/ 은 streamlit_app/ 의 형제 폴더라 어느 쪽에도 걸리지
# 않아, 저장소를 새로 pull 해도 프로세스가 살아 있는 한 예전 코드가 그대로 남았다.
# (Secrets를 저장해도 계속 "미설정"으로 뜨던 장애의 진짜 원인)
# PYTHONPATH에 저장소 루트를 넣어 app/ 도 감시 대상이 되게 한다.
# ---------------------------------------------------------------------------
_pypath = os.environ.get("PYTHONPATH", "")
if str(_ROOT) not in _pypath.split(os.pathsep):
    os.environ["PYTHONPATH"] = (
        f"{_ROOT}{os.pathsep}{_pypath}" if _pypath else str(_ROOT)
    )

import pandas as pd  # noqa: E402,F401  (페이지에서 재사용)
import streamlit as st  # noqa: E402

from app import config, github_sync  # noqa: E402
from app.airports import (  # noqa: E402
    airport_info,
    choice_from_code,
    code_from_choice,
    destination_label,
    get_airport_choices,
)
from app.database import Database  # noqa: E402
from app.models import WatchCondition  # noqa: E402
from app.services import notifier  # noqa: E402,F401
from app.services.checker import check_watch, run_full_cycle  # noqa: E402,F401
from app.services.deal import deal_status  # noqa: E402
from app.services.gemini_service import GeminiService  # noqa: E402
from app.providers.google_flights import GoogleFlightsProvider  # noqa: E402

# 각 페이지가 "이 버전 이상의 shared 가 필요하다"고 선언할 때 쓰는 표식.
# shared.py에 새 함수를 추가하면 이 값을 올리고, 페이지의 _NEEDS_SHARED 도 함께 올린다.
# (Streamlit Cloud는 페이지 스크립트만 디스크에서 다시 읽고 import된 모듈은
#  프로세스에 남겨 두는 일이 있어, 버전이 어긋나면 원인 모를 AttributeError가 난다)
# 비교는 문자열 사전순이므로 반드시 "YYYY-MM-DD.N" 꼴을 유지하고, 하루에 10회를
# 넘길 일이 생기면 N을 01, 02 처럼 두 자리로 적는다 (".10" < ".9" 함정 방지).
SHARED_REVISION = "2026-08-28.2"

CURRENCIES = ["KRW", "USD", "JPY", "EUR", "TWD", "THB", "SGD", "HKD", "AUD", "GBP"]
HOUR_OPTIONS = ["제한없음"] + [f"{h:02d}시" for h in range(24)]
STOP_OPTIONS = ["전체", "직항만", "직항+1회경유"]
DEFAULT_DROP, DEFAULT_PCTILE, DEFAULT_COOLDOWN = 15.0, 10.0, 6.0
LOGO_URL = "https://images.kiwi.com/airlines/64/{code}.png"

PRODUCT_NAME = "Airplane Fare Watch"
PRODUCT_SUB = "항공권 가격 감시 콘솔"
PRODUCT_SHORT = "Airplane Fare Watch"
CHECK_INTERVAL_TEXT = "30분"

# 상단 헤더 탭 (키, 표시명, 스크립트 경로)
NAV: list[tuple[str, str, str]] = [
    ("home", "대시보드", "app.py"),
    ("register", "조건 등록", "pages/2_register.py"),
    ("watches", "조건 관리", "pages/4_watches.py"),
    ("flights", "항공편 조회", "pages/1_flights.py"),
    ("trend", "가격 추이", "pages/3_trend.py"),
    ("alerts", "알림 기록", "pages/5_alerts.py"),
    ("settings", "설정", "pages/6_settings.py"),
]

# 판정 레벨 → (배지 클래스, 상태 점 클래스)
LEVEL_STYLE = {
    "best": ("ok", "dot-ok"),
    "good": ("teal", "dot-teal"),
    "normal": ("mute", "dot-idle"),
    "high": ("warn", "dot-warn"),
    "unknown": ("mute", "dot-idle"),
}


# ---------------------------------------------------------------------------
# 디자인 시스템
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --bg: #f5f7f9;
  --surface: #ffffff;
  --surface-2: #eceff3;
  --ink: #131b30;
  --ink-2: #363e4d;
  --ink-3: #6c7585;
  --navy: #243050;
  --blue: #1380b8;
  --teal: #44beaf;
  --ok: #1f9d6b;
  --warn: #c98a16;
  --danger: #d34646;
  --line: #dde2e9;
  --shadow: 0 2px 8px rgba(19,27,48,.08);
  --r-ctl: 5px;
  --r-box: 12px;
  --font-sans: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont,
               'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Consolas, monospace;
}

html, body, .stApp {
  font-family: var(--font-sans) !important;
  background: var(--bg);
  color: var(--ink-2);
  -webkit-font-smoothing: antialiased;
}
.stApp a { color: var(--navy); }

/* Streamlit 기본 크롬 정리 --------------------------------------------- */
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu, footer { display: none !important; }
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] { display: none !important; }

/* Streamlit 기본 헤더 및 최상단 빈 여백 완전 제거 */
header[data-testid="stHeader"],
[data-testid="stDecoration"] {
  display: none !important;
}

section[data-testid="stMain"] .block-container,
[data-testid="stMainBlockContainer"],
.block-container {
  padding-top: 8px !important;
  padding-left: 18px !important;
  padding-right: 18px !important;
  padding-bottom: 24px !important;
  max-width: 1440px !important;
  margin-top: 0 !important;
}

.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  word-break: keep-all;
}

/* 상단 네비게이션 바 ---------------------------------------------------- */
.st-key-ap_nav {
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  padding: 0 16px;
  height: 42px !important;
  display: flex; align-items: center;
  margin-bottom: 6px;
}
.st-key-ap_nav [data-testid="stElementContainer"],
.st-key-ap_nav [data-testid="stMarkdown"] { margin: 0 !important; }
.st-key-ap_nav [data-testid="stMarkdownContainer"] p { margin: 0 !important; }

.ap-brand { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.ap-mark {
  width: 22px; height: 22px; border-radius: 4px; background: var(--navy);
  display: grid; place-items: center; flex: 0 0 auto;
}
.ap-mark svg { width: 14px; height: 14px; }
.ap-brand-name {
  font-size: 13.5px; font-weight: 700; color: var(--ink);
  letter-spacing: -.01em; white-space: nowrap;
}

.st-key-ap_tabs {
  flex-direction: row !important;
  align-items: center; justify-content: center;
  gap: 0 !important; flex-wrap: nowrap;
}
.st-key-ap_tabs > [data-testid="stElementContainer"] {
  width: auto !important; height: 42px !important;
  display: flex; align-items: center;
}
.st-key-ap_tabs [data-testid="stMarkdown"],
.st-key-ap_tabs [data-testid="stMarkdownContainer"],
.st-key-ap_tabs [data-testid="stPageLink"] {
  height: 42px; display: flex; align-items: center; margin: 0 !important;
}
.st-key-ap_tabs [data-testid="stPageLink"] a {
  height: 42px; display: flex; align-items: center;
  padding: 0 10px !important; border-radius: 0 !important;
  border-bottom: 2px solid transparent;
  background: transparent !important; text-decoration: none !important;
}
.st-key-ap_tabs [data-testid="stPageLink"] a:hover { background: transparent !important; }
.st-key-ap_tabs [data-testid="stPageLink"] a p,
.st-key-ap_tabs [data-testid="stPageLink"] a span {
  font-size: 12.5px !important; font-weight: 600 !important;
  color: var(--ink-3) !important; margin: 0 !important; white-space: nowrap;
}
.st-key-ap_tabs [data-testid="stPageLink"] a:hover p,
.st-key-ap_tabs [data-testid="stPageLink"] a:hover span { color: var(--ink) !important; }
.ap-tab-active {
  height: 42px; display: flex; align-items: center; padding: 0 10px;
  border-bottom: 2px solid var(--blue);
  font-size: 12.5px; font-weight: 700; color: var(--ink); white-space: nowrap;
}

.ap-status { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.ap-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 8px; border: 1px solid var(--line); border-radius: var(--r-ctl);
  font-size: 11px; font-weight: 600; color: var(--ink-2); white-space: nowrap;
}
.ap-user { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.ap-user .nm { font-size: 11.5px; color: var(--ink-3); font-weight: 600; }
.ap-avatar {
  width: 22px; height: 22px; border-radius: var(--r-ctl); background: var(--surface-2);
  color: var(--ink-2); display: grid; place-items: center;
  font-size: 10px; font-weight: 700; font-family: var(--font-mono);
}

.ap-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex: 0 0 auto; }
.dot-ok { background: var(--ok); }
.dot-warn { background: var(--warn); }
.dot-danger { background: var(--danger); }
.dot-idle { background: #a7b0bd; }
.dot-teal { background: var(--teal); }

/* 페이지 타이틀 바 (초슬림 1줄 인라인) -------------------------------- */
.ap-titlebar {
  background: linear-gradient(135deg, #ffffff 0%, #f8fbff 65%, #edf4fc 100%);
  border: 1px solid var(--line);
  border-radius: var(--r-box) var(--r-box) 0 0;
  padding: 7px 16px 6px;
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
}
.ap-titlebar.solo { border-radius: var(--r-box); margin-bottom: 6px; }
.ap-title-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ap-eyebrow-badge {
  font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
  font-weight: 700; color: #fff; background: var(--navy); padding: 2px 7px;
  border-radius: 3px; font-family: var(--font-mono);
}
.ap-title {
  font-size: 15.5px; font-weight: 700; color: var(--ink);
  letter-spacing: -.01em; margin: 0; display: inline-flex; align-items: center; gap: 6px;
}
.ap-desc-inline { font-size: 12px; color: var(--ink-3); font-weight: 400; margin: 0; }
.ap-titlebar-side { display: flex; align-items: center; gap: 12px; flex: 0 0 auto; }
.ap-metablock-inline { font-size: 11.5px; color: var(--ink-3); display: flex; align-items: center; gap: 6px; }
.ap-metablock-inline .k { font-weight: 500; }
.ap-metablock-inline .v { font-weight: 600; color: var(--ink); }
.ap-cta {
  display: inline-flex; align-items: center;
  background: var(--blue); color: #fff !important; text-decoration: none !important;
  border-radius: var(--r-ctl); padding: 4px 10px;
  font-size: 11.5px; font-weight: 600; white-space: nowrap;
}
.ap-cta:hover { background: #10709f; color: #fff !important; }

/* 유틸리티 바 (Streamlit 위젯 수용) ------------------------------------- */
.st-key-ap_util {
  background: var(--surface-2);
  border: 1px solid var(--line); border-top: none;
  border-radius: 0 0 var(--r-box) var(--r-box);
  padding: 5px 14px !important;
  margin-bottom: 8px;
}
.st-key-ap_util [data-testid="stHorizontalBlock"] { align-items: flex-end; }
.st-key-ap_util [data-testid="stElementContainer"] { margin-bottom: 0 !important; }

/* 접히는 필터 묶음 - 모바일에서 입력칸이 세로로 길게 쌓이는 것을 막는다 */
.st-key-ap_filterbox { margin-bottom: 6px; }
.st-key-ap_filterbox [data-testid="stExpander"] details {
  border: 1px solid var(--line) !important;
  border-radius: 6px !important;
  background: var(--surface) !important;
}
.st-key-ap_filterbox [data-testid="stExpander"] summary {
  padding: 5px 10px !important;
  min-height: 0 !important;
}
.st-key-ap_filterbox [data-testid="stExpander"] summary p,
.st-key-ap_filterbox [data-testid="stExpander"] summary span {
  font-size: 12.5px !important; font-weight: 600 !important;
  color: var(--ink-2) !important; margin: 0 !important;
}
.st-key-ap_filterbox [data-testid="stExpander"] details > div { padding: 4px 10px 8px !important; }

/* 지표 타일 (초슬림) --------------------------------------------------- */
.ap-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 8px; }
.ap-tile {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px 12px; box-shadow: 0 1px 2px rgba(19,27,48,.03);
  display: flex; align-items: center; justify-content: space-between;
}
.ap-tile-left { line-height: 1.2; }
.ap-tile .k { font-size: 11px; color: var(--ink-3); font-weight: 600; }
.ap-tile .s { font-size: 10px; color: #8a94a6; margin-top: 1px; }
.ap-tile .v {
  font-family: var(--font-mono); font-size: 18px; font-weight: 700;
  color: var(--ink); letter-spacing: -.02em; text-align: right;
}
.ap-tile .v .u {
  font-family: var(--font-sans); font-size: 11px; color: var(--ink-3);
  font-weight: 600; margin-left: 2px;
}

/* 본문 + 우측 레일 ------------------------------------------------------ */
.ap-layout {
  display: grid; grid-template-columns: minmax(0, 1fr) 310px;
  gap: 14px; align-items: start; margin-top: 10px;
}
.ap-rail { display: flex; flex-direction: column; gap: 14px; }

.ap-panel {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-box); box-shadow: var(--shadow); overflow: hidden;
}
.ap-panel-h {
  padding: 12px 16px; background: var(--surface-2);
  border-bottom: 1px solid var(--line);
  font-size: 12.5px; font-weight: 700; color: var(--ink);
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.ap-panel-h .n { font-size: 11.5px; color: var(--ink-3); font-weight: 600; }
.ap-panel-b { padding: 4px 16px 10px; }
.ap-empty { padding: 18px 16px; font-size: 13px; color: var(--ink-3); line-height: 1.6; }

.ap-noti { padding: 11px 0; border-bottom: 1px solid var(--line); }
.ap-noti:last-child { border-bottom: none; }
.ap-noti .t { font-size: 11.5px; color: var(--ink-3); }
.ap-noti .l {
  font-size: 13px; font-weight: 600; color: var(--ink); margin-top: 3px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ap-noti .p { font-size: 12.5px; color: var(--ink-2); margin-top: 3px; font-weight: 600; }

.ap-slab { background: var(--navy); border-radius: var(--r-box); padding: 17px 18px 15px; color: #dfe4ee; }
.ap-slab h4 {
  color: #fff; font-size: 12px; font-weight: 700; margin: 0 0 6px; letter-spacing: .02em;
}
.ap-slab .kv {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,.12); font-size: 12.5px;
}
.ap-slab .kv:last-child { border-bottom: none; }
.ap-slab .kv b { color: #fff; font-weight: 600; }
.ap-slab .kv .st { display: inline-flex; align-items: center; gap: 7px; color: #fff; font-weight: 600; }

/* 데이터 표 ------------------------------------------------------------ */
.ap-table {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-box); box-shadow: var(--shadow); overflow: hidden;
}
.ap-thead, .ap-row {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr) 105px 120px 95px 110px;
  align-items: center; gap: 14px; padding: 0 18px;
}
.ap-thead {
  height: 38px; background: var(--surface-2); border-bottom: 1px solid var(--line);
  font-size: 11.5px; font-weight: 700; color: var(--ink-3); letter-spacing: .01em;
}
.ap-row { padding-top: 14px; padding-bottom: 14px; border-bottom: 1px solid var(--line); }
.ap-row:hover { background: var(--bg); }
.ap-table > .ap-row:last-child,
.ap-panel > .ap-row:last-child { border-bottom: none; }

/* 클릭 가능한 행 아코디언 */
details.ap-details {
  border-bottom: 1px solid var(--line);
  transition: background .15s ease;
}
details.ap-details:last-child { border-bottom: none; }
details.ap-details > summary.ap-row {
  list-style: none;
  cursor: pointer;
  user-select: none;
  border-bottom: none;
}
details.ap-details > summary.ap-row::-webkit-details-marker { display: none; }
details.ap-details > summary.ap-row:hover { background: #f0f4f8; }
details.ap-details[open] > summary.ap-row {
  background: #edf3f9;
  border-bottom: 1px solid var(--line);
}
.ap-detail-body {
  padding: 16px 20px;
  background: #f8fafc;
  border-bottom: 1px solid var(--line);
}

.ap-table > .ap-panel-h { background: var(--surface); }
.ap-group {
  display: flex; align-items: center; gap: 8px; padding: 9px 18px;
  background: #f2f4f7; border-bottom: 1px solid var(--line);
  font-size: 12px; font-weight: 700; color: var(--ink-2);
}
.ap-group .n { color: var(--ink-3); font-weight: 600; }

.ap-route { font-size: 15px; font-weight: 600; color: var(--ink); letter-spacing: .01em; }
.ap-route .arw { color: var(--ink-3); margin: 0 5px; }
.ap-id {
  font-family: var(--font-mono); font-size: 11.5px; font-weight: 500;
  color: var(--ink-3); letter-spacing: .04em; margin-top: 5px;
}
.ap-sub { font-size: 12px; color: var(--ink-3); margin-top: 4px; line-height: 1.5; }
.ap-sub b { color: var(--ink-2); font-weight: 600; }

/* 조건 · 일정 셀 */
.ap-planline { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.ap-plan {
  font-size: 13.5px; font-weight: 700; color: var(--navy); letter-spacing: -.01em;
}
.ap-flight {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  font-size: 12px; margin-top: 7px;
}
.ap-flight .lb { color: var(--ink-3); font-weight: 600; }
.ap-flight .tm { font-size: 13.5px; font-weight: 600; color: var(--ink); }
.ap-flight .tm .arw { color: var(--ink-3); margin: 0 5px; font-weight: 400; }
.ap-flight .tm .pd {
  color: var(--danger); font-size: 10px; font-weight: 700;
  margin-left: 3px; vertical-align: super;
}
.ap-flight .air { color: var(--ink-3); }
.ap-cell-price { text-align: right; }
.ap-price {
  font-family: var(--font-mono); font-size: 20px; font-weight: 600;
  color: var(--ink); white-space: nowrap;
}
.ap-price .cur {
  font-family: var(--font-sans); font-size: 11.5px; color: var(--ink-3);
  font-weight: 600; margin-left: 4px;
}
.ap-cell-verdict { display: flex; justify-content: flex-end; }
.ap-nodata { font-size: 11.5px; color: var(--ink-3); }

.ap-trend { font-size: 12.5px; font-weight: 700; white-space: nowrap; margin-top: 4px; }
.ap-trend.down { color: var(--ok); }
.ap-trend.up { color: var(--danger); }
.ap-trend.flat { color: var(--ink-3); font-weight: 600; }

.ap-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 9px; border-radius: var(--r-ctl);
  font-size: 11.5px; font-weight: 700; line-height: 1.45; white-space: nowrap;
}
.ap-badge.ok { background: rgba(31,157,107,.10); color: #17805a; }
.ap-badge.teal { background: rgba(68,190,175,.18); color: #2c7f76; }
.ap-badge.warn { background: rgba(201,138,22,.13); color: #9c6c11; }
.ap-badge.danger { background: rgba(211,70,70,.10); color: #b73b3b; }
.ap-badge.mute { background: var(--surface-2); color: var(--ink-3); }
.ap-badge.navy { background: var(--navy); color: #fff; }
.ap-badge.line { background: var(--surface); border: 1px solid var(--line); color: var(--ink-3); font-weight: 600; }

.ap-link {
  font-size: 12.5px; font-weight: 600; color: var(--navy) !important;
  text-decoration: none !important; border-bottom: 1px solid var(--line);
}
.ap-link:hover { border-bottom-color: var(--navy); }

/* 항공편 결과 행 -------------------------------------------------------- */
.ap-offers {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-box); box-shadow: var(--shadow); overflow: hidden;
}
.ap-offer {
  display: grid; grid-template-columns: 54px 190px minmax(0, 1fr) 120px 160px;
  align-items: center; gap: 16px; padding: 14px 18px;
  border-bottom: 1px solid var(--line);
}
.ap-offers > .ap-offer:last-child,
.ap-panel > .ap-offer:last-child { border-bottom: none; }
.ap-offer:hover { background: var(--bg); }
.ap-rank {
  font-family: var(--font-mono); font-size: 12px; font-weight: 600;
  color: var(--ink-3); background: var(--surface-2);
  border-radius: var(--r-ctl); padding: 4px 0; text-align: center;
}
.ap-rank.is-best { background: var(--navy); color: #fff; }
.ap-times {
  font-family: var(--font-mono); font-size: 21px; font-weight: 600;
  color: var(--ink); white-space: nowrap; letter-spacing: -.01em;
}
.ap-times .arw { color: var(--ink-3); font-size: 14px; margin: 0 7px; }
.ap-offer .d {
  font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-3);
  font-weight: 500; margin-top: 3px;
}
.ap-air { display: flex; align-items: center; gap: 9px; min-width: 0; }
.ap-air .nm {
  font-size: 13.5px; font-weight: 600; color: var(--ink-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ap-logos { display: inline-flex; gap: 3px; flex: 0 0 auto; }
.ap-logos img {
  border-radius: var(--r-ctl); border: 1px solid var(--line);
  background: #fff; object-fit: contain;
}

/* 좌측 필터 패널 · 차트 카드 -------------------------------------------- */
.st-key-ap_chart {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-box); box-shadow: var(--shadow);
  padding: 16px 18px 10px !important;
}
.st-key-ap_filters {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-box); box-shadow: var(--shadow);
  padding: 16px 16px 18px !important;
}
.ap-panel-title {
  font-size: 11.5px; font-weight: 700; color: var(--ink-3);
  letter-spacing: .02em; margin: 2px 0 8px;
}
.ap-kv {
  display: flex; justify-content: space-between; gap: 10px; padding: 8px 0;
  border-bottom: 1px solid var(--line); font-size: 12.5px; color: var(--ink-3);
}
.ap-kv:last-child { border-bottom: none; }
.ap-kv b { color: var(--ink-2); font-weight: 600; text-align: right; }

/* 차트 하단 요약 -------------------------------------------------------- */
.ap-figures {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  border-top: 1px solid var(--line);
}
.ap-panel > .ap-figures { border-top: none; }
.ap-figure { padding: 14px 18px; border-right: 1px solid var(--line); }
.ap-figure:last-child { border-right: none; }
.ap-figure .k {
  font-size: 11.5px; color: var(--ink-3); font-weight: 700; letter-spacing: .01em;
}
.ap-figure .v {
  font-family: var(--font-mono); font-size: 22px; font-weight: 600;
  color: var(--ink); margin-top: 6px; white-space: nowrap;
}
.ap-figure .v .cur {
  font-family: var(--font-sans); font-size: 11.5px;
  color: var(--ink-3); font-weight: 600; margin-left: 4px;
}
.ap-figure-none { font-family: var(--font-sans); font-size: 16px; color: var(--ink-3); }

/* 일반 표 (알림 기록 등) ------------------------------------------------ */
.ap-simple { width: 100%; border-collapse: collapse; }
.ap-simple th {
  background: var(--surface-2); border-bottom: 1px solid var(--line);
  padding: 10px 16px; text-align: left;
  font-size: 11.5px; font-weight: 700; color: var(--ink-3); letter-spacing: .01em;
}
.ap-simple td {
  padding: 12px 16px; border-bottom: 1px solid var(--line);
  font-size: 13px; color: var(--ink-2); vertical-align: top;
}
.ap-simple tr:last-child td { border-bottom: none; }
.ap-simple tbody tr:hover { background: var(--bg); }
.ap-simple td.num { text-align: right; }

/* Streamlit 위젯 -------------------------------------------------------- */
.stButton > button, .stFormSubmitButton > button, .stLinkButton > a, .stDownloadButton > button {
  border-radius: var(--r-ctl) !important;
  border: 1px solid var(--line) !important;
  background: var(--surface) !important;
  color: var(--ink-2) !important;
  font-weight: 600 !important;
  box-shadow: none !important;
  min-height: 32px !important;
  padding: 3px 12px !important;
  transition: border-color .12s ease, background .12s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover, .stLinkButton > a:hover {
  border-color: #c3cbd6 !important; background: var(--bg) !important; color: var(--ink) !important;
}
.stButton > button p, .stFormSubmitButton > button p, .stLinkButton > a p, .stDownloadButton > button p {
  font-size: 12px !important; font-weight: 600 !important;
}
button[kind="primary"], button[kind="primaryFormSubmit"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--navy) !important; border-color: var(--navy) !important; color: #fff !important;
}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover,
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: #1b2540 !important; border-color: #1b2540 !important; color: #fff !important;
}

.stTextInput input, .stTextArea textarea, .stNumberInput input, .stDateInput input {
  border-radius: var(--r-ctl) !important;
  font-size: 12.5px !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {
  font-size: 12px !important; color: #a1abb8 !important;
}
.stNumberInput input, .stDateInput input { font-family: var(--font-mono) !important; font-size: 12.5px !important; }
[data-baseweb="select"] > div { border-radius: var(--r-ctl) !important; min-height: 32px !important; font-size: 12.5px !important; }
[data-baseweb="input"] { border-radius: var(--r-ctl) !important; min-height: 32px !important; font-size: 12.5px !important; }
[data-testid="stWidgetLabel"] p {
  font-size: 11px !important; font-weight: 600 !important; color: var(--ink-3) !important; margin-bottom: 2px !important;
}


.stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] {
  height: 38px; padding: 0 14px; background: transparent !important;
  border: none; border-bottom: 2px solid transparent; color: var(--ink-3);
}
.stTabs [data-baseweb="tab"] p { font-size: 13px !important; font-weight: 600 !important; }
.stTabs [aria-selected="true"] { border-bottom-color: var(--navy) !important; }
.stTabs [aria-selected="true"] p { color: var(--ink) !important; }
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

[data-testid="stForm"] {
  border: 1px solid var(--line) !important; border-radius: var(--r-box) !important;
  background: var(--surface); padding: 20px 22px !important; box-shadow: var(--shadow);
}
[data-testid="stExpander"] {
  border: 1px solid var(--line) !important; border-radius: var(--r-box) !important;
  background: var(--surface); box-shadow: none; overflow: hidden;
}
[data-testid="stExpander"] summary { font-size: 13.5px; font-weight: 600; color: var(--ink-2); }
[data-testid="stAlert"] { border-radius: var(--r-box) !important; border: 1px solid var(--line) !important; }
[data-testid="stAlert"] p { font-size: 13.5px !important; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: var(--r-box); overflow: hidden; }
[data-testid="stMetric"] {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-box); padding: 14px 18px; box-shadow: var(--shadow);
}
[data-testid="stMetricValue"] { font-family: var(--font-mono) !important; font-size: 24px !important; }
[data-testid="stCaptionContainer"] p { font-size: 12.5px !important; color: var(--ink-3) !important; }
hr { border-color: var(--line) !important; }

.stApp h2, .stApp h3, .stApp h4 { color: var(--ink); letter-spacing: -.015em; font-weight: 700; }
.stApp h4 { font-size: 15px !important; }
.ap-section {
  font-size: 12.5px; font-weight: 700; color: var(--ink-2); letter-spacing: .01em;
  margin: 26px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--line);
}
.ap-note { font-size: 12.5px; color: var(--ink-3); line-height: 1.7; margin-top: 12px; }

/* 반응형 --------------------------------------------------------------- */
@media (max-width: 1180px) {
  .ap-layout { grid-template-columns: minmax(0, 1fr); }
  .ap-rail { flex-direction: row; flex-wrap: wrap; align-items: flex-start; }
  .ap-rail > * { flex: 1 1 280px; }
}
@media (max-width: 1023px) {
  .ap-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ap-figures { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ap-figure:nth-child(2) { border-right: none; }
  .ap-figure:nth-child(3), .ap-figure:nth-child(4) { border-top: 1px solid var(--line); }
  .ap-titlebar { flex-direction: column; align-items: flex-start; gap: 8px; }
  .ap-titlebar-side { width: 100%; justify-content: space-between; align-items: center; }
  .st-key-ap_tabs {
    width: 100%; min-width: 0; overflow-x: auto;
    justify-content: flex-start; scrollbar-width: none;
  }
  .st-key-ap_tabs::-webkit-scrollbar { display: none; }
}
@media (max-width: 900px) {
  section[data-testid="stMain"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
  section[data-testid="stMain"] [data-testid="stColumn"] {
    flex: 1 1 100% !important; width: 100% !important; min-width: 100% !important;
  }
  /* 실제 클래스명은 ap-brand-name 이다. 예전에는 존재하지 않는 ap-brand-text 를
     숨기고 있어서 모바일에서 브랜드명이 그대로 남아 탭과 겹쳤다. */
  .ap-brand-name, .ap-user { display: none; }
  .st-key-ap_nav.st-key-ap_nav [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important; gap: 6px;
  }
  .st-key-ap_nav.st-key-ap_nav [data-testid="stColumn"]:first-child {
    flex: 0 0 32px !important; width: 32px !important; min-width: 32px !important;
  }
  .st-key-ap_nav.st-key-ap_nav [data-testid="stColumn"]:nth-child(2) {
    flex: 1 1 auto !important; width: auto !important;
  }
  .st-key-ap_nav.st-key-ap_nav [data-testid="stColumn"]:last-child {
    flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
  }
  .ap-thead, .ap-row { grid-template-columns: 110px minmax(0, 1fr) 100px 85px; gap: 8px; padding: 10px 12px; }
  .ap-c-spark, .ap-c-verdict { display: none !important; }
  .ap-offer { grid-template-columns: 36px 130px minmax(0, 1fr) 120px; gap: 8px; padding: 10px 12px; }
  .ap-offer .ap-c-stops { display: none !important; }
  .ap-times { font-size: 15px; }
}
@media (max-width: 640px) {
  .block-container { padding-top: 0.4rem !important; padding-left: 8px !important; padding-right: 8px !important; }
  .ap-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .ap-thead, .ap-row { grid-template-columns: minmax(0, 1fr) 90px; gap: 6px; }
  .ap-c-route, .ap-c-spark, .ap-c-verdict { display: none !important; }
  .ap-offer { grid-template-columns: minmax(0, 1fr) 105px; }
  .ap-offer > *:first-child, .ap-offer .ap-c-stops { display: none !important; }
}

</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 캐시된 리소스
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db() -> Database:
    db = Database(config.DB_PATH)
    db.init_schema()
    return db


@st.cache_resource(show_spinner=False)
def _gemini_for(api_key: str) -> GeminiService:
    """API 키별로 인스턴스를 분리해 캐시한다 (키가 바뀌면 새 인스턴스)."""
    return GeminiService()


def get_gemini() -> GeminiService:
    return _gemini_for(config.GEMINI_API_KEY or "")


@st.cache_resource
def get_provider() -> GoogleFlightsProvider:
    return GoogleFlightsProvider()


# ---------------------------------------------------------------------------
# GitHub 동기화
# ---------------------------------------------------------------------------
def _replace_local_db(data: bytes) -> None:
    p = Path(config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(p)


SYNC_MAX_ATTEMPTS = 3


def edit_with_sync(edit_fn, commit_msg: str) -> None:
    """원격 DB 최신본 기준으로 편집 후 GitHub에 커밋 (미설정 시 로컬만 수정).

    동시 수정 대응: 받아온 시점의 blob SHA를 커밋에 함께 넘긴다. 그 사이 다른
    사용자나 Actions 크론이 DB를 커밋했다면 GitHub이 거절하고, 그때는 최신본을
    다시 받아 편집을 처음부터 재적용한다. (예전에는 커밋 직전 SHA를 새로 읽어
    항상 성공시켰기 때문에 남의 변경을 조용히 덮어썼다.)
    """
    if not github_sync.ready() or not hasattr(github_sync, "fetch_remote_db"):
        # 두 번째 조건은 예전 github_sync 모듈이 물려 있는 경우의 방어
        edit_fn(get_db())  # 로컬 전용 모드
        return

    for attempt in range(1, SYNC_MAX_ATTEMPTS + 1):
        remote = github_sync.fetch_remote_db()
        if remote.data is not None:
            _replace_local_db(remote.data)
            get_db.clear()
        elif attempt > 1:
            # 재시도인데 원격 최신본을 받지 못했다면 여기서 멈춰야 한다.
            # 이전 회차의 편집이 로컬에 남아 있으므로, 그 위에 edit_fn을 또
            # 실행하면 INSERT류 편집이 이중으로 적용된다(조건 중복 등록 등).
            st.warning("원격 저장소를 다시 읽지 못해 동기화를 중단하였습니다. "
                       "잠시 후 다시 시도하여 주십시오.")
            return

        edit_fn(get_db())

        try:
            github_sync.commit_db_bytes(
                Path(config.DB_PATH).read_bytes(), commit_msg, expected_sha=remote.sha
            )
            st.toast("GitHub 저장소에 동기화하였습니다.")
            return
        except github_sync.RemoteChanged:
            if attempt >= SYNC_MAX_ATTEMPTS:
                st.warning(
                    "다른 곳(자동 감시 또는 다른 사용자)에서 동시에 변경이 일어나 "
                    f"{SYNC_MAX_ATTEMPTS}회 재시도 후에도 반영하지 못하였습니다. "
                    "잠시 후 다시 시도하여 주십시오."
                )
                return
            st.toast(f"원격이 변경되어 최신본으로 다시 시도합니다. ({attempt}/{SYNC_MAX_ATTEMPTS})")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"GitHub 동기화에 실패하였습니다. 로컬에는 저장되었습니다. ({exc})")
            return


# ---------------------------------------------------------------------------
# 수동 가격 조회의 저장소 동기화
#
# 클라우드의 로컬 파일시스템은 재배포 때마다 저장소 내용으로 교체된다.
# "지금 조회" 류 버튼이 로컬 DB에만 기록하면 그 이력은 다음 배포에서 사라지므로
# (사용자 입장에서는 "분명히 확인했는데 이력에 없다"는 모순), 수동 조회도
# 원격 최신본 위에서 실행하고 결과를 SHA 잠금으로 커밋한다.
#
# 편집(edit_with_sync)과 달리 재시도하지 않는다 - 조회는 건당 수 초가 걸리는
# 비싼 작업이라, 충돌 시 정직하게 알리고 다음 자동 주기에 맡기는 편이 낫다.
# ---------------------------------------------------------------------------
def sync_begin() -> str | None:
    """수동 조회 전에 원격 최신 DB로 로컬을 맞추고 기준 SHA를 반환한다.

    로컬 모드(동기화 미설정)면 None. 원격 파일이 아직 없어도 None이며,
    이때 sync_commit은 신규 생성 경로를 탄다.
    """
    if not github_sync.ready():
        return None
    remote = github_sync.fetch_remote_db()
    if remote.data is not None:
        _replace_local_db(remote.data)
        get_db.clear()
    return remote.sha


def sync_commit(commit_msg: str, base_sha: str | None) -> str:
    """수동 조회 결과 DB를 저장소에 커밋한다.

    Returns:
        "ok"       - 커밋 완료
        "local"    - 동기화 미설정 (로컬에만 저장)
        "conflict" - 그 사이 원격이 변경됨 (자동 감시와 겹침) - 커밋 포기
        "error: …" - 그 외 실패
    """
    if not github_sync.ready():
        return "local"
    try:
        github_sync.commit_db_bytes(
            Path(config.DB_PATH).read_bytes(), commit_msg, expected_sha=base_sha
        )
        return "ok"
    except github_sync.RemoteChanged:
        return "conflict"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


def sync_note(code: str) -> str | None:
    """sync_commit 결과를 사용자 메시지에 덧붙일 문장으로 바꾼다 (없으면 None)."""
    if code == "conflict":
        return ("다만 자동 감시와 시점이 겹쳐 이번 조회 이력은 저장소에 반영되지 "
                f"않았습니다. 다음 자동 주기({CHECK_INTERVAL_TEXT})에 다시 수집됩니다.")
    if code.startswith("error"):
        return f"다만 저장소 반영에는 실패하였습니다. ({code[7:]})"
    return None  # ok / local 은 별도 안내 불필요


# ---------------------------------------------------------------------------
# 접근 제어
# ---------------------------------------------------------------------------
_AUTH_FLAG = "_authenticated"
_AUTH_TOKEN = "_auth_token"
AUTH_TOKEN_TTL_SEC = 12 * 3600


@st.cache_resource(show_spinner=False)
def _auth_tokens() -> dict[str, float]:
    """발급한 접속 토큰 {토큰: 만료시각}. 프로세스 재시작 시 초기화된다."""
    return {}


def _issue_auth_token() -> str:
    """로그인 성공 시 발급. 앱 내부 HTML 링크에 실어 세션 유실을 막는다.

    상단 탭은 st.page_link라 클라이언트 라우팅으로 세션이 유지되지만,
    디자인상 HTML <a>로 만든 링크(로고·조건 수정 등)는 전체 새로고침이 되어
    세션이 새로 만들어진다. 그때마다 비밀번호를 다시 묻지 않도록 한다.
    """
    now = time.time()
    tokens = _auth_tokens()
    for k, exp in list(tokens.items()):  # 만료분 청소
        if exp <= now:
            tokens.pop(k, None)
    tok = secrets.token_urlsafe(24)
    tokens[tok] = now + AUTH_TOKEN_TTL_SEC
    return tok


def _token_valid(tok: str | None) -> bool:
    if not tok:
        return False
    exp = _auth_tokens().get(str(tok))
    return bool(exp and exp > time.time())


def auth_enabled() -> bool:
    """비밀번호 게이트 활성 여부 (예전 config가 물려 있으면 False)."""
    return False if stale_config_reason() else bool(config.auth_enabled())


def config_default(key: str) -> str | None:
    """설정 기본값 (예전 config가 물려 있으면 None)."""
    return None if stale_config_reason() else config.default_for(key)


def auth_qs(prefix: str = "?") -> str:
    """앱 내부 HTML 링크 뒤에 붙일 토큰 쿼리스트링 (비밀번호 미설정 시 빈 문자열)."""
    if not config.auth_enabled():
        return ""
    tok = st.session_state.get(_AUTH_TOKEN)
    return f"{prefix}t={tok}" if tok else ""


# 이 파일이 기대하는 config 모듈의 최소 기능. 없으면 예전 코드가 물려 있는 것이다.
_REQUIRED_CONFIG_ATTRS = ("auth_enabled", "check_password", "default_for", "runtime_info")


def stale_config_reason() -> str | None:
    """실행 중인 config 모듈이 이 코드와 맞지 않으면 사유 문자열, 맞으면 None.

    Streamlit이 app/ 패키지를 다시 적재하지 못한 상태에서도 페이지가 통째로
    죽지 않고, 무엇을 해야 하는지 화면에 알려 주기 위한 안전장치다.
    """
    missing = [a for a in _REQUIRED_CONFIG_ATTRS if not hasattr(config, a)]
    return ", ".join(missing) if missing else None


def authenticated() -> bool:
    """APP_PASSWORD 미설정이면 항상 True (기존 동작), 설정 시 로그인 여부."""
    if stale_config_reason():
        return True  # 잠금 화면에 갇히지 않도록 통과시키고 boot()에서 경고를 띄운다
    if not config.auth_enabled():
        return True
    if st.session_state.get(_AUTH_FLAG):
        return True
    # 전체 새로고침으로 세션이 새로 생겼어도 유효한 토큰이면 통과시킨다
    url_token = st.query_params.get("t")
    if _token_valid(url_token):
        st.session_state[_AUTH_FLAG] = True
        st.session_state[_AUTH_TOKEN] = url_token
        return True
    return False


def require_auth() -> None:
    """비밀번호가 설정되어 있으면 로그인 전까지 페이지 렌더를 중단한다.

    공개 URL에 그대로 떠 있으면 누구나 감시 조건을 추가·삭제하고 텔레그램
    발송까지 시킬 수 있어 최소한의 문지기를 둔다.
    """
    if authenticated():
        return

    st.markdown(
        '<div style="max-width:380px;margin:14vh auto 0;text-align:center;">'
        '<div style="font-size:20px;font-weight:800;color:#131b30;">Airplane Fare Watch</div>'
        '<div style="font-size:13px;color:#6c7585;margin-top:6px;">'
        '접근하려면 비밀번호를 입력하여 주십시오.</div></div>',
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login_form", border=False):
            pw = st.text_input("비밀번호", type="password", label_visibility="collapsed",
                               placeholder="비밀번호")
            ok = st.form_submit_button("입장", type="primary", width="stretch")
        if ok:
            if config.check_password(pw):
                tok = _issue_auth_token()
                st.session_state[_AUTH_FLAG] = True
                st.session_state[_AUTH_TOKEN] = tok
                try:
                    # URL에도 실어 둔다. 브라우저 새로고침(F5)은 새 세션을 만들기
                    # 때문에, URL 토큰이 없으면 새로고침할 때마다 재로그인을
                    # 요구하게 된다.
                    st.query_params["t"] = tok
                except Exception:  # noqa: BLE001 - 구버전 API 등
                    pass
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
    st.stop()


def mask(v: str | None) -> str:
    """비밀값 표시용. 공개 배포 앱이므로 값의 일부도 노출하지 않고 길이만 알린다."""
    if not v:
        return "미설정"
    return f"설정됨 ({len(str(v))}자)"


# ---------------------------------------------------------------------------
# 서식 헬퍼
# ---------------------------------------------------------------------------
def safe_date(value: str | None) -> date | None:
    """'YYYY-MM-DD' 문자열을 date로. 값이 없거나 형식이 깨졌으면 None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def watch_matches(w: WatchCondition, query: str | None, country: str | None = "전체") -> bool:
    """대시보드·추이·조건 관리 페이지가 공유하는 검색/국가 필터.

    같은 규칙이 페이지마다 복사되어 있어 한쪽만 고쳐지는 일이 있었다.
    """
    info = airport_info(w.destination)
    if country and country != "전체" and info["country"] != country:
        return False
    q = (query or "").strip().lower()
    if not q:
        return True
    terms = (
        w.origin, w.destination, w.label or "", w.route_label or "",
        info.get("city") or "", info.get("country") or "",
    )
    return any(q in t.lower() for t in terms)


def num(v: Any, digits: int = 0, dash: str = "—") -> str:
    """천단위 구분 숫자 문자열."""
    if v is None:
        return dash
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return dash


def ts(value: str | None, dash: str = "기록 없음") -> str:
    if not value:
        return dash
    return str(value).replace("T", " ")[:16]


# ---------------------------------------------------------------------------
# 셸 (헤더 · 타이틀 바 · 유틸리티 바)
# ---------------------------------------------------------------------------
_MARK_SVG = (
    '<svg width="17" height="17" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" '
    'aria-hidden="true"><path d="M2.4 13.9 21.2 4.8l-3.4 6.9-4.5 1.1-2.9 5.6-2 .5.4-4.7'
    '-4.7 1.2-1.7-1.5Z" fill="#ffffff"/></svg>'
)


def engine_state() -> dict[str, Any]:
    """감시 파이프라인 연동 상태 요약."""
    tg, gh, gm = config.telegram_ready(), github_sync.ready(), config.gemini_ready()
    base = {"telegram": tg, "github": gh, "gemini": gm}
    if tg and gh:
        return {**base, "dot": "dot-ok", "label": "감시 가동", "ready": True}
    if tg or gh:
        return {**base, "dot": "dot-warn", "label": "일부 미연동", "ready": False}
    return {**base, "dot": "dot-idle", "label": "로컬 모드", "ready": False}


def render_header(active: str) -> None:
    """상단 고정 헤더 (로고 · 페이지 탭 · 감시 상태 · 사용자)."""
    eng = engine_state()
    with st.container(key="ap_nav"):
        left, mid, right = st.columns([3.4, 6.0, 2.6], vertical_alignment="center")
        with left:
            st.markdown(
                # HTML 링크는 전체 새로고침이라 세션이 새로 만들어진다.
                # auth_qs()로 접속 토큰을 실어 재로그인을 요구하지 않게 한다.
                f'<a href="/{auth_qs("?")}" target="_self" class="ap-brand" '
                f'style="text-decoration:none;color:inherit;">'
                f'<span class="ap-mark">{_MARK_SVG}</span>'
                f'<span class="ap-brand-name">{PRODUCT_NAME}</span></a>',
                unsafe_allow_html=True,
            )
        with mid:
            with st.container(key="ap_tabs"):
                for key, label, path in NAV:
                    if key == active:
                        st.markdown(f'<div class="ap-tab-active">{label}</div>',
                                    unsafe_allow_html=True)
                    else:
                        st.page_link(path, label=label)
        with right:
            st.markdown(
                f'<div class="ap-status">'
                f'<span class="ap-pill"><span class="ap-dot {eng["dot"]}"></span>'
                f'{eng["label"]}</span>'
                f'<span class="ap-user"><span class="ap-avatar">OP</span>'
                f'<span class="nm">운영자</span></span></div>',
                unsafe_allow_html=True,
            )


def boot(active: str, page_title: str) -> None:
    """모든 페이지의 첫 호출 - 페이지 설정 · 디자인 시스템 · 상단 헤더."""
    st.set_page_config(
        page_title=f"{page_title} · {PRODUCT_SUB}",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_css()

    stale = stale_config_reason()
    if stale:
        st.error(
            "**실행 중인 설정 모듈이 배포된 코드보다 오래되었습니다.** "
            f"(누락: `{stale}`)\n\n"
            "Streamlit Cloud가 새 코드를 받았지만 프로세스를 재시작하지 않아 "
            "`app/` 패키지가 예전 상태로 남아 있습니다. "
            "**[Manage app] → [⋮] → [Reboot app]** 으로 완전히 재시작하여 주십시오. "
            "재시작 전까지는 접근 비밀번호를 포함한 일부 기능이 동작하지 않습니다."
        )

    require_auth()  # 비밀번호가 설정된 경우 로그인 전에는 여기서 렌더가 중단된다
    render_header(active)


def page_header(
    eyebrow: str,
    title: str,
    desc: str,
    meta_label: str | None = None,
    meta_value: str | None = None,
    cta_label: str | None = None,
    cta_href: str | None = None,
    attached: bool = True,
) -> None:
    """페이지 타이틀 바 (초슬림 1줄 인라인)."""
    esc = html.escape
    side_parts = []
    if meta_label:
        side_parts.append(
            f'<div class="ap-metablock-inline"><span class="k">{esc(meta_label)}:</span> '
            f'<span class="v mono">{esc(meta_value or "—")}</span></div>'
        )
    if cta_label and cta_href:
        internal = cta_href.startswith("/")
        target = ' target="_self"' if internal else ' target="_blank" rel="noopener"'
        # 내부 링크는 전체 새로고침이므로 접속 토큰을 함께 실어 재로그인을 막는다
        href = cta_href + (auth_qs("&" if "?" in cta_href else "?") if internal else "")
        side_parts.append(f'<a class="ap-cta" href="{href}"{target}>{esc(cta_label)}</a>')
    side_html = f'<div class="ap-titlebar-side">{"".join(side_parts)}</div>' if side_parts else ""

    st.markdown(
        f'<div class="ap-titlebar{"" if attached else " solo"}">'
        f'<div class="ap-title-left">'
        f'<span class="ap-eyebrow-badge">{esc(eyebrow)}</span>'
        f'<span class="ap-title">{esc(title)}</span>'
        f'<span class="ap-desc-inline">· {esc(desc)}</span>'
        f'</div>{side_html}</div>',
        unsafe_allow_html=True,
    )


def util_bar():
    """타이틀 바에 이어지는 유틸리티 바 컨테이너."""
    return st.container(key="ap_util")


def active_filters(values: list[Any], neutral: tuple[str, ...] = ("전체",)) -> list[str]:
    """실제로 적용 중인 필터 값만 남긴다 (빈 값과 기본값 제외)."""
    picked: list[str] = []
    for v in values:
        text = str(v).strip() if v is not None else ""
        if text and text not in neutral:
            picked.append(text)
    return picked


def filter_title(label: str, picked: list[str]) -> str:
    """접힌 상태에서도 무엇이 걸려 있는지 보이도록 제목에 요약을 붙인다."""
    return f"🔎 {label}" + (f"  ·  {'  ·  '.join(picked)}" if picked else "")


@contextmanager
def filter_box(*state_keys: str, label: str = "검색 · 필터",
               neutral: tuple[str, ...] = ("전체",)):
    """검색·필터 입력을 접어 두는 컨테이너.

    모바일에서는 유틸리티 바의 컬럼이 세로로 쌓여 입력칸만으로 화면 한 장을
    차지했다. 기본은 접힌 상태로 두고, 적용 중인 필터가 있으면 제목에 요약을
    붙여 펼친 채로 보여 준다.

    Args:
        state_keys: 요약에 표시할 위젯 키들 (st.session_state에서 현재 값을 읽는다)
        neutral: '설정 안 함'으로 볼 값들 (요약에서 제외)
    """
    picked = active_filters([st.session_state.get(k) for k in state_keys], neutral)
    with st.container(key="ap_filterbox"):
        # 필터가 걸려 있으면 펼친 채로 보여 준다 (숨겨진 필터 때문에 결과를
        # 오해하는 일이 없도록)
        with st.expander(filter_title(label, picked), expanded=bool(picked)):
            yield


def section(label: str) -> None:
    st.markdown(f'<div class="ap-section" style="margin:14px 0 6px;">{html.escape(label)}</div>', unsafe_allow_html=True)


def tiles(items: list[dict[str, Any]]) -> None:
    """지표 타일 (초슬림 가로 분할 바)."""
    default_icons = ["🛫", "🎯", "🔔", "⏱️"]
    cells = []
    for idx, it in enumerate(items):
        icon = it.get("icon") or (default_icons[idx % len(default_icons)])
        unit = f'<span class="u">{html.escape(it["unit"])}</span>' if it.get("unit") else ""
        sub = f'<span class="s">({it["sub"]})</span>' if it.get("sub") else ""
        cells.append(
            f'<div class="ap-tile">'
            f'<div class="ap-tile-left">'
            f'<div class="k"><span style="margin-right:4px;">{icon}</span>{html.escape(it["label"])} {sub}</div>'
            f'</div>'
            f'<div class="v">{it["value"]}{unit}</div>'
            f'</div>'
        )
    st.markdown(f'<div class="ap-tiles">{"".join(cells)}</div>', unsafe_allow_html=True)




# ---------------------------------------------------------------------------
# 입력 변환 헬퍼 (로직 불변)
# ---------------------------------------------------------------------------
def prefill_form(d: dict) -> None:
    """Gemini 파싱 결과(초안 1개)를 등록 폼 위젯에 주입."""
    st.session_state["f_label"] = d.get("label") or ""
    origin = d.get("origin") or "ICN"
    dest = d.get("destination") or ""
    # 공항 selectbox의 위젯 키는 f_origin_sel / f_dest_sel 이다.
    # 예전에는 f_origin / f_dest 에만 넣어서, 이미 한 번 렌더된 selectbox가
    # 세션에 저장된 옛 값을 그대로 유지해 Gemini 분석 결과가 반영되지 않았다.
    st.session_state["f_origin"] = origin
    st.session_state["f_dest"] = dest
    st.session_state["f_origin_sel"] = choice_from_code(origin)
    st.session_state["f_dest_sel"] = choice_from_code(dest)
    st.session_state["f_trip"] = "왕복" if d.get("trip_type") == "round" else "편도"
    dep_d = safe_date(d.get("depart_date"))
    if dep_d:
        st.session_state["f_depart"] = dep_d
    ret_d = safe_date(d.get("return_date"))
    if ret_d:
        st.session_state["f_return"] = ret_d
    st.session_state["f_adults"] = d.get("adults") or 1
    st.session_state["f_currency"] = d.get("currency") or "KRW"
    st.session_state["f_target"] = float(d.get("target_price") or 0)
    hf, ht = d.get("dep_hour_from"), d.get("dep_hour_to")
    st.session_state["f_depfrom"] = "제한없음" if hf is None else f"{hf:02d}시"
    st.session_state["f_depto"] = "제한없음" if ht is None else f"{ht:02d}시"
    rf, rt = d.get("ret_hour_from"), d.get("ret_hour_to")
    st.session_state["f_retfrom"] = "제한없음" if rf is None else f"{rf:02d}시"
    st.session_state["f_retto"] = "제한없음" if rt is None else f"{rt:02d}시"
    ms = d.get("max_stops")
    st.session_state["f_stops"] = {None: "전체", 0: "직항만", 1: "직항+1회경유"}.get(ms, "전체")


def hour_value(sel: str) -> int | None:
    return None if sel == "제한없음" else int(sel.replace("시", ""))


def hour_index(hour: int | None) -> int:
    """저장된 시각 값 → HOUR_OPTIONS 인덱스 (수정 폼 기본값용)."""
    return 0 if hour is None else HOUR_OPTIONS.index(f"{hour:02d}시")


def stops_value(sel: str) -> int | None:
    return {"전체": None, "직항만": 0, "직항+1회경유": 1}.get(sel)


def stops_index(max_stops: int | None) -> int:
    return {None: 0, 0: 1, 1: 2}.get(max_stops, 0)


def currency_index(currency: str | None) -> int:
    return CURRENCIES.index(currency) if currency in CURRENCIES else 0


def validate_watch_input(
    origin: str, dest: str, trip: str,
    depart: date, ret: date | None,
    dep_from_v: int | None, dep_to_v: int | None,
    ret_from_v: int | None, ret_to_v: int | None,
) -> list[str]:
    """등록·수정 폼 공통 입력 검증. 오류 메시지 목록을 반환합니다."""
    errors: list[str] = []
    if not re.fullmatch(r"[A-Z]{3}", origin or ""):
        errors.append("출발 공항 코드는 IATA 3글자여야 합니다. (예: ICN)")
    if not re.fullmatch(r"[A-Z]{3}", dest or ""):
        errors.append("도착 공항 코드는 IATA 3글자여야 합니다. (예: NRT)")
    if origin and dest and origin == dest:
        errors.append("출발지와 도착지가 같습니다.")
    if trip == "왕복" and ret and ret <= depart:
        errors.append("오는 날은 가는 날 이후여야 합니다.")
    if dep_from_v is not None and dep_to_v is not None and dep_from_v > dep_to_v:
        errors.append("출발 시간대 범위가 올바르지 않습니다. (이후 ≤ 이전)")
    if (trip == "왕복" and ret_from_v is not None and ret_to_v is not None
            and ret_from_v > ret_to_v):
        errors.append("귀국 시간대 범위가 올바르지 않습니다. (이후 ≤ 이전)")
    return errors


def stops_text(w: WatchCondition) -> str:
    return {None: "경유 무관", 0: "직항만", 1: "직항+1회경유"}.get(w.max_stops, "경유 무관")


def time_window_parts(hf: int | None, ht: int | None) -> str:
    if hf is None and ht is None:
        return "시간대 무관"
    parts = []
    if hf is not None:
        parts.append(f"{hf:02d}시부터")
    if ht is not None:
        parts.append(f"{ht:02d}시까지")
    return " ~ ".join(parts)


def time_window_text_w(w: WatchCondition) -> str:
    return time_window_parts(w.dep_hour_from, w.dep_hour_to)


def ret_window_text_w(w: WatchCondition) -> str:
    return time_window_parts(w.ret_hour_from, w.ret_hour_to)


def draft_to_watch(d: dict) -> WatchCondition:
    """Gemini 초안 → 기본 규칙이 적용된 감시 조건."""
    return WatchCondition(
        label=d.get("label") or "",
        origin=d["origin"],
        destination=d["destination"],
        trip_type=d.get("trip_type") or "one-way",
        depart_date=d["depart_date"],
        return_date=d.get("return_date"),
        adults=int(d.get("adults") or 1),
        currency=d.get("currency") or "KRW",
        target_price=d.get("target_price"),
        dep_hour_from=d.get("dep_hour_from"),
        dep_hour_to=d.get("dep_hour_to"),
        ret_hour_from=d.get("ret_hour_from"),
        ret_hour_to=d.get("ret_hour_to"),
        max_stops=d.get("max_stops"),
        drop_percent=DEFAULT_DROP,
        percentile=DEFAULT_PCTILE,
        cooldown_hours=DEFAULT_COOLDOWN,
    )


# ---------------------------------------------------------------------------
# 표현 컴포넌트
# ---------------------------------------------------------------------------
def logo_urls(codes: list[str]) -> list[str]:
    return [LOGO_URL.format(code=c.upper()) for c in (codes or []) if c]


def logos_html(codes: list[str], size: int = 22) -> str:
    imgs = [
        f'<img src="{url}" width="{size}" height="{size}" '
        f'onerror="this.style.display=\'none\'" alt="">'
        for url in logo_urls(codes)[:3]
    ]
    return f'<span class="ap-logos">{"".join(imgs)}</span>' if imgs else ""


def deal_text(deal: dict[str, Any]) -> str:
    return str(deal.get("label") or "").rstrip("!")


def deal_badge_html(deal: dict[str, Any]) -> str:
    """판정 배지 - 색 점 + 라벨."""
    cls, dot = LEVEL_STYLE.get(deal.get("level", "unknown"), LEVEL_STYLE["unknown"])
    return (f'<span class="ap-badge {cls}"><span class="ap-dot {dot}"></span>'
            f'{html.escape(deal_text(deal))}</span>')


def trend_html(trend_pct: float | None) -> str:
    """직전 확인 대비 증감."""
    if trend_pct is None:
        return '<span class="ap-trend flat">비교 기준 없음</span>'
    if trend_pct < -0.05:
        return f'<span class="ap-trend down mono">▼ {abs(trend_pct):.1f}%</span>'
    if trend_pct > 0.05:
        return f'<span class="ap-trend up mono">▲ {trend_pct:.1f}%</span>'
    return '<span class="ap-trend flat">변동 없음</span>'


def sparkline_svg(history: list[dict[str, Any]], width: int = 124, height: int = 34) -> str:
    """최근 30일 최저가 추이 스파크라인."""
    vals = [float(h["price"]) for h in (history or []) if h.get("price") is not None]
    if len(vals) < 2:
        return '<span class="ap-nodata">데이터 부족</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n, pad = len(vals), 4.0
    pts = [
        (pad + i / (n - 1) * (width - pad * 2),
         height - pad - (v - lo) / rng * (height - pad * 2))
        for i, v in enumerate(vals)
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{height} {line} {pts[-1][0]:.1f},{height}"
    lx, ly = pts[-1]
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="최근 {n}회 가격 추이">'
        f'<polygon points="{area}" fill="rgba(68,190,175,.14)"/>'
        f'<polyline points="{line}" fill="none" stroke="#44beaf" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="#243050"/></svg>'
    )


def flights_search_url(w: WatchCondition) -> str:
    """해당 조건의 Google Flights 검색 링크."""
    from urllib.parse import quote

    q = f"Flights from {w.origin} to {w.destination} on {w.depart_date}"
    if w.trip_type == "round" and w.return_date:
        q += f" return {w.return_date}"
    return f"https://www.google.com/travel/flights?q={quote(q)}"


def skyscanner_search_url(w: WatchCondition) -> str:
    """해당 조건의 Skyscanner 검색 링크."""
    orig = (w.origin or "").lower().strip()
    dest = (w.destination or "").lower().strip()
    dep_yy = (w.depart_date or "").replace("-", "")[2:8]
    adults = max(1, int(w.adults or 1))
    direct_param = "&preferdirects=true" if w.max_stops == 0 else ""

    if w.trip_type == "round" and w.return_date:
        ret_yy = w.return_date.replace("-", "")[2:8]
        return (
            f"https://www.skyscanner.co.kr/transport/flights/{orig}/{dest}/{dep_yy}/{ret_yy}/"
            f"?adultsv2={adults}&cabinclass=economy{direct_param}&rtn=1"
        )
    return (
        f"https://www.skyscanner.co.kr/transport/flights/{orig}/{dest}/{dep_yy}/"
        f"?adultsv2={adults}&cabinclass=economy{direct_param}&rtn=0"
    )



def watch_code(w: WatchCondition) -> str:
    """감시 조건 식별 코드 (예: WT-019)."""
    return f"WT-{(w.id or 0):03d}"


def route_title(w: WatchCondition) -> str:
    return w.label or destination_label(w.destination)


def schedule_text(w: WatchCondition) -> str:
    return w.depart_date + (f" ~ {w.return_date}" if w.return_date else "")


def schedule_compact(w: WatchCondition) -> str:
    """표 행용 축약 일정 (같은 해면 오는 날의 연도를 생략)."""
    if not w.return_date:
        return w.depart_date
    ret = w.return_date
    if ret[:4] == w.depart_date[:4]:
        ret = ret[5:]
    return f"{w.depart_date} ~ {ret}"


def _window_short(hf: int | None, ht: int | None) -> str:
    if hf is None and ht is None:
        return "전체 시간"
    if hf is not None and ht is not None:
        return f"{hf:02d}~{ht:02d}시"
    if hf is not None:
        return f"{hf:02d}시 이후"
    return f"{ht:02d}시 이전"


def _time_window_short(w: WatchCondition) -> str:
    return _window_short(w.dep_hour_from, w.dep_hour_to)


def watch_table_header() -> str:
    return ('<div class="ap-thead">'
            '<div class="ap-c-route">노선</div>'
            '<div class="ap-c-cond">조건 · 일정</div>'
            '<div class="ap-c-spark">30일 추이</div>'
            '<div class="ap-c-price ap-cell-price">현재가</div>'
            '<div class="ap-c-verdict ap-cell-verdict">판정</div>'
            '<div class="ap-c-link" style="text-align:right;">링크</div></div>')


def flight_time_html(offers: list[dict[str, Any]], w: WatchCondition) -> str:
    """최근 조회에서 최저가였던 항공편의 출·도착 시각."""
    esc = html.escape
    o = offers[0] if offers else None
    dep = str((o or {}).get("departure") or "")
    if not o or len(dep) < 5:
        return '<div class="ap-flight"><span class="ap-nodata">운항 시각 정보 없음</span></div>'
    arr = str(o.get("arrival") or "")
    dep_t = dep[-5:]
    arr_t = arr[-5:] if len(arr) >= 5 else "--:--"
    plus = ""
    if len(dep) >= 10 and len(arr) >= 10 and dep[:10] != arr[:10]:
        try:
            days = (date.fromisoformat(arr[:10]) - date.fromisoformat(dep[:10])).days
            if days > 0:
                plus = f'<span class="pd">+{days}</span>'
        except ValueError:
            pass
    lead = "최저가편"
    airline = esc(str(o.get("airline") or "").strip())
    air = f'<span class="air">{airline}</span>' if airline else ""
    return (f'<div class="ap-flight"><span class="lb">{lead}</span>'
            f'<span class="tm mono">{esc(dep_t)}<span class="arw">→</span>'
            f'{esc(arr_t)}{plus}</span>{air}</div>')


def watch_expandable_row_html(w: WatchCondition, d: dict[str, Any]) -> str:
    """감시 조건 1건을 클릭 시 바로 아래로 상세 내용이 펼쳐지는 아코디언 행으로 렌더링."""
    esc = html.escape
    stats, deal, offers = d["stats"], d["deal"], d.get("offers") or []
    search_url = flights_search_url(w)
    sky_url = skyscanner_search_url(w)

    badges = ['<span class="ap-badge line">왕복</span>' if w.trip_type == "round"
              else '<span class="ap-badge line">편도</span>',
              f'<span class="ap-badge line">{esc(stops_text(w))}</span>']
    if not w.active:
        badges.append('<span class="ap-badge mute">'
                      '<span class="ap-dot dot-idle"></span>감시 중지</span>')

    detail = [f'<span class="mono">{esc(schedule_compact(w))}</span>',
              f'출발 {esc(_time_window_short(w))}']
    if w.trip_type == "round" and (w.ret_hour_from is not None or w.ret_hour_to is not None):
        detail.append(f'귀국 {esc(_window_short(w.ret_hour_from, w.ret_hour_to))}')
    if w.adults > 1:
        detail.append(f'성인 {w.adults}명')
    detail.append(f'목표 <span class="mono">{num(w.target_price)}</span>'
                  if w.target_price else "목표 미설정")

    # 1. 펼쳐졌을 때의 4단 가격 지표
    figures = [
        ("현재 최저가", num(stats.get("last")), w.currency),
        ("30일 최저", num(stats.get("min")), w.currency),
        ("30일 평균", num(stats.get("avg")), w.currency),
        ("첫 관측가", num(w.first_seen_price or stats.get("first")), w.currency),
    ]
    fig_cells = "".join(
        f'<div class="ap-figure"><div class="k">{k}</div>'
        f'<div class="v">{v}<span class="cur">{cur}</span></div></div>'
        for k, v, cur in figures
    )
    figures_html = f'<div class="ap-panel" style="margin-bottom:12px;"><div class="ap-figures">{fig_cells}</div></div>'

    # 2. 적용 필터 태그 요약
    filter_tags = [
        f"<b>노선:</b> {w.origin} → {w.destination}",
        f"<b>일정:</b> {schedule_text(w)}",
        f"<b>유형:</b> {'왕복' if w.trip_type == 'round' else '편도'}",
        f"<b>출발 시간대:</b> {time_window_text_w(w)}",
    ]
    if w.trip_type == "round":
        filter_tags.append(f"<b>귀국 시간대:</b> {ret_window_text_w(w)}")
    filter_tags += [
        f"<b>경유:</b> {stops_text(w)}",
        f"<b>인원:</b> 성인 {w.adults}명",
        f"<b>목표가:</b> {num(w.target_price)} {w.currency}" if w.target_price else "<b>목표가:</b> 미설정",
    ]
    filters_html = (
        f'<div style="display:flex;justify-content:space-between;align-items:center;background:#eceff3;padding:8px 14px;border-radius:6px;margin-bottom:12px;flex-wrap:wrap;gap:8px;">'
        f'<div style="font-size:12.5px;color:#363e4d;line-height:1.7;">{" · ".join(filter_tags)}</div>'
        # 수정 폼은 '조건 관리' 페이지 한 곳에만 둔다 (대시보드 사본은 제거)
        f'<a href="/watches?edit={w.id}{auth_qs("&")}" target="_self" style="display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;color:#fff;background:#243050;padding:5px 11px;border-radius:4px;text-decoration:none;white-space:nowrap;">✏️ 조건 수정</a>'
        f'</div>'
    )

    # 3. 항공편 조회 결과 목록
    if not offers:
        offers_html = (
            '<div class="ap-panel" style="margin-bottom:8px;">'
            '<div class="ap-panel-h">항공편 조회 결과</div>'
            '<div class="ap-empty">조회된 항공편 기록이 없습니다.</div></div>'
        )
    else:
        offers_rows = "".join(
            offer_row_html(o, w.currency, search_url, rank, sky_url=sky_url)
            for rank, o in enumerate(offers[:5])
        )
        offers_html = (
            f'<div class="ap-panel" style="margin-bottom:8px;">'
            f'<div class="ap-panel-h">최근 조회 항공편 목록'
            f'<span class="n">{len(offers):,}건 중 상위 5건 · {ts(offers[0]["checked_at"])} 기준</span></div>'
            f'{offers_rows}</div>'
        )

    dest_info = airport_info(w.destination)
    flag = dest_info.get("flag") or "✈️"

    return f"""
<details class="ap-details">
  <summary class="ap-row" title="클릭하여 상세 항공편 및 가격 요약 펼치기">
    <div class="ap-c-route">
      <div class="ap-route mono"><span style="font-size:15px;margin-right:3px;">{flag}</span>{esc(w.origin)}<span class="arw">→</span>{esc(w.destination)}</div>
      <div class="ap-id">{esc(watch_code(w))}</div>
    </div>
    <div class="ap-c-cond">
      <div class="ap-planline">
        <span class="ap-plan">{esc(route_title(w))}</span>{"".join(badges)}
      </div>
      <div class="ap-sub">{" · ".join(detail)}</div>
      {flight_time_html(offers, w)}
    </div>
    <div class="ap-c-spark">{sparkline_svg(d['history'])}
      <div class="ap-sub" style="margin-top:2px;">관측 {stats.get('count', 0)}회</div>
    </div>
    <div class="ap-c-price ap-cell-price">
      <div class="ap-price">{num(stats.get('last'))}<span class="cur">{esc(w.currency)}</span></div>
      {trend_html(deal.get('trend_pct'))}
    </div>
    <div class="ap-c-verdict ap-cell-verdict">{deal_badge_html(deal)}</div>
    <div class="ap-c-link" style="text-align:right;white-space:nowrap;">
      <a class="ap-link" href="{esc(search_url)}" target="_blank" rel="noopener">구글 ↗</a>
      <span style="color:#dde2e9;margin:0 3px;">|</span>
      <a class="ap-link" href="{esc(sky_url)}" target="_blank" rel="noopener">스카이 ↗</a>
    </div>
  </summary>
  <div class="ap-detail-body">
    {figures_html}
    {filters_html}
    {offers_html}
  </div>
</details>"""




def offer_row_html(o: dict[str, Any], currency: str, search_url: str, rank: int, sky_url: str = "") -> str:
    """항공편 1건을 결과 행으로 렌더링."""
    esc = html.escape
    dep = str(o.get("departure") or "-")
    arr = str(o.get("arrival") or "-")
    dep_time = dep[-5:] if len(dep) >= 5 else dep
    arr_time = arr[-5:] if len(arr) >= 5 else arr
    dep_date = dep[:10] if len(dep) >= 10 else ""
    stops = int(o.get("stops") or 0)
    stops_badge = ('<span class="ap-badge ok"><span class="ap-dot dot-ok"></span>직항</span>'
                   if stops == 0 else
                   f'<span class="ap-badge warn"><span class="ap-dot dot-warn"></span>'
                   f'경유 {stops}회</span>')
    rank_badge = ('<div class="ap-rank is-best">최저</div>' if rank == 0
                  else f'<div class="ap-rank">{rank + 1:02d}</div>')

    links = [f'<a class="ap-link" href="{esc(search_url)}" target="_blank" rel="noopener">구글 항공권 ↗</a>']
    if sky_url:
        links.append(f'<a class="ap-link" href="{esc(sky_url)}" target="_blank" rel="noopener">스카이스캐너 ↗</a>')
    links_html = " · ".join(links)

    return f"""
<div class="ap-offer">
  {rank_badge}
  <div>
    <div class="ap-times">{esc(dep_time)}<span class="arw">→</span>{esc(arr_time)}</div>
    <div class="d">{esc(dep_date)}</div>
  </div>
  <div class="ap-air">{logos_html(o.get('airline_codes') or [], size=24)}
    <span class="nm">{esc(o.get('airline') or '항공사 미상')}</span></div>
  <div class="ap-c-stops">{stops_badge}</div>
  <div class="ap-cell-price">
    <div class="ap-price">{num(o.get('price'))}<span class="cur">{esc(currency)}</span></div>
    <div style="margin-top:5px;font-size:12px;">{links_html}</div>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# 데이터 조회 (표현용 묶음)
# ---------------------------------------------------------------------------
def load_watch_data(db: Database, w: WatchCondition) -> dict[str, Any]:
    """감시 조건 1건의 통계·이력·딜 상태·최근 오퍼를 묶어 반환."""
    hist = db.get_history(w.id, days=30)
    # 이미 읽은 이력을 넘겨 동일 쿼리 재실행을 막는다 (조건 수만큼 절약)
    stats = db.price_stats(w.id, days=30, percentile=w.percentile, history=hist)
    return {
        "stats": stats,
        "history": hist,
        "deal": deal_status(stats, hist),
        "offers": db.get_latest_offers(w.id),
    }


def watch_options(watches: list[WatchCondition]) -> dict[str, int]:
    """국가·도시 순으로 정렬된 감시 조건 선택 옵션."""
    def sort_key(w: WatchCondition) -> tuple[str, str, int]:
        info = airport_info(w.destination)
        return (info["country"], info["city"] or w.destination, w.id or 0)

    return {
        f"{watch_code(w)} · {w.origin}-{w.destination} · "
        f"{route_title(w)} · {w.depart_date}": w.id
        for w in sorted(watches, key=sort_key)
    }


def last_check_text(watches: list[WatchCondition]) -> str:
    stamps = [w.last_checked_at for w in watches if w.last_checked_at]
    return ts(max(stamps)) if stamps else "기록 없음"


def today_checked(watches: list[WatchCondition]) -> int:
    today = date.today().isoformat()
    return sum(1 for w in watches if w.last_checked_at and w.last_checked_at[:10] == today)
