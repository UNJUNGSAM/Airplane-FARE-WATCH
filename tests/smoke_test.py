"""오프라인 스모크 테스트 - DB / 규칙 엔진 / 가격 파서 / 알림 포맷 검증.

실행: python tests/smoke_test.py  (네트워크 호출 없음)
"""
from __future__ import annotations

import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Database, now_str, parse_dt  # noqa: E402
from app.models import DealDecision, FlightOffer, WatchCondition  # noqa: E402
from app.providers.google_flights import parse_price  # noqa: E402
from app.services import notifier  # noqa: E402
from app.services.gemini_service import GeminiService  # noqa: E402
from app.services.rule_engine import evaluate_deal  # noqa: E402


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"{'PASS' if cond else 'FAIL'} - {name}")
        if not cond:
            failures.append(name)

    # ---------- 가격 파서 ----------
    check("parse_price 숫자", parse_price(123400) == 123400.0)
    check("parse_price 원화 문자열", parse_price("₩123,400") == 123400.0)
    check("parse_price 달러 문자열", parse_price("$1,234.56") == 1234.56)
    check("parse_price None", parse_price(None) is None)
    check("parse_price 빈 문자열", parse_price("") is None)

    # ---------- DB ----------
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    db = Database(str(tmp))
    db.init_schema()

    w = WatchCondition(
        label="도쿄 테스트", origin="ICN", destination="NRT",
        trip_type="round", depart_date="2026-09-30", return_date="2026-10-03",
        adults=1, currency="KRW", target_price=450000,
        drop_percent=15, percentile=10, cooldown_hours=6,
    )
    wid = db.add_watch(w)
    got = db.get_watch(wid)
    check("감시 조건 저장/조회", got is not None and got.origin == "ICN" and got.active)

    # 이력 12건 기록 (첫 관측가 600000, 점점 하락)
    prices = [600000, 590000, 585000, 580000, 575000, 570000,
              565000, 560000, 555000, 550000, 545000, 480000]
    for p in prices:
        db.add_price_record(
            wid,
            FlightOffer(airline="Test Air", price=p, currency="KRW",
                        departure="08:00", arrival="17:00", stops=0),
            checked_at=now_str(),
        )
    db.update_watch_fields(wid, first_seen_price=prices[0])

    stats = db.price_stats(wid, days=30, percentile=10)
    check("통계 count=12", stats["count"] == 12)
    check("통계 min=480000", stats["min"] == 480000.0)
    check("통계 first=600000", stats["first"] == 600000.0)
    # 선형 보간 p10: 정렬 시 [480000, 545000, ...] → idx 1.1 지점 = 545500
    check("백분위 산출", stats["pct_value"] is not None and abs(stats["pct_value"] - 545500) < 1)

    hist = db.get_history(wid, days=30)
    check("이력 조회 12건", len(hist) == 12)

    # ---------- 출발/귀국 시간대·경유 필터 컬럼 ----------
    wid2 = db.add_watch(WatchCondition(
        origin="ICN", destination="DAD", depart_date="2026-09-23",
        return_date="2026-09-27", trip_type="round",
        dep_hour_from=0, dep_hour_to=12,
        ret_hour_from=0, ret_hour_to=2, max_stops=0))
    w2 = db.get_watch(wid2)
    check("시간대 저장/조회", w2.dep_hour_from == 0 and w2.dep_hour_to == 12)
    check("귀국 시간대 저장/조회", w2.ret_hour_from == 0 and w2.ret_hour_to == 2)
    check("경유 필터 저장/조회", w2.max_stops == 0)
    db.update_watch_fields(wid2, dep_hour_from=20, max_stops=1, ret_hour_from=12)
    w2b = db.get_watch(wid2)
    check("시간대 부분 업데이트", w2b.dep_hour_from == 20 and w2b.dep_hour_to == 12)
    check("귀국 시간대 업데이트", w2b.ret_hour_from == 12 and w2b.ret_hour_to == 2)
    check("경유 필터 업데이트", w2b.max_stops == 1)

    # ---------- Gemini 파싱 정규화 ----------
    from app.services.gemini_service import normalize_draft

    nd = normalize_draft({
        "origin": "icn", "destination": "DAD", "depart_date": "2026-09-23",
        "trip_type": "round", "return_date": "2026-09-27", "adults": "2",
        "target_price": "400000", "currency": "krw",
        "dep_hour_from": 20, "dep_hour_to": 23, "label": "테스트",
    })
    check("normalize 형변환",
          nd["origin"] == "ICN" and nd["adults"] == 2
          and nd["target_price"] == 400000.0 and nd["dep_hour_from"] == 20
          and nd["currency"] == "KRW")
    try:
        normalize_draft({"origin": "ICN"})
        norm_ok = False
    except ValueError:
        norm_ok = True
    check("normalize 필수 누락 예외", norm_ok)
    nd2 = normalize_draft({"origin": "ICN", "destination": "PQC",
                           "depart_date": "2026-09-24"})
    check("normalize 시간대 기본 None", nd2["dep_hour_from"] is None
          and nd2["dep_hour_to"] is None)
    nd3 = normalize_draft({"origin": "ICN", "destination": "PQC",
                           "depart_date": "2026-09-24", "max_stops": 0,
                           "label": "푸꾸옥 9/24"})
    check("normalize 경유 필터", nd3["max_stops"] == 0
          and "직항" not in nd3["label"])
    db.delete_watch(wid2)  # 뒤의 활성 조회 검증을 위해 정리

    # ---------- 공항 메타데이터 ----------
    from app.airports import airport_info, destination_label

    info = airport_info("DAD")
    check("공항 정보 다낭", info["city"] == "다낭" and info["country"] == "베트남"
          and info["flag"] == "🇻🇳")
    check("미등록 공항 폴백", airport_info("XXX")["country"] == "기타")
    check("목적지 라벨", destination_label("NRT") == "도쿄(나리타) (NRT)")

    # ---------- 딜 상태 판정 ----------
    from app.services.deal import deal_status

    st_best = {"count": 5, "min": 100.0, "max": 200.0, "avg": 150.0,
               "first": 200.0, "last": 100.0, "pct_value": 110.0}
    d_best = deal_status(st_best)
    check("딜 판정 역대 최저", d_best["level"] == "best"
          and d_best["discount_first"] == 50.0)
    st_good = {"count": 5, "min": 100.0, "max": 200.0, "avg": 150.0,
               "first": 200.0, "last": 140.0, "pct_value": 110.0}
    check("딜 판정 평균 이하", deal_status(st_good)["level"] == "good")
    st_high = {"count": 5, "min": 100.0, "max": 200.0, "avg": 150.0,
               "first": 200.0, "last": 190.0, "pct_value": 110.0}
    check("딜 판정 비쌈", deal_status(st_high)["level"] == "high")
    check("딜 판정 데이터 없음", deal_status({"count": 0})["level"] == "unknown")
    d_trend = deal_status(st_good, [{"price": 200.0}, {"price": 140.0}])
    check("딜 판정 추세", d_trend["trend_pct"] == -30.0)

    # ---------- 항공편 스냅샷 ----------
    wid3 = db.add_watch(WatchCondition(origin="ICN", destination="DAD",
                                       depart_date="2026-09-23"))
    from app.models import FlightOffer as FO

    db.add_offer_snapshot(wid3, [
        FO(airline="A", airline_codes=["TW"], price=100, departure="08:00"),
        FO(airline="B", airline_codes=["7C"], price=120, departure="09:00"),
        FO(airline="C", airline_codes=["LJ"], price=130, departure="10:00"),
    ], checked_at="2026-01-01T10:00:00", top_n=2)
    snaps = db.get_latest_offers(wid3)
    check("스냅샷 top_n 저장", len(snaps) == 2 and snaps[0]["price"] == 100.0)
    check("스냅샷 항공사 코드", snaps[0]["airline_codes"] == ["TW"])
    db.prune_snapshots(max_per_watch=1)
    check("스냅샷 프루닝", len(db.get_latest_offers(wid3)) == 1)  # 행 수 기준 1행만 유지
    db.delete_watch(wid3)

    # ---------- 규칙 엔진 ----------
    watch = db.get_watch(wid)

    d = evaluate_deal(watch, 480000, stats)
    check("목표가+하락률+백분위 동시 발동", d.should_notify and len(d.reasons) >= 2)

    d2 = evaluate_deal(watch, 599000, {"count": 12, "pct_value": 500000})
    check("고가에서는 미발동", not d2.should_notify and not d2.reasons)

    # 쿨다운: 방금 알렸다고 가정
    db.update_watch_fields(wid, last_notified_at=now_str())
    watch_cool = db.get_watch(wid)
    d3 = evaluate_deal(watch_cool, 400000, stats)
    check("쿨다운 중 억제", not d3.should_notify and "쿨다운" in d3.detail)

    # 쿨다운 경과 후 재발동
    old = (parse_dt(now_str()) - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S")
    db.update_watch_fields(wid, last_notified_at=old)
    watch_old = db.get_watch(wid)
    d4 = evaluate_deal(watch_old, 400000, stats)
    check("쿨다운 경과 후 재발동", d4.should_notify)

    # 백분위 규칙: 관측 부족 시 비활성
    d5 = evaluate_deal(watch_old, 480000, {"count": 3, "pct_value": 500000})
    check("관측 3회면 백분위 규칙 미적용", all("백분위" not in r for r in d5.reasons))

    # ---------- 알림 포맷 ----------
    offer = FlightOffer(airline="Korean Air <테스트>", price=480000, currency="KRW",
                        departure="08:25", arrival="10:45", stops=0, is_best=True)
    msg = notifier.format_hot_deal(
        watch_old, offer,
        DealDecision(should_notify=True, reasons=["목표가 도달"], detail=""),
        "평균보다 15% 낮습니다.",
    )
    check("알림 메시지에 가격 포함", "480,000 KRW" in msg)
    check("HTML 이스케이프 적용", "<" in msg and "<테스트>" not in msg)
    check("Gemini 분석 문구 포함", "Gemini 분석" in msg)

    # ---------- 편집/삭제/프루닝 ----------
    db.set_active(wid, False)
    check("비활성 전환", db.get_watch(wid).active is False)
    check("활성만 조회 0건", db.list_watches(active_only=True) == [])
    db.prune_history(keep_days=90, max_rows_per_watch=5)
    check("프루닝 후 최대 5행", len(db.get_history(wid, days=36500)) <= 5)
    db.delete_watch(wid)
    check("삭제", db.get_watch(wid) is None)

    # ---------- 전체 초기화 ----------
    db.add_watch(WatchCondition(origin="ICN", destination="CXR",
                                depart_date="2026-09-24"))
    db.add_watch(WatchCondition(origin="ICN", destination="PQC",
                                depart_date="2026-09-24"))
    n = db.delete_all_watches()
    check("전체 초기화", n >= 2 and db.list_watches() == [])

    # ---------- 출발일 경과 조건 자동 종료 ----------
    from app.services.checker import retire_expired_watches
    past_id = db.add_watch(WatchCondition(origin="ICN", destination="NRT",
                                          depart_date="2020-01-01"))
    future_id = db.add_watch(WatchCondition(origin="ICN", destination="NRT",
                                            depart_date="2099-01-01"))
    retired = retire_expired_watches(db)  # 텔레그램 미설정 환경이라 발송은 건너뜀
    check("과거 출발일만 종료", [w.id for w in retired] == [past_id])
    check("종료된 조건은 비활성", db.get_watch(past_id).active is False)
    check("미래 조건은 그대로 가동", db.get_watch(future_id).active is True)
    check("두 번째 호출은 종료 대상 없음", retire_expired_watches(db) == [])

    # ---------- 알림 로그 상한 ----------
    for i in range(30):
        db.log_notification(future_id, 1000.0 + i, "테스트", "m")
    db.prune_notifications(max_rows=10)
    kept = db.list_notifications(limit=100)
    check("알림 로그 10건만 유지", len(kept) == 10)
    check("최신 알림이 남는다", kept[0]["price"] == 1029.0)

    # ---------- Gemini 미설정 동작 ----------
    g = GeminiService()
    if not g.available:
        check("키 없으면 analyze_deal 빈 문자열", g.analyze_deal(watch_old, 1, {}) == "")

    print()
    if failures:
        print(f"총 {len(failures)}개 실패: {failures}")
        return 1
    print("모든 스모크 테스트 통과!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
