# -*- coding: utf-8 -*-
"""
챗봇 자동 채점 하네스 — eval/EVAL_METRICS.md 의 L1·L2 지표를 코드로 집계.

before/after 를 같은 잣대로 재기 위한 것. 주관 채점(L3) 없이 결정론적으로만 판정한다.

실행
  python eval/eval_chat.py --base https://<서버주소> --runs 3
  python eval/eval_chat.py --base http://127.0.0.1:8000
"""
import argparse
import json
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TESTSET = BASE_DIR / "chat_testset.jsonl"

# 계산 아티팩트 — "약 0분", 음수 분 등 무의미 문구
ARTIFACT_RE = re.compile(r"약\s*0\s*분|(?<!\d)-\d+\s*분|0분의\s*여유")
# 용도 미검출인데 업종을 단정하는 폴백 서술
FALLBACK_RE = re.compile(r"(카페|밥집|서점|술집)[를을]?\s*찾으시는군요")


def load_rows():
    return [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]


def post_chat(base: str, text: str, user_id: str, timeout: int = 60) -> dict:
    body = json.dumps({"message": text, "user_id": user_id, "campus": "경희대"}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode())


def run_once(base: str, rows: list, tag: str) -> dict:
    """입력셋 1회 순회. 맥락누수 항목은 prev_id 를 같은 세션에서 먼저 보낸다."""
    results = []
    for r in rows:
        uid = f"eval_{tag}_{r['id']}"
        try:
            # 순서 의존(맥락 누수) 항목: 이전 턴을 같은 user_id 로 먼저 보냄
            if r.get("prev_id"):
                prev = next(x for x in rows if x["id"] == r["prev_id"])
                post_chat(base, prev["text"], uid)
            resp = post_chat(base, r["text"], uid)
        except Exception as e:
            results.append({**r, "error": f"{type(e).__name__}: {e}", "answer": "", "stores": []})
            continue

        answer = resp.get("answer") or ""
        stores = resp.get("stores") or []
        cond = resp.get("condition") or {}
        results.append({**r, "answer": answer, "stores": stores, "condition": cond, "error": None})
    return results


def score(results: list) -> dict:
    ok = [r for r in results if not r["error"]]
    n = len(ok) or 1

    # --- L2 규칙 판정 ---
    # 1) 맥락 누수: must_not_contain 위반
    leak_items = [r for r in ok if r.get("edge") == "맥락누수"]
    leak_fail = [r for r in leak_items
                 if any(k in r["answer"] for k in r["must_not_contain"])]
    # 2) 범위밖/무의미 거절: stores 가 비어야 성공
    reject_items = [r for r in ok if r.get("edge") in ("범위밖", "무의미") and not r["stores_expected"]]
    reject_pass = [r for r in reject_items if len(r["stores"]) == 0]
    # 3) 폴백 확정서술: 용도 미검출인데 업종 단정
    fb_items = [r for r in ok if (r.get("condition") or {}).get("purpose") in (None, "")]
    fb_fail = [r for r in fb_items if FALLBACK_RE.search(r["answer"])]
    # 4) 계산 아티팩트
    art_fail = [r for r in ok if ARTIFACT_RE.search(r["answer"])]
    # 5) 빈 결과율 (추천이 나와야 하는데 0건)
    need = [r for r in ok if r["stores_expected"]]
    empty = [r for r in need if len(r["stores"]) == 0]
    # 6) 중복 노출: 추천 항목 간 가게집합 자카드 >= 0.8
    sets = [(r["id"], {s["id"] for s in r["stores"]}) for r in need if r["stores"]]
    dup = 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i][1], sets[j][1]
            if a and b and len(a & b) / len(a | b) >= 0.8:
                dup += 1
    pairs = max(1, len(sets) * (len(sets) - 1) // 2)

    # --- L1 슬롯(가능한 항목만) ---
    slot_tot = slot_hit = 0
    for r in ok:
        g = r.get("gold") or {}
        c = r.get("condition") or {}
        for k, v in g.items():
            slot_tot += 1
            if c.get(k) == v:
                slot_hit += 1

    def pct(a, b):
        return round(a / b * 100, 1) if b else 0.0

    # 엣지 통과 = 맥락누수 성공 + 거절 성공
    edge_total = len(leak_items) + len(reject_items)
    edge_pass = (len(leak_items) - len(leak_fail)) + len(reject_pass)

    return {
        "n": len(ok),
        "errors": len(results) - len(ok),
        "맥락누수율": pct(len(leak_fail), len(leak_items)),
        "범위밖·무의미_거절률": pct(len(reject_pass), len(reject_items)),
        "폴백_확정서술률": pct(len(fb_fail), len(fb_items)),
        "계산_아티팩트율": pct(len(art_fail), len(ok)),
        "빈결과율": pct(len(empty), len(need)),
        "중복노출률": pct(dup, pairs),
        "엣지_통과율": pct(edge_pass, edge_total),
        "슬롯_정확도": pct(slot_hit, slot_tot),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="서버 주소 (예: https://xxx.trycloudflare.com)")
    ap.add_argument("--runs", type=int, default=1, help="반복 횟수(중앙값 집계)")
    ap.add_argument("--dump", help="원응답 저장 경로(json)")
    a = ap.parse_args()

    rows = load_rows()
    all_scores, last = [], None
    for i in range(a.runs):
        print(f"[{i+1}/{a.runs}] 측정 중... ({len(rows)}개 입력)")
        res = run_once(a.base, rows, tag=f"r{i}{int(time.time())%10000}")
        last = res
        s = score(res)
        all_scores.append(s)
        print("   ", {k: v for k, v in s.items() if k not in ("n", "errors")})

    keys = [k for k in all_scores[0] if k not in ("n", "errors")]
    med = {k: round(statistics.median([s[k] for s in all_scores]), 1) for k in keys}

    print("\n" + "=" * 56)
    print(f"{'지표':<24}{'중앙값':>10}")
    print("-" * 56)
    for k in keys:
        print(f"{k:<24}{med[k]:>10}")
    print("=" * 56)
    print(f"오류 응답: {all_scores[-1]['errors']}건 / 입력 {all_scores[-1]['n']}개")

    if a.dump and last:
        Path(a.dump).write_text(json.dumps(last, ensure_ascii=False, indent=2), encoding="utf-8")
        print("원응답 저장 ->", a.dump)


if __name__ == "__main__":
    main()
