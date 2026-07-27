# -*- coding: utf-8 -*-
"""
실제 도보 거리·소요시간 계산 — Valhalla (FOSSGIS 공개 서버)

직선거리 추정을 실제 보행자 경로 기반 값으로 교체한다.
API 키가 필요 없고 무료다. 공개 서버이므로 batch + delay 로 예의 있게 호출한다.

  검증 결과 (경희대 정문 -> 학교식당)
    OSRM 데모 foot     : 576m / 2.6분 = 13.4km/h  <- 자동차 속도, 사용 불가
    Valhalla pedestrian: 294m / 3.4분 =  5.2km/h  <- 실제 보행 속도

거리 계산은 상점 등록 시 1회만 하면 되므로, 학생이 아무리 많이 물어봐도
이 API를 다시 부르지 않는다. (계산 결과를 stores.json 에 캐싱)

실행
  python scripts/compute_walk_times.py            # 미리보기
  python scripts/compute_walk_times.py --write    # stores.json 갱신
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

VALHALLA = "https://valhalla1.openstreetmap.de/sources_to_targets"
ORIGIN = {"lat": 37.5967, "lon": 127.0517}      # 경희대 정문 부근
BATCH = 40                                       # 공개 서버 배려
DELAY = 1.2                                      # 초


def matrix(targets: list) -> list:
    payload = {
        "sources": [ORIGIN],
        "targets": [{"lat": t["lat"], "lon": t["lng"]} for t in targets],
        "costing": "pedestrian",
    }
    # 공백이 '+'로 인코딩되면 Valhalla가 JSON 파싱에 실패한다 -> 공백 자체를 제거
    compact = json.dumps(payload, separators=(",", ":"))
    url = VALHALLA + "?json=" + urllib.parse.quote(compact, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "woorisai/1.0 (hackathon)"})
    with urllib.request.urlopen(req, timeout=60) as res:
        data = json.loads(res.read().decode())
    return data["sources_to_targets"][0]


def run(write: bool):
    base = Path(__file__).resolve().parent.parent
    path = base / "data" / "stores.json"
    stores = json.loads(path.read_text(encoding="utf-8"))

    targets = [s for s in stores if s.get("lat") and s.get("lng")]
    skipped = len(stores) - len(targets)
    print(f"대상 {len(targets)}곳 (좌표 없어 건너뜀 {skipped}곳)")

    updated, failed = 0, 0
    for i in range(0, len(targets), BATCH):
        chunk = targets[i:i + BATCH]
        try:
            result = matrix(chunk)
        except Exception as e:
            print(f"  배치 {i // BATCH + 1} 실패: {e}")
            failed += len(chunk)
            continue

        for store, cell in zip(chunk, result):
            if cell.get("time") is None or cell.get("distance") is None:
                failed += 1
                continue
            store["walk_min"] = max(1, round(cell["time"] / 60))
            store["walk_meters"] = round(cell["distance"] * 1000)
            store["walk_source"] = "valhalla-pedestrian"
            updated += 1

        print(f"  배치 {i // BATCH + 1}/{(len(targets) - 1) // BATCH + 1} 완료 ({updated}곳)")
        time.sleep(DELAY)

    print(f"\n갱신 {updated}곳 · 실패 {failed}곳")

    done = [s for s in stores if s.get("walk_source")]
    done.sort(key=lambda s: s["walk_min"])
    print("\n가까운 순 (실제 도보 경로 기준)")
    for s in done[:12]:
        print(f"  도보{s['walk_min']:2d}분 {s['walk_meters']:4d}m  {s['category']:6s} {s['name']}")

    if done:
        avg = sum(s["walk_min"] for s in done) / len(done)
        print(f"\n평균 도보 {avg:.1f}분 · 5분 이내 {sum(1 for s in done if s['walk_min'] <= 5)}곳")

    if write:
        path.write_text(json.dumps(stores, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장 완료 -> {path}")
    else:
        print("\n--write 를 붙이면 stores.json 에 저장합니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    run(ap.parse_args().write)
