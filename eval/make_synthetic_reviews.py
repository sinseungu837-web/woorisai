"""
실험용 합성 후기 생성기 — 정답을 알고 만든다.

왜 합성 데이터인가:
    실제 후기는 8건뿐이라 '검출됐다/못했다'를 잴 수 없다. 그래서 어떤 키워드가
    어떤 흐름으로 들어있는지 미리 정해 두고(=정답) 후기를 찍어낸다. 그러면
    "심은 신호를 몇 개나 찾아냈나"를 숫자로 잴 수 있다.

공정성을 위해 지킨 것:
    1) 정답 키워드를 코드에 사전으로 넣지 않는다. 추출기는 이 키워드들을 모른다.
    2) 같은 키워드도 조사를 바꿔 넣는다("두쫀쿠가/두쫀쿠를/두쫀쿠")
       — 정규화가 실제로 동작해야만 집계된다.
    3) 정답 없는 잡음 후기를 40% 섞는다. 안 그러면 오탐률이 무의미해진다.
    4) seed 고정(42) — 누가 돌려도 같은 데이터가 나온다.

출력:
    eval/synthetic_reviews.json : [{store_id, text, date}]
    eval/synthetic_truth.json   : 심은 신호 목록(정답)
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
START = date(2026, 5, 1)
WEEKS = 12
HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 심을 신호 정의 — (가게, 키워드, 의도, 흐름, 앞구간 건수, 뒷구간 건수)
# 흐름: 신규(앞구간 0건) / 급상승(뒷구간이 1.5배 이상) / 지속(비슷)
# ---------------------------------------------------------------------------
SIGNALS = [
    # 가게 s003 — 스터디 카페형
    ("s003", "두쫀쿠",   "요청", "신규",   0, 7),
    ("s003", "콘센트",   "불만", "지속",   5, 5),
    ("s003", "라떼",     "칭찬", "지속",   4, 3),
    # 가게 s101 — 디저트 카페
    ("s101", "제로슈거", "요청", "신규",   0, 6),
    ("s101", "대기",     "불만", "급상승", 2, 6),
    # 가게 s102 — 백반집
    ("s102", "혼밥",     "요청", "지속",   4, 4),
    ("s102", "반찬",     "불만", "급상승", 2, 5),
    ("s102", "가성비",   "칭찬", "지속",   3, 4),
    # 가게 s103 — 분식
    ("s103", "마라",     "요청", "급상승", 2, 6),
    ("s103", "포장",     "불만", "지속",   4, 3),
    # 가게 s104 — 서점·스터디
    ("s104", "스터디룸", "요청", "신규",   0, 5),
    ("s104", "소음",     "불만", "지속",   4, 4),
    # 가게 s105 — 편의점
    ("s105", "냉동식품", "요청", "급상승", 2, 5),
    ("s105", "무인계산", "불만", "감소",   6, 2),
]

# 키워드를 끼워 넣을 문장 틀. {k} 자리에 조사까지 붙은 형태가 들어간다.
TEMPLATES = {
    "요청": ["{k} 여기서도 팔았으면 좋겠어요", "{k} 좀 들여놔 주세요",
             "{k} 언제 나와요?", "{k} 추가해주시면 자주 올게요",
             "{k} 있으면 좋겠는데 아쉬워요", "{k} 생기면 매일 올 것 같아요"],
    "불만": ["{k} 때문에 좀 불편했어요", "{k} 부분이 아쉬웠습니다",
             "{k} 이거 개선되면 좋겠어요", "{k} 문제로 오래 기다렸어요",
             "{k} 쪽이 좀 별로였어요"],
    "칭찬": ["{k} 정말 좋았어요", "{k} 덕분에 만족했습니다",
             "{k} 최고예요 또 올게요", "{k} 친절하게 챙겨주셔서 좋았어요"],
}

# 조사 변형 — 정규화가 동작해야만 하나로 합쳐진다.
JOSA_VARIANTS = ["", "", "가", "를", "는", "도", "랑", "이", "은", "을"]

# 정답이 없는 잡음 후기. 오탐률 측정용.
NOISE = [
    "그냥 무난했어요", "다음에 또 올게요", "생각보다 괜찮았습니다",
    "친구랑 같이 갔어요", "위치가 학교에서 가까워요", "분위기 나쁘지 않아요",
    "가끔 들르는 곳이에요", "특별한 건 없었어요", "적당했어요",
    "수업 끝나고 들렀습니다", "혼자 가기 편했어요", "재방문 의사 있어요",
    "직원분이 바빠 보였어요", "평범합니다", "무난하게 잘 먹었어요",
]

NOISE_RATIO = 0.4          # 전체 후기의 40%를 잡음으로


def _josa(term: str, rng: random.Random) -> str:
    """키워드에 조사를 무작위로 붙인다. 받침 유무는 따지지 않는다 —
    실제 학생 입력도 완벽하지 않고, 정규화가 그걸 견뎌야 하기 때문이다."""
    return term + rng.choice(JOSA_VARIANTS)


def _date_in(half: str, rng: random.Random) -> str:
    """앞구간(전반 6주) / 뒷구간(후반 6주) 중 하나에서 날짜를 뽑는다."""
    lo, hi = (0, WEEKS * 7 // 2) if half == "prev" else (WEEKS * 7 // 2, WEEKS * 7)
    return (START + timedelta(days=rng.randrange(lo, hi))).isoformat()


def build() -> tuple[list, list]:
    rng = random.Random(SEED)
    reviews, truth = [], []

    for store_id, term, intent, trend, n_prev, n_recent in SIGNALS:
        for half, n in (("prev", n_prev), ("recent", n_recent)):
            for _ in range(n):
                tpl = rng.choice(TEMPLATES[intent])
                reviews.append({
                    "store_id": store_id,
                    "text": tpl.format(k=_josa(term, rng)),
                    "date": _date_in(half, rng),
                })
        truth.append({"store_id": store_id, "term": term, "intent": intent,
                      "trend": trend, "prev": n_prev, "recent": n_recent})

    # 잡음 주입 — 신호 후기 수에 비례해서 넣는다.
    n_noise = int(len(reviews) * NOISE_RATIO / (1 - NOISE_RATIO))
    stores = sorted({s[0] for s in SIGNALS})
    for _ in range(n_noise):
        reviews.append({
            "store_id": rng.choice(stores),
            "text": rng.choice(NOISE),
            "date": _date_in(rng.choice(["prev", "recent"]), rng),
        })

    reviews.sort(key=lambda r: (r["date"], r["store_id"]))
    return reviews, truth


if __name__ == "__main__":
    reviews, truth = build()
    (HERE / "synthetic_reviews.json").write_text(
        json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "synthetic_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"후기 {len(reviews)}건 생성 "
          f"(신호 {len(reviews) - int(len(reviews) * NOISE_RATIO)}건 + "
          f"잡음 {int(len(reviews) * NOISE_RATIO)}건)")
    print(f"심은 신호 {len(truth)}개, 가게 {len({t['store_id'] for t in truth})}곳")
    print(f"기간 {reviews[0]['date']} ~ {reviews[-1]['date']}")
