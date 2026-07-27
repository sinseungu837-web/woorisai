"""
데모용 후기 주입 — 발표 시연 때 '학생 목소리' 화면을 보여주기 위한 것.

주의:
    여기 들어가는 후기는 전부 만들어낸 문장이다. 실제 학생이 쓴 말이 아니다.
    그래서 기본 데이터(data/reviews.json)에 넣어두지 않고, 필요할 때만
    직접 실행하도록 분리했다. 시연이 끝나면 --clear 로 지운다.

사용:
    python scripts/seed_demo_reviews.py            # 주입
    python scripts/seed_demo_reviews.py --clear    # 제거
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWS = ROOT / "data" / "reviews.json"
MARK = "__demo__"          # 이 표시가 붙은 것만 지운다. 실제 후기는 건드리지 않는다.

# 카페형 가게 한 곳에 3개월치 흐름을 심는다.
#   - 콘센트/자리: 계속 나오는 불편 -> [먼저 고칠 것]
#   - 두쫀쿠: 6월 중순부터 새로 뜬 요청 -> [들여놓을 것] + [지금 잡을 흐름]
#   - 라떼: 꾸준한 칭찬 -> [이미 잘하는 것]
DEMO = [
    ("2026-05-06", "콘센트 자리가 부족해서 불편했어요"),
    ("2026-05-11", "콘센트를 좀 늘려주세요"),
    ("2026-05-19", "자리가 좁아서 아쉬웠어요"),
    ("2026-05-28", "콘센트 때문에 다른 데 갔어요"),
    ("2026-06-14", "두쫀쿠 여기서도 팔았으면 좋겠어요"),
    ("2026-06-22", "두쫀쿠 언제 나와요?"),
    ("2026-07-02", "두쫀쿠를 기다리고 있어요"),
    ("2026-07-09", "두쫀쿠 생기면 매일 올게요"),
    ("2026-07-15", "두쫀쿠 추가해주시면 자주 올게요"),
    ("2026-07-18", "라떼 정말 맛있어요"),
    ("2026-07-20", "라떼가 최고예요 또 올게요"),
    ("2026-07-21", "자리 아직도 모자라요"),
]


def main():
    sys.path.insert(0, str(ROOT))
    from app import db

    reviews = json.loads(REVIEWS.read_text(encoding="utf-8"))
    kept = [r for r in reviews if not r.get(MARK)]

    if "--clear" in sys.argv:
        REVIEWS.write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        print(f"데모 후기 제거: {len(reviews)} -> {len(kept)}건")
        return

    store = db.get_stores()[0]
    kept += [{"store_id": store["id"], "text": t, "date": d, MARK: True}
             for d, t in DEMO]
    REVIEWS.write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"'{store['name']}'에 데모 후기 {len(DEMO)}건 주입 (총 {len(kept)}건)")
    print("시연이 끝나면: python scripts/seed_demo_reviews.py --clear")


if __name__ == "__main__":
    main()
