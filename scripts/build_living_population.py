# -*- coding: utf-8 -*-
"""
서울 생활인구(OA-14991)에서 회기동만 추출해 분기별 시계열을 만든다.

기존 매출 데이터(2021~2025, 16분기)보다 훨씬 긴 이력(2017~, 34분기+)을 확보해서,
"Chronos-Bolt 성능이 표본 부족 때문에 안 좋았던 건지" 실제로 검증하기 위함.

다운로드 -> 회기동만 필터링 -> 원본 즉시 삭제 (용량 절약, 반기 파일 하나가 250MB+)

실행
  python scripts/build_living_population.py --years 2017 2025
"""
import argparse
import csv
import io
import json
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

DONG_CODE = "11230710"          # 회기동 행정동코드
DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"

# data.seoul.go.kr 파일 목록에서 확인한 seqNo (2017~2022=반기, 2023~=월별)
HALF_YEAR_SEQ = {
    2017: (2213, 2214), 2018: (2215, 2216), 2019: (2217, 2218),
    2020: (2219, 2220), 2021: (2221, 2222), 2022: (2223, 2224),
}
MONTHLY_SEQ_BASE = {2023: 2300, 2024: 2400, 2025: 2500, 2026: 2600}


def fetch(seq_no: int) -> bytes:
    data = f"infId=OA-14991&seqNo={seq_no}&seq={seq_no}&infSeq=3".encode()
    req = urllib.request.Request(DOWNLOAD_URL, data=data,
                                 headers={"User-Agent": "woorisai/1.0"})
    with urllib.request.urlopen(req, timeout=120) as res:
        return res.read()


def extract_dong(csv_bytes: bytes) -> dict:
    """CSV 하나에서 회기동 행만 걸러, 날짜별로 24시간 총생활인구 평균을 낸다.
    인코딩이 파일마다 다르다(2019년 10월부터 cp949로 바뀜) -> 순서대로 시도."""
    daily = defaultdict(list)
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            text = io.TextIOWrapper(io.BytesIO(csv_bytes), encoding=enc, newline="")
            reader = csv.reader(text)
            header = next(reader)
            for row in reader:
                if len(row) < 4 or row[2] != DONG_CODE:
                    continue
                date, pop = row[0], row[3]
                try:
                    daily[date].append(float(pop))
                except ValueError:
                    continue
            return {d: sum(v) / len(v) for d, v in daily.items()}
        except UnicodeDecodeError:
            daily.clear()
            continue
    print("    ! 모든 인코딩 실패, 이 파일 건너뜀")
    return {}


def quarter_of(date_str: str) -> str:
    y, m = date_str[:4], int(date_str[4:6])
    q = (m - 1) // 3 + 1
    return f"{y}{q}"


def process_zip(raw: bytes, label: str) -> dict:
    daily_all = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        for name in names:
            print(f"    {name} 처리 중...")
            try:
                daily_all.update(extract_dong(z.read(name)))
            except Exception as e:
                print(f"    ! {name} 처리 실패, 건너뜀: {e}")
    print(f"  {label}: {len(daily_all)}일 추출")
    return daily_all


CHECKPOINT = Path(__file__).resolve().parent.parent / "data" / "_lp_checkpoint.json"


def save_checkpoint(all_daily: dict):
    CHECKPOINT.write_text(json.dumps(all_daily), encoding="utf-8")


def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {}


def run(year_from: int, year_to: int, out_path: Path, resume: bool = True):
    all_daily = load_checkpoint() if resume else {}
    if all_daily:
        print(f"체크포인트에서 재개: 이미 {len(all_daily)}일 확보됨")

    for year in range(year_from, year_to + 1):
        if year in HALF_YEAR_SEQ:
            for half, seq in zip(("상반기", "하반기"), HALF_YEAR_SEQ[year]):
                label = f"{year}_{half}"
                # 이미 이 구간 데이터가 있으면 건너뜀 (예: 2017-01-01 있으면 상반기 완료로 간주)
                probe = f"{year}0101" if half == "상반기" else f"{year}0701"
                if any(d.startswith(str(year)) for d in all_daily) and probe in all_daily:
                    print(f"[{label}] 이미 있음, 건너뜀")
                    continue
                print(f"[{label}] 다운로드 중 (seq={seq})...")
                try:
                    raw = fetch(seq)
                except Exception as e:
                    print(f"  실패: {e}")
                    continue
                all_daily.update(process_zip(raw, label))
                save_checkpoint(all_daily)
                time.sleep(1)
        elif year in MONTHLY_SEQ_BASE:
            base = MONTHLY_SEQ_BASE[year]
            for m in range(1, 13):
                seq = base + m
                label = f"{year}-{m:02d}"
                probe = f"{year}{m:02d}01"
                if probe in all_daily:
                    print(f"[{label}] 이미 있음, 건너뜀")
                    continue
                print(f"[{label}] 다운로드 중 (seq={seq})...")
                try:
                    raw = fetch(seq)
                except Exception as e:
                    print(f"  건너뜀({label}): {e}")
                    continue
                all_daily.update(process_zip(raw, label))
                save_checkpoint(all_daily)
                time.sleep(1)

    # 분기별로 집계 (그 분기에 속한 날짜들의 평균)
    quarter_vals = defaultdict(list)
    for date, val in all_daily.items():
        quarter_vals[quarter_of(date)].append(val)

    quarters = sorted(quarter_vals.keys())
    values = [sum(quarter_vals[q]) / len(quarter_vals[q]) for q in quarters]

    payload = {
        "meta": {
            "dong": "회기동", "dong_code": DONG_CODE,
            "source": "서울 열린데이터광장 — 서울 생활인구(OA-14991)",
            "days_collected": len(all_daily),
        },
        "quarters": quarters,
        "values": values,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n완료 -> {out_path}")
    print(f"분기 수: {len(quarters)} ({quarters[0]} ~ {quarters[-1]})")
    for q, v in zip(quarters, values):
        print(f"  {q}: {v:,.0f}")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs=2, type=int, default=[2017, 2025])
    ap.add_argument("--out", default=str(base / "data" / "living_population_quarterly.json"))
    a = ap.parse_args()
    run(a.years[0], a.years[1], Path(a.out))
