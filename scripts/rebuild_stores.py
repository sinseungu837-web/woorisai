# -*- coding: utf-8 -*-
"""
소상공인 상가정보(회기동 706곳)를 앱 stores.json 으로 교체

  - OSM 데이터보다 업종 분류가 정확하고 도로명주소가 있다
  - 기준점(경희대 정문) 도보시간을 미리 계산해 넣는다
    -> GPS를 거부한 사용자에게 보여줄 기본값
  - 회식럽 등 수기 등록 점포는 유지

실행
  python scripts/rebuild_stores.py --write
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

VALHALLA = "https://valhalla1.openstreetmap.de/sources_to_targets"
DEFAULT_ORIGIN = {"lat": 37.5967, "lon": 127.0517}      # 경희대 정문
BATCH, DELAY = 40, 1.2

PRICE_HINT = {
    "카페": 4500, "한식": 9000, "중식": 9000, "일식": 12000, "양식": 13000,
    "분식": 6500, "치킨": 18000, "술집": 15000, "편의점": 3000,
    "서점": 12000, "문구": 5000, "꽃집": 15000, "사진": 8000,
    "인쇄": 500, "스터디카페": 3500, "미용실": 15000, "의류": 20000,
    "오락": 10000, "스포츠": 12000,
}
CAPACITY_HINT = {"한식": 24, "중식": 24, "일식": 20, "양식": 20,
                 "술집": 30, "분식": 12, "치킨": 24, "카페": 20}


def matrix(origin: dict, targets: list) -> list:
    payload = {"sources": [origin],
               "targets": [{"lat": t["lat"], "lon": t["lng"]} for t in targets],
               "costing": "pedestrian"}
    compact = json.dumps(payload, separators=(",", ":"))
    url = VALHALLA + "?json=" + urllib.parse.quote(compact, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "woorisai/1.0 (hackathon)"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())["sources_to_targets"][0]


def run(write: bool):
    base = Path(__file__).resolve().parent.parent
    src = base / "data" / "raw" / "회기동_상가정보.json"
    dst = base / "data" / "stores.json"

    raw = json.loads(src.read_text(encoding="utf-8"))
    print(f"소상공인 데이터 {len(raw)}곳 로드")

    stores = []
    for r in raw:
        cat = r["category"]
        stores.append({
            "id": r["id"],
            "name": r["name"] + (f" {r['branch']}" if r.get("branch") else ""),
            "category": cat,
            "category_detail": r.get("category_detail", ""),
            "address": r.get("address", ""),
            "walk_min": None,          # 아래에서 계산
            "walk_meters": None,
            "price_from": PRICE_HINT.get(cat, 8000),
            "capacity": CAPACITY_HINT.get(cat, 0),
            "description": "",         # 상인이 등록 시 직접 작성
            "hours": "",
            "lat": r["lat"], "lng": r["lng"],
            "owner": None,
            "source": r.get("source", "소상공인시장진흥공단"),
        })

    # 수기 등록 점포(회식럽 등) 유지
    manual = []
    if dst.exists():
        old = json.loads(dst.read_text(encoding="utf-8"))
        manual = [s for s in old if s["id"].startswith("s") and not s["id"].startswith("sb")
                  and not s["id"].startswith("osm")]
        names = {s["name"] for s in stores}
        manual = [m for m in manual if m["name"] not in names]
    print(f"수기 등록 유지: {len(manual)}곳")

    all_stores = manual + stores

    # 기준점 도보시간 (GPS 거부 시 기본값)
    targets = [s for s in all_stores if s.get("lat")]
    print(f"\n기준점(경희대 정문) 도보시간 계산: {len(targets)}곳")
    ok = 0
    for i in range(0, len(targets), BATCH):
        chunk = targets[i:i + BATCH]
        try:
            for s, cell in zip(chunk, matrix(DEFAULT_ORIGIN, chunk)):
                if cell.get("time") is not None:
                    s["walk_min"] = max(1, round(cell["time"] / 60))
                    s["walk_meters"] = round(cell["distance"] * 1000)
                    ok += 1
        except Exception as e:
            print(f"  배치 {i // BATCH + 1} 실패: {e}")
        print(f"  {min(i + BATCH, len(targets))}/{len(targets)}")
        time.sleep(DELAY)

    # 실패분은 대략값으로 채워 화면이 비지 않게
    for s in all_stores:
        if s.get("walk_min") is None:
            s["walk_min"] = 10

    from collections import Counter
    print(f"\n총 {len(all_stores)}곳 · 도보시간 계산 {ok}곳")
    for c, n in Counter(s["category"] for s in all_stores).most_common():
        print(f"  {c:8s} {n:4d}")

    near = sorted([s for s in all_stores if s.get("walk_meters")],
                  key=lambda s: s["walk_min"])[:8]
    print("\n가까운 순")
    for s in near:
        print(f"  도보{s['walk_min']:2d}분 {s['walk_meters']:4d}m  {s['category']:5s} {s['name']}")

    if write:
        dst.write_text(json.dumps(all_stores, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장 -> {dst}")
    else:
        print("\n--write 를 붙이면 저장합니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    run(ap.parse_args().write)
