# -*- coding: utf-8 -*-
"""
재매핑된 회기동 상가(893곳)를 stores.json 으로 병합.
  - 기존 id는 도보시간(walk_min/meters/walk_campus)·상인등록정보 그대로 재사용
  - 새로 편입된 가게만 Valhalla 로 도보시간 계산(경희대·한국외대)
  - 수기 등록 점포(회식럽 s*)는 유지, 음식 통합(치킨/술집→술·치킨) 반영

실행
  python scripts/merge_remap_walk.py --write
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
NEW = BASE / "data" / "raw" / "회기동_상가정보.json"
DST = BASE / "data" / "stores.json"

VALHALLA = "https://valhalla1.openstreetmap.de/sources_to_targets"
BATCH, DELAY = 40, 1.2
CAMPUSES = {
    "경희대":   {"lat": 37.5967213, "lon": 127.0519867},
    "한국외대": {"lat": 37.5970815, "lon": 127.0587413},
}
PRICE_HINT = {
    "카페": 4500, "한식": 9000, "중식": 9000, "일식": 12000, "양식": 13000,
    "분식": 6500, "술·치킨": 16000, "편의점": 3000, "서점": 12000,
    "문구": 5000, "꽃집": 15000, "사진": 8000, "인쇄": 500, "스터디카페": 3500,
    "미용실": 15000, "의류": 20000, "오락": 10000, "스포츠": 12000,
    "약국": 6000, "화장품": 12000, "병원": 8000, "학원": 0, "통신": 0,
    "세탁": 5000, "안경": 60000, "부동산": 0, "숙박": 40000, "반려동물": 15000,
}
CAPACITY_HINT = {"한식": 24, "중식": 24, "일식": 20, "양식": 20,
                 "술·치킨": 28, "분식": 12, "카페": 20}
# 세부 업종 -> 통합 그룹 (remap 산출 업종/수기 점포 모두 통일)
GROUP_MERGE = {
    "한식": "식사", "중식": "식사", "일식": "식사", "양식": "식사",
    "카페": "가볍게", "분식": "가볍게", "술·치킨": "가볍게",
    "치킨": "가볍게", "술집": "가볍게",
    "통신": "가정", "세탁": "가정", "안경": "가정",
    "오락": "레저", "스포츠": "레저",
    "서점": "실무", "스터디카페": "실무", "문구": "실무", "인쇄": "실무",
    "약국": "의료", "병원": "의료",
}


def matrix(origin, targets):
    payload = {"sources": [origin],
               "targets": [{"lat": t["lat"], "lon": t["lng"]} for t in targets],
               "costing": "pedestrian"}
    compact = json.dumps(payload, separators=(",", ":"))
    url = VALHALLA + "?json=" + urllib.parse.quote(compact, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "woorisai/1.0"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())["sources_to_targets"][0]


def run(write: bool):
    new = json.loads(NEW.read_text(encoding="utf-8"))
    old = json.loads(DST.read_text(encoding="utf-8"))
    old_by_id = {s["id"]: s for s in old}

    merged = []
    for r in new:
        o = old_by_id.get(r["id"])
        name = r["name"] + (f" {r['branch']}" if r.get("branch") else "")
        cat = GROUP_MERGE.get(r["category"], r["category"])   # 세부->통합 그룹
        s = {
            "id": r["id"], "name": name,
            "category": cat, "category_detail": r.get("category_detail", ""),
            "address": r.get("address", ""),
            "price_from": PRICE_HINT.get(r["category"], 8000),
            "capacity": CAPACITY_HINT.get(r["category"], 0),
            "description": (o or {}).get("description", ""),
            "hours": (o or {}).get("hours", ""),
            "lat": r["lat"], "lng": r["lng"],
            "owner": (o or {}).get("owner"),
            "verified": (o or {}).get("verified", False),
            "source": r.get("source", "소상공인시장진흥공단"),
        }
        if o and o.get("walk_campus"):        # 기존 도보 데이터 재사용
            s["walk_min"] = o.get("walk_min")
            s["walk_meters"] = o.get("walk_meters")
            s["walk_campus"] = o["walk_campus"]
            s["walk_source"] = o.get("walk_source", "valhalla")
        merged.append(s)

    # 수기 등록(회식럽 등 s*) 유지 + 음식 통합 반영
    names = {s["name"] for s in merged}
    for m in old:
        if m["id"].startswith("sb"):
            continue
        if m["name"] in names:
            continue
        m = dict(m)
        m["category"] = GROUP_MERGE.get(m.get("category"), m.get("category"))
        merged.append(m)

    # 새로 편입돼 도보 데이터 없는 가게만 라우팅
    todo = [s for s in merged if not s.get("walk_campus") and s.get("lat")]
    print(f"총 {len(merged)}곳 · 신규 라우팅 {len(todo)}곳")
    for campus, origin in CAMPUSES.items():
        print(f"[{campus}] 계산 중...")
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            try:
                cells = matrix(origin, chunk)
            except Exception as e:
                print(f"  배치 {i // BATCH + 1} 실패: {e}"); continue
            for s, cell in zip(chunk, cells):
                if cell.get("time") is not None:
                    s.setdefault("walk_campus", {})[campus] = {
                        "min": max(1, round(cell["time"] / 60)),
                        "meters": round(cell["distance"] * 1000)}
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")
            time.sleep(DELAY)

    # 기본 도보(walk_min)는 경희대 기준으로 채움
    for s in todo:
        khu = s.get("walk_campus", {}).get("경희대")
        s["walk_min"] = khu["min"] if khu else 10
        s["walk_meters"] = khu["meters"] if khu else None
        s["walk_source"] = "valhalla"

    print(f"\n=== 최종 업종 분포 ({len(merged)}곳) ===")
    for c, n in Counter(s["category"] for s in merged).most_common():
        print(f"  {c:6s} {n:4d}")

    if write:
        DST.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장 -> {DST}")
    else:
        print("\n--write 를 붙이면 저장합니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    run(ap.parse_args().write)
