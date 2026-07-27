"""
학생 목소리(Voice of Student) 집계 — 후기·요청을 키워드와 트렌드로 바꾼다.

설계 원칙 (프로젝트 철학 그대로):
    판단은 전부 이 파일(코드)이 한다. EXAONE은 결과를 문장으로 번역만 한다.
    그래서 이 모듈은 LLM을 호출하지 않는다. 같은 입력이면 항상 같은 출력이다.

왜 만들었나:
    기존 classify_review_category()는 후기를 5개 고정 버킷으로만 나눈다.
    "두쫀쿠 팔았으면 좋겠어요"가 10건 들어와도 사장님이 보는 건 '메뉴 10건'이다.
    무엇을 원하는지가 사라진다. 이 모듈은 그 '무엇'을 되살린다.

형태소 분석기(konlpy 등)를 쓰지 않는 이유:
    GPU 서버에 새 의존성을 넣지 않기 위해서다. 대신 '말뭉치 투표' 방식으로
    조사를 뗀다 — 자세한 원리는 normalize_tokens() 주석 참고.
"""
from __future__ import annotations

import math
import re
from datetime import date as _date
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# 1. 토큰화 & 조사 제거
# ---------------------------------------------------------------------------

# 격조사·보조사만 넣는다. 길이가 긴 것을 먼저 시도해야 "에서"를 "서"로 잘못 떼지 않는다.
#
# 종결어미("요", "라", "면" 등)를 여기 넣으면 안 된다:
#   "아쉬워요"의 '요'를 떼면 "아쉬워"가 남는데, 이건 명사 필터(VERB_ENDINGS)를
#   빠져나가 키워드로 올라온다. 조사 제거는 명사 뒤에 붙은 것만 대상으로 한다.
JOSA = sorted(
    ["이", "가", "을", "를", "은", "는", "의", "에", "도", "만", "과", "와", "랑",
     "로", "으로", "에서", "에게", "한테", "까지", "부터", "보다", "처럼", "마다",
     "조차", "밖에", "이나", "나", "라도", "든지", "이랑"],
    key=len, reverse=True)

# 후기에 흔하지만 정보가 없는 말. 키워드 후보에서 제외한다.
STOPWORDS = {
    "그리고", "그래서", "하지만", "근데", "진짜", "정말", "너무", "조금", "약간",
    "완전", "그냥", "다시", "역시", "생각", "느낌", "부분", "정도", "때문", "경우",
    "여기", "저기", "거기", "이번", "다음", "지난", "오늘", "어제", "내일", "요즘",
    "저는", "제가", "우리", "사람", "사람들", "학생", "학생들", "가게", "매장",
    "방문", "이용", "사용", "구매", "주문", "이곳", "그곳", "하나", "가지", "많이",
    "좋겠", "좋았", "같아", "같은", "있는", "없는", "합니", "습니", "했어", "해서",
    "있어", "없어", "이랑", "이런", "저런", "그런", "어떤", "무슨", "한번", "한번더",
    "때문", "문제", "부분", "이거", "그거", "저거", "오래", "여기서", "다음에",
    "생각보다", "친구", "직원", "위치", "분위기", "의사", "재방문", "수업",
    # 부사·시간어 — 자주 나오지만 사장님이 실행할 거리가 없는 말
    "매일", "가끔", "같이", "자주", "항상", "계속", "바로", "빨리", "천천히",
    "미리", "아주", "제일", "가장", "특별", "평범", "적당", "무난", "혼자",
    "학교", "쪽이", "이곳", "그곳", "곳이",
    "생기", "가기", "올게", "바빠", "직원분", "끝나고", "들르", "괜찮",
}

TOKEN_SPLIT = re.compile(r"[^가-힣A-Za-z0-9]+")

