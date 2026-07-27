"""
학생 목소리 집계 검증 실험.

세 방식을 같은 데이터에 돌려 비교한다:
    A. 기존 5버킷    - classify_review_category (결제수단/대기시간/메뉴/좌석/기타)
    B. 단순 빈도     - 조사 정규화 없이 토큰 빈도 상위 5개
    C. voice.py     - 조사 정규화 + TF-IDF + 의도/트렌드 판정

B를 넣은 이유:
    C가 좋게 나왔을 때 그게 '키워드를 뽑았기 때문'인지 '정규화와 IDF 덕분'인지
    갈라내기 위해서다. B가 없으면 개선의 원인을 특정할 수 없다.

측정 지표:
    1) 신호 검출률 Recall@5 - 심은 키워드가 상위 5개에 잡힌 비율
    2) 오탐률              - 상위 5개 중 심지 않은 항목의 비율
    3) 의도 정확도          - 요청/불만/칭찬 분류가 정답과 일치하는 비율
    4) 트렌드 정확도        - 신규/급상승/지속/감소 판정 정확도
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app import voice                                    # noqa: E402
from app.logic import classify_review_category           # noqa: E402

TOP_K = 5


def load():
    reviews = json.loads((HERE / "synthetic_reviews.json").read_text(encoding="utf-8"))
    truth = json.loads((HERE / "synthetic_truth.json").read_text(encoding="utf-8"))
    by_store = defaultdict(list)
    for r in reviews:
        by_store[r["store_id"]].append(r)
    truth_by_store = defaultdict(list)
    for t in truth:
        truth_by_store[t["store_id"]].append(t)
    return reviews, by_store, truth_by_store


# --- A. 기존 5버킷 -----------------------------------------------------------
def arm_bucket(store_reviews):
    """기존 방식이 사장님께 내놓는 것 = 버킷 이름과 건수뿐."""
    c = Counter(classify_review_category(r["text"]) for r in store_reviews)
    return [k for k, _ in c.most_common(TOP_K)]


# --- B. 단순 빈도 ------------------------------------------------------------
def arm_freq(store_reviews):
    """조사 정규화 없이 그대로 센다."""
    c = Counter()
    for r in store_reviews:
        for t in voice.tokenize(r["text"]):
            if t not in voice.STOPWORDS:
                c[t] += 1
    return [k for k, _ in c.most_common(TOP_K)]


# --- C. voice.py -------------------------------------------------------------
def arm_voice(store_reviews, all_reviews):
    rep = voice.build_voice_report(store_reviews, all_reviews)
    return [k["term"] for k in rep["keywords"]], rep


def main():
    reviews, by_store, truth_by_store = load()
    stores = sorted(by_store)

    results = {"A": {"hit": 0, "fp": 0, "out": 0},
               "B": {"hit": 0, "fp": 0, "out": 0},
               "C": {"hit": 0, "fp": 0, "out": 0},
               "cards": {"hit": 0, "fp": 0, "out": 0}}
    n_signals = 0
    intent_ok = intent_tot = 0
    trend_ok = trend_tot = 0
    trend_confusion = Counter()
    detail = []

    for sid in stores:
        srv = by_store[sid]
        gold = {t["term"] for t in truth_by_store[sid]}
        n_signals += len(gold)

        top_a = arm_bucket(srv)
        top_b = arm_freq(srv)
        top_c, rep = arm_voice(srv, reviews)

        for arm, top in (("A", top_a), ("B", top_b), ("C", top_c)):
            results[arm]["hit"] += len(gold & set(top))
            # 정밀도는 상위 |정답개수| 까지만 본다.
            # 가게당 정답이 2~3개인데 상위 5개를 억지로 채우게 하면,
            # 완벽한 시스템도 오탐률 40~60%가 나와 비교가 무의미해진다.
            head = top[:len(gold)]
            results[arm]["fp"] += len([t for t in head if t not in gold])
            results[arm]["out"] += len(head)

        # 사장님이 실제로 보는 것은 상위 5개가 아니라 '비전 카드'다.
        for c in rep["cards"]:
            results["cards"]["out"] += 1
            results["cards"]["fp"] += int(c["term"] not in gold)

        # 의도·트렌드는 C만 산출한다 (A/B는 아예 내놓지 못하는 값)
        placed = {}
        for want, lst in rep["by_intent"].items():
            for kw in lst:
                placed[kw["term"]] = want
        trends = {k["term"]: k["trend"] for k in rep["keywords"]}

        for t in truth_by_store[sid]:
            if t["term"] in placed:
                intent_tot += 1
                intent_ok += int(placed[t["term"]] == t["intent"])
            if t["term"] in trends:
                trend_tot += 1
                got = trends[t["term"]]
                trend_ok += int(got == t["trend"])
                trend_confusion[(t["trend"], got)] += 1

        detail.append({"store": sid, "n": len(srv), "gold": sorted(gold),
                       "A": top_a, "B": top_b, "C": top_c,
                       "cards": rep["cards"]})

    print("=" * 74)
    print(f"학생 목소리 집계 검증 — 후기 {len(reviews)}건 / 가게 {len(stores)}곳 / "
          f"심은 신호 {n_signals}개")
    print("=" * 74)
    names = {"A": "기존 5버킷", "B": "단순 빈도", "C": "voice.py(정규화+IDF)"}
    print(f"\n{'방식':<24}{'검출률(Recall@5)':>18}{'오탐률(상위=정답수)':>16}")
    print("-" * 74)
    for arm in "ABC":
        r = results[arm]
        rec = r["hit"] / n_signals * 100
        fp = r["fp"] / r["out"] * 100 if r["out"] else 0
        print(f"{names[arm]:<24}{rec:>15.1f}%{fp:>13.1f}%")

    cd = results["cards"]
    print(f"\n사장님께 나가는 비전 카드: {cd['out']}장 중 정답 키워드 "
          f"{cd['out'] - cd['fp']}장 = 정확도 "
          f"{(cd['out'] - cd['fp']) / max(cd['out'],1) * 100:.1f}%")

    print(f"\n의도 분류 정확도 (요청/불만/칭찬): "
          f"{intent_ok}/{intent_tot} = {intent_ok / max(intent_tot,1) * 100:.1f}%")
    print(f"트렌드 판정 정확도 (신규/급상승/지속/감소): "
          f"{trend_ok}/{trend_tot} = {trend_ok / max(trend_tot,1) * 100:.1f}%")
    if trend_confusion:
        print("  틀린 건:", ", ".join(
            f"{a}->{b} {n}건" for (a, b), n in trend_confusion.items() if a != b) or "없음")

    print("\n" + "=" * 74)
    print("가게별 상위 5개 비교")
    print("=" * 74)
    for d in detail:
        print(f"\n[{d['store']}] 후기 {d['n']}건 / 정답: {', '.join(d['gold'])}")
        print(f"  A 기존 : {', '.join(d['A'])}")
        print(f"  B 빈도 : {', '.join(d['B'])}")
        print(f"  C 신규 : {', '.join(d['C'])}")

    print("\n" + "=" * 74)
    print("생성된 비전 카드 예시 (s003)")
    print("=" * 74)
    for c in next(d for d in detail if d["store"] == "s003")["cards"]:
        print(f"  [{c['type']}] {c['action']}")
        for ev in c["evidence"][:1]:
            print(f"        근거: \"{ev}\"")

    (HERE / "voice_eval_result.json").write_text(json.dumps({
        "n_reviews": len(reviews), "n_signals": n_signals,
        "arms": {a: {"recall": results[a]["hit"] / n_signals * 100,
                     "fp_rate": results[a]["fp"] / max(results[a]["out"], 1) * 100}
                 for a in "ABC"},
        "intent_acc": intent_ok / max(intent_tot, 1) * 100,
        "trend_acc": trend_ok / max(trend_tot, 1) * 100,
        "detail": detail,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n결과 저장: eval/voice_eval_result.json")


if __name__ == "__main__":
    main()
