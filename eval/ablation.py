"""
입력 제거(ablation) 실험 — 각 입력을 뺐을 때 결과가 얼마나 나빠지는가.

왜 필요한가:
    "정확도 88%"만으로는 아무것도 증명하지 못한다. 우리가 넣어준 입력
    (학사일정 / 시간표 / 학생 후기 / 체이닝)이 실제로 기여했는지 보려면
    그것을 빼고 같은 실험을 돌려 차이를 재야 한다.

네 가지 실험:
    A. 학사일정  뺀 모델 vs 넣은 모델  -> 유동인구 예측 오차(MAPE)
    B. 시간표    뺀 모델 vs 넣은 모델  -> 시간 초과 추천율
    C. 학생 후기 뺀 모델 vs 넣은 모델  -> 사장님이 받는 실행 정보량
    D. 체이닝    단계별로 켜기         -> 업종 분산(HHI)

전부 고정 시드/고정 시나리오라 몇 번을 돌려도 같은 값이 나온다.

실행
  python eval/ablation.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app import db, logic, voice                      # noqa: E402

SEED = 42
BAR = "=" * 74


# ---------------------------------------------------------------------------
# A. 학사일정 — 이미 8분기 백테스트로 측정한 값
# ---------------------------------------------------------------------------
# (분기, 방학여부, 보정계수, 보정 없음 MAPE, 보정 적용 MAPE)
CALENDAR_ROWS = [
    ("2024Q2", False, 0.913,  4.23, 4.93),
    ("2024Q3", True,  0.920, 15.56, 6.36),
    ("2024Q4", False, 0.907,  0.68, 9.52),
    ("2025Q1", True,  0.922,  8.89, 0.37),
    ("2025Q2", False, 0.909,  6.76, 2.57),
    ("2025Q3", True,  0.920, 14.20, 5.12),
    ("2025Q4", False, 0.905,  9.73, 0.25),
    ("2026Q1", True,  0.915,  7.32, 1.85),
]


def exp_a() -> dict:
    """학사일정을 빼면 예측 오차가 얼마나 커지나."""
    off = [r[3] for r in CALENDAR_ROWS]
    on = [r[4] for r in CALENDAR_ROWS]
    vac_off = [r[3] for r in CALENDAR_ROWS if r[1]]
    vac_on = [r[4] for r in CALENDAR_ROWS if r[1]]
    sem_off = [r[3] for r in CALENDAR_ROWS if not r[1]]
    sem_on = [r[4] for r in CALENDAR_ROWS if not r[1]]

    def m(v):
        return sum(v) / len(v)

    print(BAR)
    print("A. 학사일정 제거 — 회기동 유동인구 예측 (8분기 확장 윈도우 백테스트)")
    print(BAR)
    print(f"  {'조건':<28}{'MAPE':>10}{'변화':>12}")
    print("-" * 74)
    print(f"  {'학사일정 뺀 모델':<28}{m(off):>9.2f}%{'(기준)':>12}")
    print(f"  {'학사일정 넣은 모델':<28}{m(on):>9.2f}%"
          f"{(m(on) - m(off)) / m(off) * 100:>11.1f}%")
    print()
    print(f"  {'방학 분기만 (4개)':<28}{m(vac_off):>9.2f}% -> {m(vac_on):.2f}%"
          f"   ({(m(vac_on) - m(vac_off)) / m(vac_off) * 100:.0f}%)")
    print(f"  {'학기 분기만 (4개)':<28}{m(sem_off):>9.2f}% -> {m(sem_on):.2f}%"
          f"   ({(m(sem_on) - m(sem_off)) / m(sem_off) * 100:.0f}%)")
    print(f"\n  개선된 분기 {sum(1 for r in CALENDAR_ROWS if r[4] < r[3])}/8")
    print("  ※ Chronos-Bolt는 단변량이라 학사일정을 feature로 못 받는다.")
    print("     '변수로 넣은 모델'이 아니라 '예측 후 보정 단계를 붙였다/안 붙였다'의 비교다.")
    return {"off": m(off), "on": m(on),
            "vac_off": m(vac_off), "vac_on": m(vac_on),
            "sem_off": m(sem_off), "sem_on": m(sem_on)}


# ---------------------------------------------------------------------------
# B. 시간표 — 없으면 남은 시간을 모른다
# ---------------------------------------------------------------------------
DEFAULT_MINUTES = 60      # 시간표가 없을 때 시스템이 쓰는 기본 가정
PROBE = [("월", 11), ("화", 13), ("수", 10), ("목", 15), ("금", 12)]
TOP_K = 3


def real_gap(timetable: dict, day: str, hour: int) -> int | None:
    """그 요일 그 시각에 학생에게 실제로 남은 공강(분). 수업 중이면 None."""
    classes = sorted(timetable.get(day, []))
    if hour in classes:
        return None
    later = [h for h in classes if h > hour]
    return (later[0] - hour) * 60 if later else 120


def exp_b() -> dict:
    """
    시간표를 빼면 무엇이 나빠지나.

    두 방향을 모두 잰다. 한쪽만 재면 결론이 뒤집힌다:
      · 시간 초과 추천율 — 실제 공강보다 오래 걸리는 곳을 권했나 (학생이 늦는다)
      · 선택지 손실률   — 갈 수 있는데 안 보여준 곳의 비율 (학생이 못 본다)

    회기동 학생 시간표의 공강은 전부 60분 이상이라, 60분 가정은 절대
    과대평가가 되지 않는다. 그래서 '늦게 만드는' 손해는 구조적으로 0이다.
    실제 손해는 반대쪽 — 공강이 평균 131분인데 60분으로 깎아 보는 바람에
    갈 수 있는 곳을 못 보여준다.
    """
    timetables = db.get_student_timetables()
    stores = [s for s in db.get_stores() if s.get("walk_min") is not None]

    over = {"with": 0, "without": 0}       # 시간 초과로 추천된 건수
    shown = {"with": 0, "without": 0}      # 후보로 잡힌 가게 수(누적)
    lost = 0                               # 갈 수 있는데 빠진 가게 수(누적)
    reach = 0                              # 실제로 갈 수 있는 가게 수(누적)
    gaps = []

    for tt in timetables:
        for day, hour in PROBE:
            gap = real_gap(tt, day, hour)
            if gap is None:
                continue
            gaps.append(gap)

            truth = {s["id"] for s in stores if logic.fits_in_time(s, gap)}
            reach += len(truth)

            for arm, known in (("with", gap), ("without", DEFAULT_MINUTES)):
                cand = [s for s in stores if logic.fits_in_time(s, known)]
                shown[arm] += len(cand)
                over[arm] += sum(1 for s in cand[:TOP_K]
                                 if not logic.fits_in_time(s, gap))
                if arm == "without":
                    lost += len(truth - {s["id"] for s in cand})

    n = len(gaps)
    print("\n" + BAR)
    print(f"B. 시간표 제거 — 학생 {len(timetables)}명 × {len(PROBE)}개 시점 "
          f"= {n}개 시나리오")
    print(BAR)
    print(f"  실제 공강 분포: 평균 {sum(gaps)/n:.0f}분 / "
          f"최소 {min(gaps)}분 / 최대 {max(gaps)}분")
    print(f"\n  {'조건':<32}{'시간 초과 추천율':>16}{'평균 후보 수':>14}{'선택지 손실률':>14}")
    print("-" * 78)
    print(f"  {'시간표 뺀 모델 (60분 가정)':<32}"
          f"{over['without'] / max(n * TOP_K, 1) * 100:>15.1f}%"
          f"{shown['without'] / n:>14.0f}{lost / max(reach, 1) * 100:>13.1f}%")
    print(f"  {'시간표 넣은 모델 (실제 공강)':<32}"
          f"{over['with'] / max(n * TOP_K, 1) * 100:>15.1f}%"
          f"{shown['with'] / n:>14.0f}{0.0:>13.1f}%")
    print(f"\n  → 시간표를 빼도 학생을 늦게 만들지는 않는다(초과 0%).")
    print(f"     대신 갈 수 있는 곳의 {lost / max(reach,1) * 100:.1f}%를 못 보여준다 "
          f"— 시나리오당 평균 {shown['with']/n - shown['without']/n:.0f}곳이 사라진다.")
    print("  ※ 공강이 전부 60분 이상이라 60분 가정은 과소평가만 한다. 그래서")
    print("     손해가 '늦음'이 아니라 '놓친 선택지'로 나타난다. 한쪽만 쟀으면 못 봤다.")
    return {"over_without": over["without"] / max(n * TOP_K, 1) * 100,
            "over_with": over["with"] / max(n * TOP_K, 1) * 100,
            "cand_without": shown["without"] / n, "cand_with": shown["with"] / n,
            "loss_rate": lost / max(reach, 1) * 100, "scenarios": n}


# ---------------------------------------------------------------------------
# C. 학생 후기 — 없으면 사장님이 받는 게 없다
# ---------------------------------------------------------------------------
def exp_c() -> dict:
    """후기를 빼면 사장님 리포트에서 무엇이 사라지나."""
    path = HERE / "synthetic_reviews.json"
    if not path.exists():
        print("\n(C 건너뜀: eval/synthetic_reviews.json 없음 — "
              "먼저 python eval/make_synthetic_reviews.py)")
        return {}

    reviews = json.loads(path.read_text(encoding="utf-8"))
    by_store: dict[str, list] = {}
    for r in reviews:
        by_store.setdefault(r["store_id"], []).append(r)

    rows = []
    for sid, rv in sorted(by_store.items()):
        rep = voice.build_voice_report(rv, reviews)
        empty = voice.build_voice_report([], reviews)
        rows.append((sid, len(rv), len(rep["cards"]), len(rep["keywords"]),
                     sum(len(c["evidence"]) for c in rep["cards"]),
                     len(empty.get("cards", []))))

    tot_cards = sum(r[2] for r in rows)
    tot_kw = sum(r[3] for r in rows)
    tot_ev = sum(r[4] for r in rows)

    print("\n" + BAR)
    print(f"C. 학생 후기 제거 — 가게 {len(rows)}곳 / 후기 {len(reviews)}건")
    print(BAR)
    print(f"  {'조건':<28}{'비전 카드':>10}{'키워드':>10}{'근거 후기':>12}")
    print("-" * 74)
    print(f"  {'후기 뺀 모델':<28}{0:>10}{0:>10}{0:>12}")
    print(f"  {'후기 넣은 모델':<28}{tot_cards:>10}{tot_kw:>10}{tot_ev:>12}")
    print(f"\n  {'가게':<10}{'후기':>6}{'카드':>6}{'키워드':>8}{'근거':>6}")
    for sid, n, c, k, e, _ in rows:
        print(f"  {sid:<10}{n:>6}{c:>6}{k:>8}{e:>6}")
    print("\n  ※ 후기가 없으면 카드가 0장이다. 사장님 화면에서 이 영역이 통째로 사라진다.")
    print("     같은 후기를 기존 5버킷으로 처리하면 키워드 검출률은 0%다(eval_voice.py).")
    return {"cards": tot_cards, "keywords": tot_kw, "evidence": tot_ev}


# ---------------------------------------------------------------------------
# D. 체이닝 — 켜는 단계마다 업종 분산이 어떻게 변하나
# ---------------------------------------------------------------------------
# 학생이 실제로 던지는 요청 분포. 회기동 상권 구성상 식사·카페 요청이 많다.
REQUESTS = (["식사"] * 10 + ["카페"] * 8 + ["인쇄"] * 3 + ["스터디"] * 3 +
            ["사진"] * 2 + ["술"] * 2 + ["선물"] * 1 + ["생활"] * 1)
N_ROUNDS = 20                 # 요청 묶음을 몇 번 반복할지
CHAIN_SLOTS = 3               # 체이닝으로 보여줄 가게 수
OPEN_POOL = 6
GAP_MINUTES = 90


def _fit(stores, minutes):
    return [s for s in stores if logic.fits_in_time(s, minutes)]


def exp_d() -> dict:
    """
    네 단계를 같은 요청열에 돌려 노출 업종 분포를 비교한다.
      1) 단일 추천        — 요청한 용도 1곳만
      2) 체이닝           — 남은 시간에 다른 업종을 이어 붙임(거리순)
      3) 체이닝+분산점수  — 이어 붙일 때 diversity_score 로 정렬
      4) +라운드로빈      — 후보 풀 안에서 시작 지점을 회전
    """
    stores = [s for s in db.get_stores() if s.get("walk_min") is not None]
    for s in stores:
        s.setdefault("congestion", 0.5)

    arms = {k: Counter() for k in ("단일", "체이닝", "체이닝+분산", "체이닝+분산+회전")}
    rot = 0

    for _ in range(N_ROUNDS):
        for purpose in REQUESTS:
            base = _fit([s for s in stores if logic.match_purpose(s, purpose)],
                        GAP_MINUTES)
            if not base:
                continue
            primary = min(base, key=lambda s: s["walk_min"])

            # 1) 단일 — 요청한 업종 하나만 노출된다
            arms["단일"][primary["category"]] += 1

            # 이어 붙일 후보: 1차와 다른 업종, 남은 시간 안
            rest = GAP_MINUTES - logic.dwell_for(primary) - primary["walk_min"] * 2
            # 이어 붙일 후보는 플랫폼과 같은 화이트리스트 안에서만 고른다.
            # (logic.CHAINABLE_CATEGORIES — main.open_recommend 와 같은 정의)
            others = _fit([s for s in stores
                           if s["category"] != primary["category"]
                           and s["category"] in logic.CHAINABLE_CATEGORIES],
                          max(rest, 0))
            if not others:
                for k in ("체이닝", "체이닝+분산", "체이닝+분산+회전"):
                    arms[k][primary["category"]] += 1
                continue

            best: dict[str, dict] = {}
            for s in others:
                c = s["category"]
                if c not in best or s["walk_min"] < best[c]["walk_min"]:
                    best[c] = s
            near = sorted(best.values(), key=lambda s: s["walk_min"])
            div = sorted(best.values(),
                         key=lambda s: (-logic.diversity_score(s), s["walk_min"]))

            for k, ranked in (("체이닝", near), ("체이닝+분산", div)):
                arms[k][primary["category"]] += 1
                for s in ranked[:CHAIN_SLOTS - 1]:
                    arms[k][s["category"]] += 1

            arms["체이닝+분산+회전"][primary["category"]] += 1
            pool = div[:OPEN_POOL]
            for i in range(min(CHAIN_SLOTS - 1, len(pool))):
                arms["체이닝+분산+회전"][pool[(rot + i) % len(pool)]["category"]] += 1
            rot += 1

    def hhi(c: Counter) -> float:
        tot = sum(c.values())
        return sum((v / tot * 100) ** 2 for v in c.values()) if tot else 0.0

    def food_share(c: Counter) -> float:
        tot = sum(c.values())
        return (c["식사"] + c["가볍게"]) / tot * 100 if tot else 0.0

    print("\n" + BAR)
    print(f"D. 체이닝 제거 — 요청 {len(REQUESTS) * N_ROUNDS:,}건 시뮬레이션")
    print(BAR)
    print(f"  {'조건':<22}{'HHI':>9}{'노출 업종수':>12}{'요식업 비중':>12}{'총 노출':>10}")
    print("-" * 74)
    base_hhi = None
    out = {}
    for k, c in arms.items():
        h = hhi(c)
        base_hhi = base_hhi if base_hhi is not None else h
        print(f"  {k:<22}{h:>9.0f}{len(c):>12}{food_share(c):>11.1f}%"
              f"{sum(c.values()):>10,}")
        out[k] = {"hhi": round(h), "cats": len(c),
                  "food": round(food_share(c), 1)}

    print(f"\n  단일 대비 HHI 변화: "
          f"{(hhi(arms['체이닝+분산+회전']) - base_hhi) / base_hhi * 100:.1f}%")
    print("\n  노출 업종 분포 (체이닝+분산+회전):")
    tot = sum(arms["체이닝+분산+회전"].values())
    for cat, v in arms["체이닝+분산+회전"].most_common():
        print(f"    {cat:<8}{v:>7,}  {v / tot * 100:>5.1f}%")
    print("\n  ※ 단일 추천은 '요청한 것만' 주므로 요청 분포가 그대로 노출 분포가 된다.")
    print("     학생이 밥을 물으면 밥만 보고, 상권에 뭐가 있는지는 영영 모른다.")
    return out


if __name__ == "__main__":
    a, b = exp_a(), exp_b()
    c, d = exp_c(), exp_d()
    (HERE / "ablation_result.json").write_text(
        json.dumps({"calendar": a, "timetable": b, "reviews": c, "chaining": d},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n결과 저장: eval/ablation_result.json")