# 용언(동사·형용사) 활용 어미. 이걸로 끝나면 명사가 아니라 서술어 조각이다.
#
# 왜 필요한가:
#   빈도만 보면 "좋았어요", "아쉬웠습니다", "때문에" 같은 조각이 상위권을 채운다.
#   사장님께 "'좋겠어요'를 4번 요청했습니다"라고 말할 수는 없다.
#   사장님이 알아야 할 건 '무엇'이므로, 키워드는 명사로 한정한다.
VERB_ENDINGS = (
    # -다체 / -습니다체
    "니다", "습니", "입니", "합니", "됩니", "봅니", "았습", "었습", "겠습",
    # 연결어미
    "해서", "아서", "어서", "와서", "가서", "하고", "나고", "리고", "지고",
    "하는", "하지", "지만", "는데", "려고", "더라", "잖아", "같아", "싶어",
    # 가정('-면') — 단, '라면·냉면·짜장면' 같은 명사는 걸리지 않게
    # 활용형에만 나타나는 앞 음절까지 묶어서 본다.
    "으면", "시면", "되면", "하면", "기면", "가면", "오면", "보면", "지면", "려면",
    # 종결·보조 어간
    "겠어", "았어", "었어", "했어", "왔어", "갔어", "있어", "없어",
    "드려", "드립", "놔", "줘", "봐", "하게", "하니", "해도", "라서", "면서",
)

# 2음절 토큰이 이 글자로 끝나면, 남는 어간이 1음절뿐이라 명사일 수 없다.
# ("되는" -> '되', "드는" -> '드'). 반대로 조사로도 자주 쓰이는 '이/에/도/의'는
# 뺐다 — "종이", "온도", "각도" 같은 멀쩡한 명사가 같이 날아가기 때문이다.
SHORT_TAIL = ("는", "은", "가", "를", "을")


def tokenize(text: str) -> list[str]:
    """공백·문장부호로 자른 뒤, 길이 2 이상만 남긴다."""
    return [t for t in TOKEN_SPLIT.split(text or "") if len(t) >= 2]


def is_content_word(token: str) -> bool:
    """
    키워드 후보로 쓸 수 있는 명사인가.

    세 가지를 본다:
      1) '요'로 끝나면 서술어다 — 후기 말투는 대부분 해요체라, 이 한 줄이
         "아쉬워요/좋았어요/주세요/올게요"를 통째로 걸러낸다.
         ('필요', '수요' 같은 명사도 같이 걸리지만, 후기에서 사장님이 실행할
          키워드로 쓰일 일이 없어 손해보다 이득이 크다.)
      2) 활용 어미로 끝나면 서술어다.
      3) 조사를 뗀 형태가 불용어면 불용어다 — "문제로/부분이/때문에"처럼
         정규화가 실패해 조사가 붙은 채 남은 경우를 여기서 잡는다.
    """
    if len(token) < 2 or token in STOPWORDS:
        return False
    if token.endswith("요") or token.endswith(VERB_ENDINGS):
        return False
    if len(token) == 2 and token.endswith(SHORT_TAIL):
        return False
    return not any(c in STOPWORDS for c in _candidates(token))


def _candidates(token: str) -> list[str]:
    """이 토큰이 될 수 있는 원형 후보들. 자기 자신 + 조사를 뗀 형태."""
    out = [token]
    for j in JOSA:
        if token.endswith(j) and len(token) - len(j) >= 2:
            out.append(token[: -len(j)])
    return out


