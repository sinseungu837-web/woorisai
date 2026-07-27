"""
'검증된 성능' vs '플랫폼이 지금 실제로 내는 성능' 의 격차를 숫자로 잰다.

왜 필요한가:
    ablation.py 는 실험 조건을 직접 만들어 돌린다. 그 수치가 좋아도
    플랫폼이 그 로직을 쓰고 있지 않으면 사용자는 그 성능을 못 받는다.
    그래서 여기서는 시뮬레이션이 아니라 **배포된 추천 경로를 그대로 호출**해
    실제 노출 분포를 잰다.

실행
  python eval/deployed_gap.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import main                                            # noqa: E402
from app import logic                                  # noqa: E402

BAR = "=" * 74

# 학생이 실제로 던지는 요청. 회기동 상권 구성상 식사·카페 요청이 많다.
# (ablation.py 의 REQUESTS 와 같은 비율 — 두 실험을 비교할 수 있어야 한다)
REQUEST_MIX = (
    [("식사", "90분 비는데 밥 먹을 데")] * 10 +
    [("카페", "90분 비는데 카페")] * 8 +
    [("인쇄", "90분 비는데 프린트 어디서 해")] * 3 +
    [("스터디", "90분 비는데 공부할 데")] * 3 +
    [("사진", "90분 비는데 사진 찍을 데")] * 2 +
    [("술", "90분 비는데 술 한잔")] * 2 +
    [("선물", "90분 비는데 선물 살 데")] * 1 +
    [("생활", "90분 비는데 약국")] * 1
)
N_ROUNDS = 5          # 요청 150건 — HHI 는 이 정도면 안정된다
OPEN_TEXT = "90분 비는데 뭐 할까?"


def hhi(c: Counter) -> float:
    tot = sum(c.values())
    return sum((v / tot * 100) ** 2 for v in c.values()) if tot else 0.0


def food_share(c: Counter) -> float:
    tot = sum(c.values())
    return (c["식사"] + c["가볍게"]) / tot * 100 if tot else 0.0


def measure(texts, user_prefix: str) -> Counter:
    """배포된 recommend_reply 를 그대로 호출해 노출된 업종을 센다."""
    seen = Counter()
    for i, text in enumerate(texts):
        r = main.recommend_reply(text, f"{user_prefix}{i}", "경희대", None, None)
        for s in r.get("stores") or []:
            seen[s["category"]] += 1
    return seen


def main_run():
    texts = [t for _ in range(N_ROUNDS) for _, t in REQUEST_MIX]

    print(BAR)
    print(f"플랫폼 실측 — 배포된 recommend_reply 를 {len(texts):,}회 호출")
    print(BAR)

    # ① 용도를 명시한 일반 추천 (분산 점수·회전이 아직 안 붙은 경로)
    normal = measure(texts, "gapN")

    # ② 열린 추천 ("뭐 할까") — 분산 점수 + 회전이 붙어 있는 경로
    #    같은 사용자로 반복 호출해야 회전이 돌아간다.
    open_seen = Counter()
    for i in range(len(texts)):
        r = main.recommend_reply(OPEN_TEXT, "gapOpen", "경희대", None, None)
        for s in r.get("stores") or []:
            open_seen[s["category"]] += 1

    rows = [
        ("일반 추천 (용도 명시)", normal),
        ("열린 추천 ('뭐 할까')", open_seen),
    ]
    print(f"\n  {'경로':<26}{'HHI':>8}{'업종수':>8}{'요식업':>10}{'노출':>9}")
    print("-" * 74)
    out = {}
    for label, c in rows:
        print(f"  {label:<26}{hhi(c):>8.0f}{len(c):>8}{food_share(c):>9.1f}%"
              f"{sum(c.values()):>9,}")
        out[label] = {"hhi": round(hhi(c)), "cats": len(c),
                      "food": round(food_share(c), 1), "n": sum(c.values())}

    print("\n  일반 추천 노출 분포:")
    tot = sum(normal.values())
    for cat, v in normal.most_common():
        print(f"    {cat:<8}{v:>7,}  {v / tot * 100:>5.1f}%")

    # ------------------------------------------------------------------ 격차
    ABL = json.loads((HERE / "ablation_result.json").read_text(encoding="utf-8"))
    verified = ABL["chaining"]["체이닝+분산+회전"]["hhi"]
    baseline = ABL["chaining"]["단일"]["hhi"]
    deployed = hhi(normal)

    print("\n" + BAR)
    print("검증된 성능 vs 플랫폼 실측 — 격차")
    print(BAR)
    print(f"  {'항목':<34}{'HHI':>9}{'단일 대비':>12}")
    print("-" * 74)
    print(f"  {'단일 추천 (아무것도 안 한 경우)':<34}{baseline:>9,}{'(기준)':>12}")
    print(f"  {'플랫폼 일반 추천 (현재)':<34}{deployed:>9,.0f}"
          f"{(deployed - baseline) / baseline * 100:>11.1f}%")
    print(f"  {'실험에서 검증된 최선':<34}{verified:>9,}"
          f"{(verified - baseline) / baseline * 100:>11.1f}%")
    print(f"\n  미실현 격차: HHI {deployed - verified:>,.0f} "
          f"({(deployed - verified) / max(deployed, 1) * 100:.1f}% 더 낮출 여지)")

    # ------------------------------------------------------------ 예측 격차
    cal = ABL["calendar"]
    print(f"\n  {'유동인구 예측 (사장님 화면)':<34}{'MAPE':>9}")
    print("-" * 74)
    print(f"  {'플랫폼 현재 (보정 미적용)':<34}{cal['off']:>8.2f}%")
    print(f"  {'실험에서 검증된 성능 (보정 적용)':<34}{cal['on']:>8.2f}%")
    print(f"\n  미실현 격차: {cal['off'] - cal['on']:.2f}%p "
          f"({(cal['off'] - cal['on']) / cal['off'] * 100:.1f}% 개선 여지)")

    out["gap"] = {
        "hhi_deployed": round(deployed), "hhi_verified": verified,
        "hhi_baseline": baseline, "hhi_gap": round(deployed - verified),
        "mape_deployed": cal["off"], "mape_verified": cal["on"],
        "mape_gap": round(cal["off"] - cal["on"], 2),
    }
    (HERE / "deployed_gap_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n결과 저장: eval/deployed_gap_result.json")


if __name__ == "__main__":
    main_run()
