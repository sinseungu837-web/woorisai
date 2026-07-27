# -*- coding: utf-8 -*-
"""
실시간 도보 경로 — 사용자의 현재 위치 기준

  GPS는 별도 API를 발급받을 필요가 없다.
  브라우저에 내장된 Geolocation API(navigator.geolocation)가 위경도를 준다.
  (HTTPS 또는 localhost 에서만 동작 — 브라우저 보안 정책)

  받은 좌표로 Valhalla(FOSSGIS 공개 서버)에 도보 경로를 물어본다.
  API 키 불필요, 무료.

호출을 아끼는 방법
  1) 직선거리로 먼저 후보를 좁힌다 (계산 비용 0)
  2) 좁혀진 후보만 Valhalla matrix 로 한 번에 계산
  3) 같은 좌표 재요청은 캐시에서 응답
"""
import json
import math
import time
import urllib.parse
import urllib.request

VALHALLA = "https://valhalla1.openstreetmap.de/sources_to_targets"
MAX_TARGETS = 40          # 한 번에 물어볼 최대 지점
CACHE_TTL = 300           # 초 — 같은 위치 재조회 시 캐시 사용

_cache: dict = {}


def haversine(lat1, lng1, lat2, lng2) -> float:
    """직선거리(m) — 후보를 좁히는 용도. API 호출 없음."""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _matrix(lat: float, lng: float, targets: list) -> list | None:
    payload = {
        "sources": [{"lat": lat, "lon": lng}],
        "targets": [{"lat": t["lat"], "lon": t["lng"]} for t in targets],
        "costing": "pedestrian",
    }
    compact = json.dumps(payload, separators=(",", ":"))
    url = VALHALLA + "?json=" + urllib.parse.quote(compact, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "woorisai/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as res:
            return json.loads(res.read().decode())["sources_to_targets"][0]
    except Exception:
        return None          # 실패 시 직선거리 추정으로 폴백


def walk_from(lat: float, lng: float, stores: list, limit: int = 20) -> list:
    """
    현재 위치에서 각 점포까지의 실제 도보 거리·시간.

    반환: 가까운 순으로 정렬된 점포 목록
          walk_min / walk_meters / walk_source 가 채워진다
    """
    # 캐시 키에 '어떤 점포 묶음을 넘겼는지'까지 넣어야 한다.
    # 좌표·limit 만으로 키를 잡으면, 업종을 바꿔 걸러 넣어도 첫 호출 결과가
    # 그대로 되돌아온다(모든 업종이 같은 가게를 보여주던 원인).
    key = (round(lat, 4), round(lng, 4), limit,
           hash(tuple(s.get("id") for s in stores)))
    hit = _cache.get(key)
    if hit and time.time() - hit["at"] < CACHE_TTL:
        return hit["data"]

    # ① 직선거리로 후보 좁히기 (API 호출 없음)
    scored = []
    for s in stores:
        if s.get("lat") is None or s.get("lng") is None:
            continue
        d = haversine(lat, lng, s["lat"], s["lng"])
        scored.append((d, s))
    scored.sort(key=lambda x: x[0])
    candidates = [s for _, s in scored[:min(MAX_TARGETS, max(limit, 20))]]

    # ② 후보만 실제 경로 계산
    result = _matrix(lat, lng, candidates)

    out = []
    for i, store in enumerate(candidates):
        item = dict(store)
        cell = result[i] if result and i < len(result) else None
        if cell and cell.get("time") is not None:
            item["walk_min"] = max(1, round(cell["time"] / 60))
            item["walk_meters"] = round(cell["distance"] * 1000)
            item["walk_source"] = "valhalla-realtime"
        else:
            # 폴백: 직선거리 × 1.3, 도보 4km/h
            straight = haversine(lat, lng, store["lat"], store["lng"])
            item["walk_meters"] = round(straight * 1.3)
            item["walk_min"] = max(1, round(straight * 1.3 / 67))
            item["walk_source"] = "estimate"
        out.append(item)

    out.sort(key=lambda s: s["walk_min"])
    out = out[:limit]
    _cache[key] = {"at": time.time(), "data": out}
    return out


def route_detail(lat: float, lng: float, store: dict) -> dict:
    """한 점포까지의 상세 — 거리·시간·경로 안내"""
    payload = {
        "locations": [{"lat": lat, "lon": lng},
                      {"lat": store["lat"], "lon": store["lng"]}],
        "costing": "pedestrian",
        "directions_options": {"language": "ko-KR", "units": "kilometers"},
    }
    compact = json.dumps(payload, separators=(",", ":"))
    url = ("https://valhalla1.openstreetmap.de/route?json="
           + urllib.parse.quote(compact, safe=""))
    req = urllib.request.Request(url, headers={"User-Agent": "woorisai/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as res:
            trip = json.loads(res.read().decode())["trip"]
    except Exception:
        d = haversine(lat, lng, store["lat"], store["lng"]) * 1.3
        return {"available": False, "walk_min": max(1, round(d / 67)),
                "walk_meters": round(d), "steps": []}

    summary = trip["summary"]
    steps = []
    for leg in trip.get("legs", []):
        for m in leg.get("maneuvers", []):
            steps.append({
                "text": m.get("instruction", ""),
                "meters": round(m.get("length", 0) * 1000),
                "seconds": round(m.get("time", 0)),
            })
    return {
        "available": True,
        "walk_min": max(1, round(summary["time"] / 60)),
        "walk_meters": round(summary["length"] * 1000),
        "steps": steps,
    }
