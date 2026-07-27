# -*- coding: utf-8 -*-
"""
회기동 상가 업종 재분류 — 음식 통합(치킨+술집→술·치킨) + 버려졌던 비음식 추가.

  입력 : data/raw/회기동_상가정보.csv  (원본 963곳, 좌표·중분류 포함)
  출력 : data/raw/회기동_상가정보.json (앱용, 재매핑 결과)

기존 stores.json 의 도보시간(walk_min/meters/walk_campus)은
rebuild + campus 스크립트에서 id 매칭으로 최대한 재사용한다.

실행
  python scripts/remap_categories.py            # 분포만 출력(dry)
  python scripts/remap_categories.py --write     # json 저장
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "raw" / "회기동_상가정보.csv"
DST = BASE / "data" / "raw" / "회기동_상가정보.json"

# --- 중분류 -> 앱 업종 (원본 유지 + 버려졌던 것 추가) ---
MID_MAP = {
    # 음식 (요리 종류 유지)
    "한식": "한식", "중식": "중식", "일식": "일식", "서양식": "양식",
    "기타 외국식": "양식", "출장 음식": "한식", "동남아시아": "양식",
    "기타 간이": "분식", "비알코올": "카페",
    "주점": "술·치킨",                      # ← 통합
    # 소매·생활
    "종합 소매": "편의점", "식료품 소매": "편의점", "담배 소매": "편의점",
    "오락용품 소매": "문구", "서적·문구 소매": "문구", "장식품 소매": "문구",
    "섬유·의복·신발 소매": "의류",
    "화초·애완 소매": "꽃집", "식물 소매": "꽃집",
    "애완동물·용품 소매": "반려동물",
    "가전·통신 소매": "통신", "컴퓨터 수리": "통신",
    "안경·정밀기기 소매": "안경",
    "세탁": "세탁",
    "부동산 서비스": "부동산",
    "기타 숙박": "숙박", "일반 숙박": "숙박",
    # 서비스·의료·학습
    "이용·미용": "미용실",
    "의약·화장품 소매": "약국",             # 소분류로 약국/화장품 세분(아래)
    "의원": "병원", "병원": "병원",
    "일반 교육": "학원", "기타 교육": "학원", "교육 지원": "학원",
    "사진 촬영": "사진",
    "인쇄": "인쇄", "사무 지원": "인쇄", "인쇄·제품제작": "인쇄",
    "도서관·사적지": "서점",
    "유원지·오락": "오락",
    "스포츠 서비스": "스포츠",
}

# --- 소분류/상호명 우선 판정(중분류보다 먼저) ---
DETAIL_OVERRIDE = [
    (("독서실", "스터디"), "스터디카페"),
    (("커피", "카페", "제과", "베이커리", "빵"), "카페"),
    (("요가", "필라테스", "헬스", "피트니스"), "스포츠"),
    (("약국",), "약국"),
    (("화장품",), "화장품"),
    (("의료기기",), "약국"),
    (("명함", "간판", "광고물"), "인쇄"),
    (("문구", "팬시"), "문구"),
    (("꽃", "화훼"), "꽃집"),
    (("서점", "책"), "서점"),
    (("복사", "출력", "인쇄"), "인쇄"),
    (("돈가스", "돈까스", "초밥", "라멘", "스시"), "일식"),
    (("피자", "파스타", "스테이크", "햄버거", "버거"), "양식"),
    (("치킨", "닭강정"), "술·치킨"),
    (("호프", "포차", "주점", "맥주", "술집"), "술·치킨"),
    (("분식", "김밥", "떡볶이", "토스트"), "분식"),
]


def classify(mid: str, detail: str, name: str) -> str | None:
    for keys, mapped in DETAIL_OVERRIDE:
        if any(k in detail or k in name for k in keys):
            return mapped
    return MID_MAP.get(mid)


def run(write: bool):
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))   # BOM 제거
    stores, dropped = [], Counter()
    drop_detail = defaultdict(Counter)
    for r in rows:
        mid = (r.get("상권업종중분류명") or "").strip()
        detail = (r.get("상권업종소분류명") or "").strip()
        name = (r.get("상호명") or "").strip()
        cat = classify(mid, detail, name)
        if not cat:
            dropped[mid] += 1
            drop_detail[mid][detail] += 1
            continue
        try:
            lat, lng = float(r.get("위도")), float(r.get("경도"))
        except (TypeError, ValueError):
            continue
        stores.append({
            "id": "sb" + (r.get("상가업소번호") or "").strip(),
            "name": name,
            "branch": (r.get("지점명") or "").strip(),
            "category": cat,
            "category_detail": detail,
            "address": (r.get("도로명주소") or r.get("지번주소") or "").strip(),
            "lat": lat, "lng": lng,
            "source": "소상공인시장진흥공단(2026-03)",
        })

    print(f"원본 {len(rows)}곳 -> 채택 {len(stores)}곳 / 제외 {sum(dropped.values())}곳\n")
    print("=== 새 업종 분포 ===")
    for c, n in Counter(s["category"] for s in stores).most_common():
        print(f"  {c:6s} {n:4d}")
    print("\n=== 제외된 중분류(순수 B2B/산업) ===")
    for m, n in dropped.most_common():
        print(f"  {m}: {n}")

    if write:
        DST.write_text(json.dumps(stores, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장 -> {DST} ({len(stores)}곳)")
    else:
        print("\n--write 를 붙이면 저장합니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    run(ap.parse_args().write)
