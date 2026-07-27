# -*- coding: utf-8 -*-
"""
EXAONE 조건 추출(parse_query) 정량 평가 — 발표용 개선 곡선을 뽑는다.

측정하는 것
  Slot Precision / Recall / F1   : (key, value) 쌍 일치
  Exact Match                    : 3개 조건 전부 일치한 문항 비율
  JSON 유효율                    : 파싱 가능 비율
  Latency p50 / p95              : 응답 지연

비교하는 것 (ablation 사다리)
  B0 규칙       : 정규식 (LLM 없음)          → LLM이 필요한가?
  B1 날것       : EXAONE, 최소 지시           → 모델만 쓰면?
  B2 스키마     : + JSON 형식 명시            → 형식 지정 효과?
  B3 few-shot   : + 정답 예시 (빈 예시 포함)   → 우리 튜닝의 기여분

실행 (GPU 서버 노트북에서)
  import sys; sys.path.insert(0, "/home/data/woorisai")
  from eval.eval_nlu import run_all
  run_all()
"""
import json
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
TESTSET = BASE / "testset.jsonl"
SCORED_SLOTS = ("minutes", "purpose", "people")   # 채점 대상 (자유서술 없음)


# ---------------------------------------------------------------- 데이터
def load_testset() -> list:
    rows = []
    with open(TESTSET, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ------------------------------------------------------------- 채점 로직
def slot_pairs(slots: dict) -> set:
    """조건 dict -> (key, value) 집합. 빈 값(null/기본값)은 제외."""
    pairs = set()
    for k in SCORED_SLOTS:
        v = slots.get(k)
        if v is None:
            continue
        if k == "people" and v == 1:       # 기본값 1은 '명시 안 함'으로 간주
            continue
        pairs.add((k, str(v)))
    return pairs


def score(rows: list, predict_fn) -> dict:
    """predict_fn(text) -> {"slots": {...}, "valid": bool} 를 받아 지표 계산."""
    tp = fp = fn = 0
    exact = 0
    valid = 0
    latencies = []

    for r in rows:
        t0 = time.perf_counter()
        out = predict_fn(r["text"])
        latencies.append((time.perf_counter() - t0) * 1000)

        valid += 1 if out.get("valid", True) else 0
        gold = slot_pairs(r["slots"])
        pred = slot_pairs(out.get("slots", {}))

        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
        if gold == pred:
            exact += 1

    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    latencies.sort()
    n = len(rows)

    return {
        "precision": round(prec * 100, 1),
        "recall": round(rec * 100, 1),
        "f1": round(f1 * 100, 1),
        "exact_match": round(exact / n * 100, 1),
        "json_valid": round(valid / n * 100, 1),
        "latency_p50": round(latencies[n // 2], 1),
        "latency_p95": round(latencies[min(n - 1, int(n * 0.95))], 1),
        "n": n, "tp": tp, "fp": fp, "fn": fn,
    }


# ------------------------------------------- B0: 규칙 기반 (LLM 없음)
def rule_predict(text: str) -> dict:
    """정규식·키워드로만 추출 — app.ai._stub_parse 와 동일한 규칙."""
    from app.ai import Exaone
    return {"slots": Exaone._stub_parse(text), "valid": True}


# ---------------------------------- B1~B3: EXAONE (프롬프트만 교체)
_PROMPTS = {
    "B1": {  # 날것 — 최소 지시
        "system": "학생 문장을 이해해서 답해라.",
        "user": "다음 문장에서 남은시간, 용무, 인원을 알려줘.\n문장: {text}",
    },
    "B2": {  # + JSON 스키마 명시
        "system": "너는 회기동 상권 안내 시스템의 파서다. 반드시 JSON만 출력한다.",
        "user": ("다음 문장에서 조건을 뽑아 JSON으로만 답해라.\n"
                 '형식: {{"minutes": 남은시간(분, 모르면 null), '
                 '"purpose": "식사"|"카페"|"선물"|"인쇄"|"스터디"|"서점"|"단체"|null, '
                 '"people": 인원수(기본 1)}}\n\n문장: {text}'),
    },
    "B3": {  # + few-shot 예시 (빈 예시 포함 = 환각 억제)
        "system": "너는 회기동 상권 안내 시스템의 파서다. 반드시 JSON만 출력한다.",
        "user": ("다음 문장에서 조건을 뽑아 JSON으로만 답해라. "
                 "명시적으로 말한 것만 넣고, 애매하면 비운다(지어내지 마라).\n"
                 '형식: {{"minutes": 남은시간(분, 모르면 null), '
                 '"purpose": "식사"|"카페"|"선물"|"인쇄"|"스터디"|"서점"|"단체"|null, '
                 '"people": 인원수(기본 1)}}\n\n'
                 "예시\n"
                 '문장: "50분 비는데 밥 먹을 곳" -> {{"minutes": 50, "purpose": "식사", "people": 1}}\n'
                 '문장: "8명이서 저녁 예약" -> {{"minutes": null, "purpose": "단체", "people": 8}}\n'
                 '문장: "그냥 심심해" -> {{"minutes": null, "purpose": null, "people": 1}}\n'
                 '문장: "안녕" -> {{"minutes": null, "purpose": null, "people": 1}}\n\n'
                 "문장: {text}"),
    },
}


def make_exaone_predict(cond: str):
    """B1/B2/B3 프롬프트로 EXAONE 을 호출하는 predict 함수를 만든다."""
    from app.ai import exaone
    p = _PROMPTS[cond]

    def predict(text: str) -> dict:
        raw = exaone._chat(p["system"], p["user"].format(text=text), 128)
        parsed = exaone._json_from(raw)
        return {"slots": parsed or {}, "valid": parsed is not None}

    return predict


# ------------------------------------------------------------- 실행
def run_all() -> dict:
    rows = load_testset()
    print(f"테스트셋: {len(rows)}문항\n")

    results = {}
    print("[B0] 규칙 기반 측정 중...")
    results["B0 규칙"] = score(rows, rule_predict)

    for cond, label in [("B1", "B1 날것"), ("B2", "B2 스키마"), ("B3", "B3 few-shot")]:
        print(f"[{cond}] EXAONE 측정 중...")
        results[label] = score(rows, make_exaone_predict(cond))

    _print_table(results)
    return results


def _print_table(results: dict):
    print("\n" + "=" * 70)
    print(f"{'조건':<14}{'F1':>7}{'정밀도':>8}{'재현율':>8}{'ExactM':>8}{'JSON':>7}{'p50ms':>8}")
    print("-" * 70)
    for label, r in results.items():
        print(f"{label:<14}{r['f1']:>7}{r['precision']:>8}{r['recall']:>8}"
              f"{r['exact_match']:>8}{r['json_valid']:>7}{r['latency_p50']:>8}")
    print("=" * 70)

    b0 = list(results.values())[0]["f1"]
    b3 = list(results.values())[-1]["f1"]
    print(f"\n개선 요약: 규칙 {b0} → few-shot {b3}  (Slot F1 {b3 - b0:+.1f}점)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(BASE.parent))
    run_all()