def normalize_tokens(texts: list[str]) -> list[list[str]]:
    """
    조사를 떼되, 규칙으로 무조건 떼지 않고 '말뭉치 투표'로 결정한다.

    왜 이렇게 하나:
        규칙만 쓰면 "와이파이"의 끝 '이'를 조사로 오인해 "와이파"가 된다.
        그래서 먼저 말뭉치 전체에서 '맨몸으로 등장한 형태'를 세어 둔다.
        "커피가/커피는/커피" 가 섞여 있으면 맨몸 "커피"가 표로 이기고,
        "와이파이"는 "와이파"가 맨몸으로 등장한 적이 없으니 그대로 남는다.

    반환: 후기별 정규화 토큰 리스트 (입력과 같은 순서·길이)
    """
    raw = [tokenize(t) for t in texts]

    surface = Counter()
    for toks in raw:
        for t in toks:
            surface[t] += 1

    # 1단계: 어간 후보마다 '어떤 조사를 달고 나타났는지' 모은다.
    #        "자리가", "자리를", "자리에" -> 어간 '자리'가 조사 3종을 달았다.
    attached: dict[str, set[str]] = defaultdict(set)
    for token in surface:
        for j in JOSA:
            if token.endswith(j) and len(token) - len(j) >= 2:
                attached[token[: -len(j)]].add(j)

    def attested(stem: str) -> bool:
        """이 어간을 실제 단어로 볼 근거가 있나."""
        if stem in surface:                        # 맨몸으로 등장한 적이 있다
            return True
        return len(attached.get(stem, ())) >= 2    # 서로 다른 조사 2종 이상을 달았다

    # 2단계: 조사를 떼되 '단어로 확인된 어간'으로만 뗀다.
    #        확인 안 되면 원형을 건드리지 않는다 — "와이파이"를 "와이파"로
    #        망가뜨리는 쪽보다 안 떼고 두는 쪽이 안전하기 때문이다.
    #        후보가 여럿이면 가장 긴 어간(= 가장 덜 깎은 형태)을 택한다.
    resolved: dict[str, str] = {}
    for token in surface:
        stems = [c for c in _candidates(token)[1:] if attested(c)]
        resolved[token] = max(stems, key=len) if stems else token

    return [[resolved[t] for t in toks] for toks in raw]


# ---------------------------------------------------------------------------
# 2. 의도 분류 — 요청인가, 불만인가, 칭찬인가
# ---------------------------------------------------------------------------
# 순서가 중요하다. "있었으면 좋겠어요"는 '좋'이 들어가지만 칭찬이 아니라 요청이다.
# 그래서 요청 → 불만 → 칭찬 순으로 검사한다.

REQUEST_PAT = ["있었으면", "있으면 좋", "생겼으면", "팔았으면", "했으면", "주세요",
               "주시면", "주시길", "원해", "원합니", "바라", "추가", "들여놔",
               "가져다", "부탁", "만들어", "생기면", "나왔으면", "받았으면",
               "됐으면", "되면 좋", "필요해", "필요할", "찾는데", "언제 나와",
               "안 파", "안파", "없나요", "있나요", "파나요", "가능할까", "가능한가"]
NEGATIVE_PAT = ["아쉬", "불편", "당황", "별로", "실망", "짜증", "너무 오래", "오래 기다",
                "안 돼", "안돼", "안 되", "안되", "없어서", "모자라", "부족", "비싸",
                "시끄", "좁아", "좁고", "더러", "불친절", "헷갈", "못 찾", "복잡",
                "끊겨", "끊기", "느려", "느리", "안 잡", "막혀", "밀려", "지저분",
                "춥", "덥", "기다렸", "대기가", "품절", "다 떨어"]
POSITIVE_PAT = ["좋았", "좋아요", "맛있", "예뻤", "예뻐", "친절", "만족", "최고",
                "감사", "편했", "편해", "훌륭", "깔끔", "쾌적", "빠르", "저렴", "추천"]


def classify_intent(text: str) -> str:
    """단건 후기의 의도. 요청 > 불만 > 칭찬 > 기타 순으로 판정."""
    t = text or ""
    if any(p in t for p in REQUEST_PAT):
        return "요청"
    if any(p in t for p in NEGATIVE_PAT):
        return "불만"
    if any(p in t for p in POSITIVE_PAT):
        return "칭찬"
    return "기타"


# ---------------------------------------------------------------------------
# 3. 키워드 점수 — 흔한 말 말고 '이 가게 이야기'를 뽑는다
# ---------------------------------------------------------------------------

