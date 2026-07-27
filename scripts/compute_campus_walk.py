# -*- coding: utf-8 -*-
"""
3개 학교 정문 기준으로 711개 가게까지의 실제 도보시간을 각각 계산해 stores.json 에 저장.

  경희대 학생 → 한국외대 쪽 가게 = 멀다 → 자동으로 걸러지게 하는 근거.
  학교별로 walk_campus["경희대"|"한국외대"|"한예종"] = {min, meters} 를 각 가게에 넣는다.

좌표는 예전에 Nominatim 지오코딩으로 확인한 각 학교 서울/석관 캠퍼스 대표점(정문 부근).
Valhalla(무료, 키 불필요) 도보 matrix 사용.

실행
  python scripts/compute_campus_walk.py --write
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

VALHALLA = "https://valhalla1.openstreetmap.de/sources_to_targets"
BATCH, DELAY = 40, 1.2

# 지오코딩으로 확인한 학교 대표 좌표 (정문 부근)
CAMPUSES = {
    "경희대":   {"lat": 37.5967213, "lon": 127.0519867},   # 서울캠퍼스
    "한국외대": {"lat": 37.5970815, "lon": 127.0587413},   # 서울캠퍼스
    "한예종":   {"lat": 37.6049302, "lon": 127.0574461},   # 석관동캠퍼스
}


def matrix(origin: dict, targets: list) -> list:
    payload = {"sources": [origin],
               "targets": [{"lat": t["lat"], "lon": t["lng"]} for t in targets],
               "costing": "pedestrian"}
    compact = json.dumps(payload, separators=(",", ":"))
    url = VALHALLA + "?json=" + urllib.parse.quote(compact, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "woorisai/1.0"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())["sources_to_targets"][0]


def run(write: bool):
    base = Path(__file__).resolve().parent.parent
    path = base / "data" / "stores.json"
    stores = json.loads(path.read_text(encoding="utf-8"))
    targets = [s for s in stores if s.get("lat") and s.get("lng")]
    print(f"대상 {len(targets)}곳 · 학교 {len(CAMPUSES)}개")

    for name, origin in CAMPUSES.items():
        print(f"\n[{name}] 도보시간 계산 중...")
        ok = 0
        for i in range(0, len(targets), BATCH):
            chunk = targets[i:i + BATCH]
            try:
                cells = matrix(origin, chunk)
            except Exception as e:
                print(f"  배치 {i // BATCH + 1} 실패: {e}")
                continue
            for s, cell in zip(chunk, cells):
                if cell.get("time") is not None:
                    s.setdefault("walk_campus", {})[name] = {
                        "min": max(1, round(cell["time"] / 60)),
                        "meters": round(cell["distance"] * 1000),
                    }
                    ok += 1
            print(f"  {min(i + BATCH, len(targets))}/{len(targets)}")
            time.sleep(DELAY)
        print(f"  {name}: {ok}곳 완료")

    # 요약
    print("\n=== 가까운 순 상위 3곳 (학교별) ===")
    for name in CAMPUSES:
        ranked = sorted(
            [s for s in stores if s.get("walk_campus", {}).get(name)],
            key=lambda s: s["walk_campus"][name]["min"])[:3]
        near = ", ".join(f"{s['name']}({s['walk_campus'][name]['min']}분)" for s in ranked)
        print(f"  {name}: {near}")

    if write:
        path.write_text(json.dumps(stores, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장 완료 -> {path}")
    else:
        print("\n--write 를 붙이면 저장합니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    run(ap.parse_args().write)
