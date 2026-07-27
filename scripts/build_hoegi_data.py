# -*- coding: utf-8 -*-
"""
회기동 실데이터 추출 -> Chronos 입력용 시계열 생성

입력
  1) 서울시 상권분석서비스 추정매출 (sales_20XX.zip)  — 회기동 named 상권 2곳
  2) 해커톤 제공 데이터 (data.xlsx)                    — 회기동 행정동 유동인구

출력
  woorisai/data/hoegi_timeseries.json

실행
  python scripts/build_hoegi_data.py --raw <seoul_raw 경로> --xlsx <data.xlsx 경로>
"""
import argparse
import json
from pathlib import Path

import pandas as pd

# 회기동 named 상권 — 경희대삼거리, 경희대
HOEGI_CODES = [3110205, 3120064]
DONG = "회기동"
YEARS = ["2021", "2022", "2023", "2024", "2025"]

DAY_COLS = {
    "월": "월요일_매출_금액", "화": "화요일_매출_금액", "수": "수요일_매출_금액",
    "목": "목요일_매출_금액", "금": "금요일_매출_금액",
    "토": "토요일_매출_금액", "일": "일요일_매출_금액",
}
TIME_COLS = {
    "00~06": "시간대_00~06_매출_금액", "06~11": "시간대_06~11_매출_금액",
    "11~14": "시간대_11~14_매출_금액", "14~17": "시간대_14~17_매출_금액",
    "17~21": "시간대_17~21_매출_금액", "21~24": "시간대_21~24_매출_금액",
}


def load_sales(raw_dir: Path) -> pd.DataFrame:
    frames = []
    for yr in YEARS:
        zip_path = raw_dir / f"sales_{yr}.zip"
        if not zip_path.exists():
            print(f"  ! {zip_path.name} 없음, 건너뜀")
            continue
        df = pd.read_csv(zip_path, encoding="cp949")
        frames.append(df[df["상권_코드"].isin(HOEGI_CODES)])
    if not frames:
        raise SystemExit("추정매출 데이터를 하나도 못 읽었습니다.")
    return pd.concat(frames, ignore_index=True)


def load_population(xlsx_path: Path) -> pd.DataFrame | None:
    if not xlsx_path.exists():
        print(f"  ! {xlsx_path} 없음, 유동인구 생략")
        return None
    pop = pd.read_excel(pd.ExcelFile(xlsx_path), "유동인구 데이터")
    return pop[pop["행정동명"] == DONG]


def build(raw_dir: Path, xlsx_path: Path, out_path: Path):
    print("[1/4] 추정매출 로드 (회기동 상권 2곳)")
    sales = load_sales(raw_dir)
    quarters = sorted(sales["기준_년분기_코드"].unique())
    print(f"      {len(sales)}행 · {len(quarters)}개 분기 ({quarters[0]}~{quarters[-1]})")

    # --- 분기별 총매출 시계열 (Chronos 입력) ---
    q_sales = sales.groupby("기준_년분기_코드")["당월_매출_금액"].sum().sort_index()
    q_count = sales.groupby("기준_년분기_코드")["당월_매출_건수"].sum().sort_index()

    # --- 업종별 분기 매출 (업종 단위 추이용) ---
    by_cat = {}
    for cat, g in sales.groupby("서비스_업종_코드_명"):
        s = g.groupby("기준_년분기_코드")["당월_매출_금액"].sum().sort_index()
        if len(s) >= 8 and s.iloc[0] > 0:            # 표본 부족 업종 제외
            by_cat[cat] = {"quarters": [int(q) for q in s.index],
                           "values": [float(v) for v in s.values]}

    # --- 요일 프로파일 (상대 비중) ---
    day_total = {k: float(sales[v].sum()) for k, v in DAY_COLS.items() if v in sales.columns}
    day_sum = sum(day_total.values()) or 1
    day_profile = {k: round(v / day_sum, 4) for k, v in day_total.items()}

    # --- 시간대 프로파일 (상대 비중) ---
    time_total = {k: float(sales[v].sum()) for k, v in TIME_COLS.items() if v in sales.columns}
    time_sum = sum(time_total.values()) or 1
    time_profile = {k: round(v / time_sum, 4) for k, v in time_total.items()}

    print("[2/4] 요일·시간대 프로파일 산출")
    print(f"      요일 최다: {max(day_profile, key=day_profile.get)}")
    print(f"      시간대 최다: {max(time_profile, key=time_profile.get)}")

    # --- 유동인구 시계열 ---
    print("[3/4] 유동인구 로드 (제공 데이터)")
    pop_series, vacation = None, None
    pop = load_population(xlsx_path)
    if pop is not None:
        qcols = [c for c in pop.columns if "년_" in c]
        totals = pop[qcols].sum()
        pop_series = {"quarters": list(qcols),
                      "values": [float(v) for v in totals.values]}

        # 방학 근사(1·3분기) vs 학기(2·4분기) 비교 -> 방학 보정계수 근거
        q1 = [c for c in qcols if "1분기" in c]
        q2 = [c for c in qcols if "2분기" in c]
        q3 = [c for c in qcols if "3분기" in c]
        q4 = [c for c in qcols if "4분기" in c]
        vac_avg = (totals[q1].sum() + totals[q3].sum()) / (len(q1) + len(q3))
        sem_avg = (totals[q2].sum() + totals[q4].sum()) / (len(q2) + len(q4))
        pct = (vac_avg - sem_avg) / sem_avg * 100
        vacation = {
            "vacation_avg": float(vac_avg), "semester_avg": float(sem_avg),
            "change_pct": round(float(pct), 2),
            "factor": round(1 + float(pct) / 100, 3),
            "method": "1·3분기(방학 포함) 평균 vs 2·4분기(학기) 평균",
        }
        print(f"      방학기 유동 변화: {vacation['change_pct']}% -> 보정계수 {vacation['factor']}")

    # --- 저장 ---
    payload = {
        "meta": {
            "dong": DONG,
            "trade_area_codes": HOEGI_CODES,
            "quarters": [int(q) for q in quarters],
            "sources": [
                "서울 열린데이터광장 — 우리마을가게 상권분석서비스 추정매출(OA-15572)",
                "AICOSS 해커톤 제공 데이터 — 유동인구",
            ],
        },
        "sales_quarterly": {"quarters": [int(q) for q in q_sales.index],
                            "values": [float(v) for v in q_sales.values]},
        "count_quarterly": {"quarters": [int(q) for q in q_count.index],
                            "values": [float(v) for v in q_count.values]},
        "sales_by_category": by_cat,
        "day_profile": day_profile,
        "time_profile": time_profile,
        "population_quarterly": pop_series,
        "vacation_effect": vacation,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[4/4] 저장 완료 -> {out_path}")
    print(f"      업종 {len(by_cat)}개 · 분기 시계열 {len(q_sales)}포인트")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="seoul_raw 폴더 경로")
    ap.add_argument("--xlsx", required=True, help="data.xlsx 경로")
    ap.add_argument("--out", default=str(base / "data" / "hoegi_timeseries.json"))
    a = ap.parse_args()
    build(Path(a.raw), Path(a.xlsx), Path(a.out))
