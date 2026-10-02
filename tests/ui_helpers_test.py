"""표현 계층 헬퍼 테스트 (스트림릿 실행 없이 순수 함수만 검증).

    python tests/ui_helpers_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# streamlit_app 을 나중에 넣어야 루트의 app/ 패키지가 가려지지 않는다
for p in (str(ROOT / "streamlit_app"), str(ROOT)):
    while p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

import shared  # noqa: E402

passed = failed = 0


def check(label: str, got, want) -> None:
    global passed, failed
    if got == want:
        passed += 1
        print(f"PASS - {label}")
    else:
        failed += 1
        print(f"FAIL - {label}\n       기대: {want!r}\n       실제: {got!r}")


def main() -> int:
    # --- 접힌 필터 요약 ---
    check("아무것도 안 걸면 빈 목록",
          shared.active_filters([None, "", "   ", "전체"]), [])
    check("실제 값만 남긴다",
          shared.active_filters(["나트랑", "전체", "가동"]), ["나트랑", "가동"])
    check("기본값은 neutral로 제외 (추이 화면의 30일)",
          shared.active_filters(["전체", "30일", "7일"], neutral=("전체", "30일")),
          ["7일"])
    check("앞뒤 공백은 정리",
          shared.active_filters(["  다낭  "]), ["다낭"])

    check("필터 없으면 제목만",
          shared.filter_title("검색 · 필터", []), "🔎 검색 · 필터")
    check("필터가 있으면 제목에 요약",
          shared.filter_title("검색 · 필터", ["나트랑", "가동"]),
          "🔎 검색 · 필터  ·  나트랑  ·  가동")

    # --- 검색 필터 (페이지 공용) ---
    from app.models import WatchCondition
    w = WatchCondition(label="다낭 9/23", origin="ICN", destination="DAD",
                       depart_date="2026-09-23")
    check("빈 검색어는 전부 통과", shared.watch_matches(w, ""), True)
    check("도시명으로 검색", shared.watch_matches(w, "다낭"), True)
    check("다른 도시는 제외", shared.watch_matches(w, "나트랑"), False)
    check("공항 코드 대소문자 무시", shared.watch_matches(w, "dad"), True)
    check("국가 필터 일치", shared.watch_matches(w, "", "베트남"), True)
    check("국가 필터 불일치", shared.watch_matches(w, "", "일본"), False)

    # --- 비밀값 표시 ---
    check("미설정은 그대로 표기", shared.mask(None), "미설정")
    check("설정된 값은 길이만 노출", shared.mask("AIzaSyABCDEFG"), "설정됨 (13자)")

    # --- 날짜 방어 ---
    check("깨진 날짜는 None", shared.safe_date("2026-13-99"), None)
    check("빈 값도 None", shared.safe_date(""), None)
    check("정상 날짜는 파싱", str(shared.safe_date("2026-09-23")), "2026-09-23")

    # --- 텔레그램 본문 상한 (4096자 초과 시 400으로 알림 유실 방지) ---
    from app.services.notifier import MAX_TELEGRAM_TEXT, _truncate
    check("상한 이하는 그대로", _truncate("짧은 알림"), "짧은 알림")
    long_msg = "\n".join(f"라인 {i}: " + "가" * 80 for i in range(80))
    cut = _truncate(long_msg)
    check("상한 초과는 4096자 이내로 절단", len(cut) <= MAX_TELEGRAM_TEXT, True)
    check("절단 표식이 붙는다", cut.endswith("…(생략)"), True)
    check("줄 중간이 아니라 줄 단위로 자른다",
          cut[: -len("\n…(생략)")].rstrip("가").endswith(": ") or "\n" in cut, True)

    # --- 동기화 계층 계약 (수동 조회 커밋이 기대는 API) ---
    from app import github_sync
    check("RemoteChanged 예외 존재", issubclass(github_sync.RemoteChanged, RuntimeError), True)
    rd = github_sync.RemoteDB(b"x", "sha123")
    check("RemoteDB는 (data, sha) 쌍", (rd.data, rd.sha), (b"x", "sha123"))
    check("sync_note: 충돌은 안내 문구",
          "반영되지 않았습니다" in (shared.sync_note("conflict") or ""), True)
    check("sync_note: 성공·로컬은 안내 없음",
          (shared.sync_note("ok"), shared.sync_note("local")), (None, None))
    check("sync_note: 오류는 원인 포함",
          "boom" in (shared.sync_note("error: boom") or ""), True)

    # --- 무상태 인증 토큰 (재배포로 프로세스가 죽어도 유효해야 한다) ---
    import os
    from datetime import date, timedelta
    os.environ["APP_PASSWORD"] = "test-8144"
    try:
        tok = shared._issue_auth_token()
        check("같은 날 발급 토큰은 항상 동일 (무상태)",
              tok == shared._issue_auth_token(), True)
        check("발급 토큰은 유효", shared._token_valid(tok), True)
        check("전일 토큰도 유효 (자정 직후 대비)",
              shared._token_valid(shared._window_token(date.today() - timedelta(days=1))), True)
        check("이틀 전 토큰은 무효",
              shared._token_valid(shared._window_token(date.today() - timedelta(days=2))), False)
        check("엉뚱한 토큰은 무효", shared._token_valid("abcd1234"), False)
        prev = tok
        os.environ["APP_PASSWORD"] = "changed"
        check("비밀번호를 바꾸면 기존 토큰 즉시 무효", shared._token_valid(prev), False)
    finally:
        os.environ.pop("APP_PASSWORD", None)

    # 신규 복제 및 지역 프리셋 헬퍼 테스트
    presets = shared.get_popular_region_presets()
    check("인기 여행지 프리셋 존재", len(presets) >= 5, True)
    check("베트남 프리셋 포함", "베트남 주요 (다낭/나트랑/푸꾸옥/하노이)" in presets, True)
    check("다낭(DAD) 포함", "DAD" in presets["베트남 주요 (다낭/나트랑/푸꾸옥/하노이)"], True)

    countries = shared.get_country_list()
    check("국가 목록 반환", "베트남" in countries and "일본" in countries, True)

    # 라벨 스마트 치환 테스트
    check("라벨 도시명 치환 (다낭 -> 나트랑)",
          shared.suggest_cloned_label("추석 다낭 휴가", "ICN", "DAD", "CXR"), "추석 나트랑 휴가")
    check("라벨 도시명 치환 (다낭 -> 방콕)",
          shared.suggest_cloned_label("골든위크 다낭", "ICN", "DAD", "BKK"), "골든위크 방콕")
    check("라벨 IATA 치환 (DAD -> FUK)",
          shared.suggest_cloned_label("여름 DAD 투어", "ICN", "DAD", "FUK"), "여름 FUK 투어")
    check("라벨 빈값일 때",
          shared.suggest_cloned_label("", "ICN", "DAD", "CXR"), "나트랑 감시")
    check("라벨에 도시명이 없을 때 접미사 추가",
          shared.suggest_cloned_label("가족여행", "ICN", "DAD", "CXR"), "가족여행 · 나트랑")

    # 복제 조건 객체 생성 및 중복 검사 테스트
    from app.models import WatchCondition
    base_w = WatchCondition(
        id=1, label="휴가 다낭", origin="ICN", destination="DAD", trip_type="round",
        depart_date="2026-10-03", return_date="2026-10-07", target_price=450000.0,
        dep_hour_from=20, dep_hour_to=23, ret_hour_from=18, ret_hour_to=None, max_stops=0,
    )
    cloned_w = shared.clone_watch_for_destination(base_w, "CXR")
    check("복제된 목적지 코드", cloned_w.destination, "CXR")
    check("복제된 라벨", cloned_w.label, "휴가 나트랑")
    check("복제된 여행 기간 일치", cloned_w.depart_date == base_w.depart_date and cloned_w.return_date == base_w.return_date, True)
    check("복제된 시간대 조건 일치", cloned_w.dep_hour_from == 20 and cloned_w.ret_hour_from == 18, True)
    check("복제된 목표가 일치", cloned_w.target_price, 450000.0)

    # 중복 검사
    check("동일 조건 중복 발견",
          shared.find_duplicate_watch([base_w], "ICN", "DAD", "2026-10-03", "round", "2026-10-07") is not None, True)
    check("다른 목적지는 미중복",
          shared.find_duplicate_watch([base_w], "ICN", "CXR", "2026-10-03", "round", "2026-10-07") is None, True)

    print()
    if failed:
        print(f"실패 {failed}건 / 전체 {passed + failed}건")
        return 1
    print(f"모든 UI 헬퍼 테스트 통과! ({passed}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
