# -*- coding: utf-8 -*-
"""
소상공인시장진흥공단 상가(상권)정보 -> 회기동만 추출

원본은 UTF-8인데 Excel이 cp949로 읽어서 글자가 깨진다.
여기서는 회기동만 잘라내고 **UTF-8 BOM**으로 저장해, Excel에서 더블클릭만 해도
바로 열리게 만든다. (BOM이 있으면 Excel이 UTF-8임을 자동 인식)

실행
  python scripts/extract_smallbiz.py --zip "<원본 zip 경로>"
"""
import argparse
import csv
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

TARGET_DONG = "회기동"
TARGET_SIGUNGU = "동대문구"

# 우리 앱 업종으로 매핑 (상권업종중분류명 기준)
# 실제 회기동 데이터의 중분류 분포를 확인해서 작성했다.
CATEGORY_MAP = {
    # 음식
    "한식": "한식", "중식": "중식", "일식": "일식", "서양식": "양식",
    "기타 간이": "분식",          # 분식·김밥·토스트 등
    "비알코올": "카페",           # 커피전문점·카페
    "주점": "술집",
    "기타 외국식": "양식", "출장 음식": "한식",
    # 소매
    "종합 소매": "편의점", "식료품 소매": "편의점",
    "오락용품 소매": "문구", "서적·문구 소매": "문구",
    "섬유·의복·신발 소매": "의류",
    "화초·애완 소매": "꽃집",
    # 서비스
    "이용·미용": "미용실",
    "사진 촬영": "사진",
    "인쇄": "인쇄", "사무 지원": "인쇄",
    # 문화·학습
    "도서관·사적지": "서점",
    "유원지·오락": "오락",
    "스포츠 서비스": "스포츠",
}

# 소분류로 더 정확히 잡아내는 예외 (중분류만으로는 뭉뚱그려지는 것들)
DETAIL_OVERRIDE = [
    # 순서 주의 — 위에서부터 먼저 매칭된다.
    # '독서실/스터디 카페'가 '카페'로 새지 않도록 스터디카페를 앞에 둔다.
    (("독서실", "스터디"), "스터디카페"),
    (("커피", "카페", "제과", "베이커리", "빵"), "카페"),
    (("문구", "팬시"), "문구"),
    (("꽃", "화훼"), "꽃집"),
    (("서점", "책"), "서점"),
    (("복사", "출력", "인쇄"), "인쇄"),
    (("돈가스", "돈까스", "일식", "초밥", "라멘"), "일식"),
    (("피자", "파스타", "스테이크", "햄버거"), "양식"),
    (("치킨", "닭"), "치킨"),
    (("분식", "김밥", "떡볶이", "토스트"), "분식"),
]


def find_seoul(z: zipfile.ZipFile):
    for info in z.infolist():
        try:
            name = info.filename.encode("cp437").decode("cp949")
        except Exception:
            name = info.filename
        if "서울" in name:
            return info, name
    raise SystemExit("서울 CSV를 찾지 못했습니다.")


def run(zip_path: Path, out_dir: Path):
    z = zipfile.ZipFile(zip_path)
    info, display = find_seoul(z)
    print(f"[1/3] 서울 파일 읽는 중 — {display} ({info.file_size / 1024 / 1024:.0f} MB)")

    rows, header = [], None
    with z.open(info) as fp:
        text = io.TextIOWrapper(fp, encoding="utf-8", newline="")
        reader = csv.reader(text)
        header = next(reader)
        idx = {name: i for i, name in enumerate(header)}
        col_dong = idx.get("행정동명")
        col_gu = idx.get("시군구명")

        for row in reader:
            if len(row) <= max(col_dong, col_gu):
                continue
            if row[col_dong] == TARGET_DONG and row[col_gu] == TARGET_SIGUNGU:
                rows.append(row)

    print(f"[2/3] 회기동 추출: {len(rows)}곳")

    out_dir.mkdir(parents=True, exist_ok=True)

    # (1) Excel에서 바로 열리는 CSV — UTF-8 BOM
    csv_path = out_dir / "회기동_상가정보.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"      Excel용 저장 -> {csv_path.name}")

    # (2) 앱에서 쓸 JSON
    idx = {name: i for i, name in enumerate(header)}

    def get(row, col):
        i = idx.get(col)
        return row[i] if i is not None and i < len(row) else ""

    stores = []
    for r in rows:
        mid = get(r, "상권업종중분류명")
        detail = get(r, "상권업종소분류명")
        name = get(r, "상호명")

        # 소분류·상호명으로 먼저 정밀 판정, 없으면 중분류로
        cat = None
        for keys, mapped in DETAIL_OVERRIDE:
            if any(k in detail or k in name for k in keys):
                cat = mapped
                break
        if not cat:
            cat = CATEGORY_MAP.get(mid)
        if not cat:
            continue
        lat, lng = get(r, "위도"), get(r, "경도")
        try:
            lat, lng = float(lat), float(lng)
        except ValueError:
            continue
        stores.append({
            "id": "sb" + get(r, "상가업소번호"),
            "name": get(r, "상호명"),
            "branch": get(r, "지점명"),
            "category": cat,
            "category_detail": get(r, "상권업종소분류명"),
            "address": get(r, "도로명주소") or get(r, "지번주소"),
            "lat": lat, "lng": lng,
            "source": "소상공인시장진흥공단(2026-03)",
        })

    json_path = out_dir / "회기동_상가정보.json"
    json_path.write_text(json.dumps(stores, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"      앱용 저장 -> {json_path.name} ({len(stores)}곳)")

    print("\n[3/3] 업종 분포")
    for cat, n in Counter(s["category"] for s in stores).most_common():
        print(f"      {cat:8s} {n:4d}")

    print("\n미리보기")
    for s in stores[:10]:
        print(f"      {s['category']:5s} {s['name']} ({s['category_detail']})")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", default=str(base / "data" / "raw"))
    a = ap.parse_args()
    run(Path(a.zip), Path(a.out))