def keyword_scores(store_docs: list[list[str]],
                   corpus_df: Counter, n_docs_corpus: int) -> list[dict]:
    """
    TF-IDF 방식. 이 가게 후기에서 자주 나오되, 전체 상권 후기에서는
    드문 단어일수록 높은 점수를 준다.

    왜 단순 빈도를 안 쓰나:
        빈도만 세면 "커피", "카페" 같은 업종 일반명사가 항상 1위가 된다.
        사장님한테 "손님들이 커피 얘기를 많이 합니다"는 아무 정보가 아니다.
        IDF를 곱하면 이 가게에서만 튀는 "두쫀쿠"가 위로 올라온다.
    """
    tf = Counter()
    doc_hits = defaultdict(set)                      # 단어 -> 등장한 후기 index
    for i, toks in enumerate(store_docs):
        for t in set(toks):                          # 한 후기 안 중복은 1회로
            doc_hits[t].add(i)
        for t in toks:
            if is_content_word(t):                   # 명사만 키워드 후보로
                tf[t] += 1

    out = []
    for term, count in tf.items():
        df = corpus_df.get(term, 1)
        idf = math.log((n_docs_corpus + 1) / (df + 1)) + 1.0
        out.append({
            "term": term,
            "count": count,
            "doc_count": len(doc_hits[term]),
            "score": round(count * idf, 3),
        })
    out.sort(key=lambda d: (-d["score"], -d["count"], d["term"]))
    return out


# ---------------------------------------------------------------------------
# 4. 트렌드 — 최근에 뜬 말인가, 원래 있던 말인가
# ---------------------------------------------------------------------------

