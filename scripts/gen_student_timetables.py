# -*- coding: utf-8 -*-
"""
학생 시간표 분포 테스트용 합성 데이터 생성 (기본 120명).

사장님 리포트의 '요일별 공강 분포' 집계를 실제 규모로 검증하기 위한 것.
실제 한국 대학생 패턴을 반영:
  - 주 4~6과목, 과목당 1~3시간
  - 절반 정도는 주 2회 수업(월수 / 화목)
  - 금요일 수업을 피하는 경향(금공강) → 금요일 공강이 많아짐
  - 수업은 9~18시에 몰리고, 저녁(19~21시)은 대부분 공강

실행
  python scripts/gen_student_timetables.py --n 120 --write
"""
import argparse
import json
import random
from pathlib import Path

WEEK = ["월", "화", "수", "목", "금"]
# 요일별 수업 배치 가중치 — 금요일을 낮춰 '금공강' 경향 반영
DAY_WEIGHT = {"월": 1.15, "화": 1.1, "수": 1.1, "목": 1.0, "금": 0.55}
PAIRED = [("월", "수"), ("화", "목"), ("월", "수", "금")]   # 주 2~3회 수업 묶음


def place_course(table: dict, days: tuple, start: int, dur: int) -> bool:
    """겹치지 않으면 배치하고 True. 겹치면 False."""
    hours = list(range(start, start + dur))
    for d in days:
        if any(h in table.get(d, []) for h in hours):
            return False
    for d in days:
        table.setdefault(d, []).extend(hours)
    return True


def make_one(rng: random.Random) -> dict:
    table = {d: [] for d in WEEK}
    n_courses = rng.choice([4, 4, 5, 5, 5, 6])          # 대개 5과목
    placed = 0
    tries = 0
    while placed < n_courses and tries < 40:
        tries += 1
        dur = rng.choice([1, 2, 2, 3])                  # 대개 2시간
        # 주 2회 수업이면 짝지어진 요일, 아니면 단일 요일(가중치 반영)
        if rng.random() < 0.5:
            days = rng.choice(PAIRED)
            slot_dur = min(dur, 2)                       # 반복 수업은 좀 짧게
        else:
            days = (rng.choices(WEEK, weights=[DAY_WEIGHT[d] for d in WEEK])[0],)
            slot_dur = dur
        start = rng.choice([9, 10, 11, 13, 14, 15, 16])  # 점심(12) 피함
        if place_course(table, days, start, slot_dur):
            placed += 1

    return {d: sorted(set(hs)) for d, hs in table.items() if hs}


def run(n: int, out_path: Path, write: bool):
    rng = random.Random(42)                             # 재현 가능
    students = [make_one(rng) for _ in range(n)]

    # 간단 요약 (요일별 평균 공강)
    DAY_HOURS = list(range(9, 22))
    by_day = {d: 0 for d in WEEK}
    for tt in students:
        for d in WEEK:
            classes = set(tt.get(d, []))
            by_day[d] += sum(1 for h in DAY_HOURS if h not in classes)
    for d in WEEK:
        by_day[d] = round(by_day[d] / n, 1)

    print(f"생성: {n}명")
    print("요일별 평균 공강 시간(시):", by_day)
    busiest = max(by_day, key=by_day.get)
    quiet = min(by_day, key=by_day.get)
    print(f"공강 최다 요일(방문 몰림): {busiest} / 최소(한산): {quiet}")

    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(students, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        print(f"\n저장 -> {out_path}")
    else:
        print("\n--write 를 붙이면 저장합니다.")
        print("예시 3명:", students[:3])


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--out", default=str(base / "data" / "student_timetables.json"))
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    run(a.n, Path(a.out), a.write)
