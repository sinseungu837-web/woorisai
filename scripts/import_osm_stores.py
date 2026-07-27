# -*- coding: utf-8 -*-
"""
회기동 실제 상점 목록 수집 — OpenStreetMap Overpass API

API 키가 필요 없고 무료다. 다만 자원봉사 기반이라 누락과 폐업이 섞여 있으므로,
정확도가 필요해지면 공공데이터포털의 '소상공인시장진흥공단 상가(상권)정보'로 교체한다.
  https://www.data.go.kr/data/15083033/fileData.do

실행
  python scripts/import_osm_stores.py            # 미리보기
  python scripts/import_osm_stores.py --write    # data/stores.json 갱신
"""
import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

# 회기동 일대 (경희대 서울캠 ~ 회기역)
BBOX = (37.588, 127.045, 37.600, 127.060)
ORIGIN = (37.5967, 127.0517)          # 기준점: 경희대 정문 부근
WALK_SPEED_M_PER_MIN = 67             # 도보 4km/h

OVERPASS = "https://overpass-api.de/api/interpreter"

# OSM 태그 -> 우리 업종
CATEGORY = {
    "cafe": "카페", "restaurant": "한식", "fast_food": "분식",
    "bar": "술집", "pub": "술집",
    "convenience": "편의점", "supermarket": "편의점",
    "books": "서점", "stationery": "문구", "gift": "문구",
    "florist": "꽃집", "photo": "사진", "copyshop": "인쇄",
    "hairdresser": "미용실", "beauty": "미용실",
    "bakery": "카페", "clothes": "의류",
}
# 상호명으로 업종을 더 정확히 추정
NAME_HINT = [
    (("카페", "커피", "coffee", "cafe", "베이커리", "빵"), "카페"),
    (("떡볶이", "김밥", "분식", "토스트", "핫도그"), "분식"),
    (("호프", "포차", "맥주", "술집", "이자카야", "펍"), "술집"),
    (("문구", "팬시", "다이소"), "문구"),
    (("꽃", "플라워", "flower"), "꽃집"),
    (("서점", "북", "책방"), "서점"),
    (("프린트", "인쇄", "복사", "출력"), "인쇄"),
    (("스터디", "독서실"), "스터디카페"),
]
PRICE_HINT = {"카페": 4500, "한식": 9000, "분식": 7000, "술집": 15000,
              "편의점": 3000, "서점": 12000, "문구": 5000, "꽃집": 15000,
              "사진": 8000, "인쇄": 500, "스터디카페": 3500, "미용실": 15000,
              "의류": 20000}


def query_overpass() -> list:
    s, w, n, e = BBOX
    q = f"""[out:json][timeout:60];
(
 node["shop"]({s},{w},{n},{e});
 node["amenity"~"^(cafe|restaurant|fast_food|bar|pub)$"]({s},{w},{n},{e});
 way["shop"]({s},{w},{n},{e});
 way["amenity"~"^(cafe|restaurant|fast_food|bar|pub)$"]({s},{w},{n},{e});
);
out center 500;"""
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(OVERPASS, data=data,
                                 headers={"User-Agent": "woorisai/1.0 (hackathon)"})
    with urllib.request.urlopen(req, timeout=90) as res:
        return json.loads(res.read().decode())["elements"]


def walk_minutes(lat: float, lng: float) -> int:
    """기준점에서의 직선거리 -> 도보 분 (실제 경로는 더 길어서 1.3배 보정)"""
    r = 6371000
    p1, p2 = math.radians(ORIGIN[0]), math.radians(lat)
    dp = math.radians(lat - ORIGIN[0])
    dl = math.radians(lng - ORIGIN[1])
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    dist = 2 * r * math.asin(math.sqrt(a)) * 1.3
    return max(1, round(dist / WALK_SPEED_M_PER_MIN))


# 학생이 '갈 곳'으로 추천하면 안 되는 곳
EXCLUDE = ("장례식장", "영안실", "기숙사", "구내식당(직원)", "임직원")


def guess_category(name: str, tags: dict) -> str | None:
    if any(x in name for x in EXCLUDE):
        return None
    lower = name.lower()
    for keys, cat in NAME_HINT:
        if any(k in lower for k in keys):
            return cat
    return CATEGORY.get(tags.get("amenity")) or CATEGORY.get(tags.get("shop"))


def convert(elements: list) -> list:
    seen, out = set(), []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name or name in seen:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        cat = guess_category(name, tags)
        if not cat:
            continue
        seen.add(name)

        walk = walk_minutes(lat, lng)
        out.append({
            "id": f"osm{el['id']}",
            "name": name,
            "category": cat,
            "walk_min": walk,
            "price_from": PRICE_HINT.get(cat, 8000),
            "capacity": 0,
            "description": "",                       # 상인이 등록 시 직접 작성
            "hours": tags.get("opening_hours", ""),
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "owner": None,
            "source": "OpenStreetMap",
            "verified": False,                       # 현장 확인 전
        })
    out.sort(key=lambda s: s["walk_min"])
    return out


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="data/stores.json 에 저장")
    ap.add_argument("--keep-manual", action="store_true", default=True,
                    help="기존 수기 등록 점포(회식럽 등) 유지")
    a = ap.parse_args()

    print("Overpass API 조회 중…")
    stores = convert(query_overpass())

    from collections import Counter
    print(f"수집: {len(stores)}곳")
    for cat, n in Counter(s["category"] for s in stores).most_common():
        print(f"  {cat:10s} {n:3d}")
    print("\n가까운 순 미리보기")
    for s in stores[:12]:
        print(f"  도보{s['walk_min']:2d}분  {s['category']:6s}  {s['name']}")

    if a.write:
        path = base / "data" / "stores.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        manual = [s for s in existing if not s["id"].startswith("osm")] if a.keep_manual else []
        merged = manual + [s for s in stores
                           if s["name"] not in {m["name"] for m in manual}]
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장 완료 -> {path}  (수기 {len(manual)} + OSM {len(merged) - len(manual)})")
    else:
        print("\n--write 를 붙이면 data/stores.json 에 저장합니다.")