def _parse(s: str):
    """'YYYY-MM-DD' -> date. 형식이 어긋나면 None (날짜 없는 후기도 견뎌야 한다)."""
    try:
        return _date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def split_by_time(reviews: list[dict], ratio: float = 0.5) -> tuple[list, list]:
    """
    후기를 앞(과거)/뒤(최근) 두 구간으로 나눈다.

    '개수 절반'이 아니라 '기간 절반'으로 자른다:
        개수로 자르면 후기가 몰린 시기 쪽으로 경계가 끌려간다. 예를 들어 최근에
        후기가 폭증하면 경계가 최근으로 밀려서, 정작 최근에 새로 뜬 키워드가
        앞구간에도 걸쳐 '신규'가 아니라 '지속'으로 잘못 찍힌다.
        흐름을 보는 게 목적이므로 기준은 시간이어야 한다.

    날짜가 하나도 없으면 입력 순서를 시간순으로 보고 개수로 자른다(차선책).
    """
    dated = [(reviews[i].get("date"), i) for i in range(len(reviews))]
    days = sorted(d for d, _ in dated if d)

    if not days or days[0] == days[-1]:
        idx = sorted(range(len(reviews)),
                     key=lambda i: (reviews[i].get("date") or "", i))
        cut = int(len(idx) * ratio)
        return idx[:cut], idx[cut:]

    # 달력상의 한가운데 날짜. '관측치의 중앙값'이 아니라 '기간의 중앙'이어야
    # 한다 — 후기가 몰린 시기로 경계가 끌려가는 걸 막는 게 목적이기 때문이다.
    d0, d1 = _parse(days[0]), _parse(days[-1])
    mid = (d0 + (d1 - d0) * ratio).isoformat() if d0 and d1 else days[len(days) // 2]
    prev = [i for d, i in dated if d and d < mid]
    recent = [i for d, i in dated if not d or d >= mid]
    return prev, recent


MIN_SPAN_DAYS = 14      # 흐름을 말하려면 최소 2주치는 쌓여야 한다
MIN_REVIEWS_TREND = 8   # 그리고 최소 8건은 있어야 한다


def _has_enough_span(reviews: list[dict]) -> bool:
    """흐름(신규/급상승/감소)을 판정할 만큼 기간과 건수가 쌓였나."""
    if len(reviews) < MIN_REVIEWS_TREND:
        return False
    days = sorted(d for d in (r.get("date") for r in reviews) if d)
    if len(days) < 2:
        return False
    d0, d1 = _parse(days[0]), _parse(days[-1])
    return bool(d0 and d1 and (d1 - d0).days >= MIN_SPAN_DAYS)


def trend_label(prev: int, recent: int) -> str:
    """
    두 구간의 등장 횟수로 흐름을 판정한다.
    임계값은 후기 수가 적은 초기 상권을 감안해 보수적으로 잡았다.
    """
    # prev를 0이 아니라 1까지 '신규'로 본다.
    # 후기가 적은 상권에서는 구간 경계에 한 건이 걸치는 일이 흔한데,
    # 그 한 건 때문에 '신규'가 '급상승'으로 뒤집히면 사장님이 받는 메시지가
    # 달라진다("처음 나온 요구" vs "원래 있던 요구"). 한 건은 잡음으로 본다.
    if prev <= 1 and recent >= 3:
        return "신규"
    if prev == 0:
        return "관찰중"
    growth = (recent - prev) / prev
    if growth >= 0.5 and recent >= 3:
        return "급상승"
    if growth <= -0.5:
        return "감소"
    return "지속"


# ---------------------------------------------------------------------------
# 5. 최종 조립 — 사장님 리포트에 넣을 구조화 결과
# ---------------------------------------------------------------------------

TOP_N = 5
MIN_SIGNAL = 2          # 이 횟수 미만은 신호로 안 본다 (1건짜리 잡음 차단)
MIN_DOCS = 2            # 서로 다른 후기 2건 이상에서 나와야 신호로 본다


def _is_signal(kw: dict) -> bool:
    """
    한 명이 여러 번 쓴 말과, 여러 명이 각각 말한 것을 구분한다.
    후자만 신호다 — 사장님이 돈을 쓸 근거는 '여러 사람이 같은 말을 했다'는 사실이다.
    """
    return kw["count"] >= MIN_SIGNAL and kw["doc_count"] >= MIN_DOCS


def build_voice_report(store_reviews: list[dict],
                       all_reviews: list[dict] | None = None) -> dict:
    """
    한 가게의 후기 묶음 -> 사장님 리포트용 구조화 결과.

    all_reviews: IDF 계산용 전체 상권 후기. 없으면 store_reviews로 대체
                 (이 경우 IDF가 무의미해지므로 빈도순과 비슷해진다).
    """
    if not store_reviews:
        return {"available": False, "n": 0, "keywords": [], "cards": [],
                "by_intent": {}, "period": None}

    corpus = all_reviews if all_reviews else store_reviews
    corpus_docs = normalize_tokens([r["text"] for r in corpus])
    corpus_df = Counter()
    for toks in corpus_docs:
        for t in set(toks):
            corpus_df[t] += 1

    texts = [r["text"] for r in store_reviews]
    docs = normalize_tokens(texts)
    intents = [classify_intent(t) for t in texts]

    # --- 키워드 랭킹 ---
    ranked = keyword_scores(docs, corpus_df, len(corpus_docs))

    # --- 트렌드: 각 키워드가 과거/최근 구간에 몇 번 나왔나 ---
    #
    # 흐름을 말하려면 '시간이 지나야' 한다. 후기가 하루치뿐이거나 몇 건 안 되면
    # 앞/뒤로 갈라도 그건 흐름이 아니라 잡음이다. 그런데도 '감소'라고 써 버리면
    # 사장님이 없는 하락을 믿고 잘못 움직인다. 그래서 근거가 모자랄 때는
    # 판정을 하지 않고 '관찰중'으로 둔다.
    trendable = _has_enough_span(store_reviews)
    prev_idx, recent_idx = split_by_time(store_reviews)
    prev_set, recent_set = set(prev_idx), set(recent_idx)
    for kw in ranked:
        p = sum(1 for i in prev_set if kw["term"] in docs[i])
        r = sum(1 for i in recent_set if kw["term"] in docs[i])
        kw["prev"], kw["recent"] = p, r
        kw["trend"] = trend_label(p, r) if trendable else "관찰중"

    # --- 의도별 키워드: '원하는 것'과 '고칠 것'을 분리 ---
    by_intent: dict[str, list[dict]] = {}
    for want in ("요청", "불만", "칭찬"):
        sub = [i for i, x in enumerate(intents) if x == want]
        if not sub:
            by_intent[want] = []
            continue
        sub_ranked = keyword_scores([docs[i] for i in sub],
                                    corpus_df, len(corpus_docs))
        for kw in sub_ranked:
            kw["examples"] = [texts[i] for i in sub if kw["term"] in docs[i]][:2]
        by_intent[want] = [k for k in sub_ranked if _is_signal(k)][:TOP_N]

    cards = build_vision_cards(by_intent, ranked, len(store_reviews))
    dates = [r.get("date") for r in store_reviews if r.get("date")]

    return {
        "available": True,
        "n": len(store_reviews),
        "period": (min(dates), max(dates)) if dates else None,
        "intent_counts": dict(Counter(intents)),
        "keywords": [k for k in ranked if _is_signal(k)][:TOP_N],
        "by_intent": by_intent,
        "cards": cards,
    }


# 카드 유형별 우선순위. 숫자가 낮을수록 리포트 위쪽에 온다.
# 불만을 요청보다 위에 두는 이유: 이미 온 손님을 잃는 쪽이 손해가 더 크다.
CARD_ORDER = {"개선": 0, "도입": 1, "흐름": 2, "강점": 3}


def build_vision_cards(by_intent: dict, ranked: list[dict], n: int) -> list[dict]:
    """
    구조화 결과 -> '비전 카드' 목록. 여기가 실제로 판단하는 곳이다.

    카드 하나 = {유형, 키워드, 근거 후기 원문, 코드가 만든 제안 문장}
    근거(evidence)를 반드시 붙인다. 이게 있어야 나중에 EXAONE이 쓴 문장이
    실제 후기에 근거한 것인지 기계적으로 검사할 수 있다.
    """
    cards = []

    for kw in by_intent.get("불만", [])[:2]:
        cards.append({
            "type": "개선", "term": kw["term"], "count": kw["count"],
            "evidence": kw.get("examples", []),
            "action": f"'{kw['term']}' 관련 불편이 {kw['count']}건 반복됐습니다. "
                      f"가장 먼저 손볼 지점입니다.",
        })

    for kw in by_intent.get("요청", [])[:2]:
        cards.append({
            "type": "도입", "term": kw["term"], "count": kw["count"],
            "evidence": kw.get("examples", []),
            "action": f"학생들이 '{kw['term']}'를 {kw['count']}번 먼저 요청했습니다. "
                      f"이미 수요가 확인된 항목이라 도입 위험이 낮습니다.",
        })

    rising = [k for k in ranked
              if k["trend"] in ("신규", "급상승") and _is_signal(k)][:2]
    for kw in rising:
        cards.append({
            "type": "흐름", "term": kw["term"], "count": kw["count"],
            "evidence": [],
            "action": f"'{kw['term']}' 언급이 최근 {kw['prev']}건에서 {kw['recent']}건으로 "
                      f"늘었습니다. 지금 대응하면 흐름을 선점할 수 있습니다.",
        })

    for kw in by_intent.get("칭찬", [])[:1]:
        cards.append({
            "type": "강점", "term": kw["term"], "count": kw["count"],
            "evidence": kw.get("examples", []),
            "action": f"'{kw['term']}'는 이미 강점입니다. 홍보 문구에 그대로 쓰세요.",
        })

    cards.sort(key=lambda c: (CARD_ORDER[c["type"]], -c["count"]))
    return cards


def evidence_terms(voice: dict) -> set[str]:
    """
    리포트 문장이 근거로 삼을 수 있는 단어 집합.
    EXAONE 출력이 이 밖의 고유명사를 지어냈는지 검사할 때 쓴다.
    """
    return {k["term"] for k in voice.get("keywords", [])} | {
        k["term"] for lst in voice.get("by_intent", {}).values() for k in lst}


def prompt_block(voice: dict) -> str:
    """EXAONE에 넘길 텍스트 블록. 코드가 정한 사실만 담는다."""
    if not voice.get("available"):
        return ""
    lines = [f"학생 후기 {voice['n']}건 집계 결과:"]
    for c in voice["cards"]:
        lines.append(f"- [{c['type']}] {c['action']}")
        for ev in c["evidence"][:1]:
            lines.append(f"    (실제 후기: \"{ev}\")")
    return "\n".join(lines)
