# -*- coding: utf-8 -*-
"""
우리사이 — 회기동 대학상권 매칭 플랫폼

실행:  uvicorn main:app --reload
접속:  http://127.0.0.1:8000
"""
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db, logic, routing, voice
from app.ai import exaone, chronos, bge

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

app = FastAPI(title="우리사이", description="회기동 대학상권 매칭 플랫폼")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def no_cache_api(request, call_next):
    """/api/* 는 항상 새로 받는다.
    시간표·공강처럼 매번 달라지는 값을 브라우저가 캐시하면
    표를 고쳐도 화면이 옛날 값에 멈춰 있게 된다."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

# ---------------------------------------------------------------- 데모 고정값
#
# 발표·시연 때 "지금 몇 시냐"와 "어디 있냐"에 따라 화면이 매번 달라지면
# 같은 장면을 다시 보여줄 수 없다. 그래서 시각과 위치를 고정한다.
#
#   DEMO_HOUR = None  이면 실제 시각·실제 GPS 를 쓴다 (평상시)
#   숫자를 넣으면 그 시각으로 고정되고, 위치는 아래 좌표로 고정된다
#
# 요일도 고정한다. 서버 시계가 내 PC 와 하루 어긋나면(시간대 차이)
# 화면에서는 금요일을 고치는데 서버는 목요일을 읽어 숫자가 안 변하는 것처럼 보인다.
#   DEMO_DAY = None  이면 서버의 실제 요일
DEMO_HOUR: int | None = 13                      # 오후 1시
DEMO_DAY: str | None = "금"                     # "월"~"금" / None = 실제 요일
DEMO_MINUTE = 0
DEMO_CAMPUS = "경희대"
DEMO_LAT, DEMO_LNG = 37.5967213, 127.0519867    # 경희대 서울캠퍼스 정문


def now() -> datetime:
    """플랫폼이 '지금'으로 삼는 시각. 데모 모드면 고정 시각을 준다."""
    real = datetime.now()
    if DEMO_HOUR is None:
        return real
    fixed = real.replace(hour=DEMO_HOUR, minute=DEMO_MINUTE, second=0, microsecond=0)
    if DEMO_DAY in WEEKDAY_KR:
        # 이번 주 안에서 원하는 요일로 옮긴다 (날짜만 이동, 시각은 그대로)
        fixed += timedelta(days=WEEKDAY_KR.index(DEMO_DAY) - fixed.weekday())
    return fixed


def demo_position(lat, lng):
    """위치를 안 준(또는 데모 모드) 요청에 고정 좌표를 채워준다."""
    if DEMO_HOUR is not None:
        return DEMO_LAT, DEMO_LNG
    return lat, lng

# 챗봇 다중 턴 세션 — 메모리에만 있음, 서버 재시작하면 초기화된다
BOOKING_SESSIONS: dict = {}      # user_id -> {"step": ..., "people": ...}
REVIEW_SESSIONS: dict = {}       # user_id -> {"step": ..., "store_id": ...}
SURVEY_SESSIONS: set = set()     # 설문 답변을 기다리는 user_id 목록
SURVEY_QUESTION = "회기에 새로 생긴 가게, 알고 계세요?"
GROUP_CATEGORIES = ("한식", "중식", "일식", "양식", "술집", "분식", "치킨")


CAMPUSES = ("경희대", "한국외대")


def infer_campus(text: str) -> str | None:
    """전공/소개 자연어에서 학교를 추론한다.
    회기동 생활권 2개 대학만 구분 — 규칙(코드)이 판단, 애매하면 None."""
    t = (text or "").lower().replace(" ", "")
    if any(k in t for k in ("한국외대", "외대", "외국어대", "hufs")):
        return "한국외대"
    if any(k in t for k in ("경희대", "경희", "khu")):
        return "경희대"
    return None


# ------------------------------------------------------------ 공통 헬퍼
def apply_user_position(stores: list, lat: float | None, lng: float | None) -> list:
    """
    현재 위치가 주어지면 도보시간을 그 위치 기준으로 다시 계산한다.
    캠퍼스 정문 기준값은 GPS를 안 준 사용자를 위한 기본값일 뿐이라,
    실제로 어디 있는지 알면 그 자리에서 갈 수 있는지로 판단해야 한다.
    """
    if lat is None or lng is None:
        return stores
    out = []
    for s in stores:
        wm = logic.walk_min_from(lat, lng, s)
        if wm is None:
            continue                     # 좌표 없는 가게는 거리 판단 불가 -> 제외
        s = {**s, "walk_min": wm,
             "walk_meters": round(logic.haversine_m(lat, lng, s["lat"], s["lng"]) * logic.DETOUR),
             "walk_source": "현재 위치 기준(추정)"}
        out.append(s)
    return out


def enrich(store: dict, when: datetime | None = None, campus: str | None = None) -> dict:
    """점포 정보에 혼잡도 예측을 붙인다 (Chronos 캐시 조회 + 보정계수 적용).
    campus 를 주면 도보시간을 그 학교 기준으로 바꾼다 (경희대↔외대 거리 차이 반영)."""
    when = when or now()
    raw = chronos.get_congestion(store["id"], when.weekday(), when.hour)
    corr = logic.correction_factor(when.date(), db.get_calendar())
    score = logic.apply_correction(raw, corr["factor"])

    out = {
        **store,
        "congestion": score,
        "congestion_label": chronos.to_label(score),
        "correction": corr["factor"],
        "dwell_min": logic.dwell_for(store),
        "navermap": naver_url(store),
    }
    # 학교 기준 도보시간으로 덮어쓰기 (있을 때만)
    cw = store.get("walk_campus", {}).get(campus) if campus else None
    if cw:
        out["walk_min"] = cw["min"]
        out["walk_meters"] = cw["meters"]
        out["campus_base"] = campus
    return out


def naver_url(store: dict) -> str | None:
    """네이버지도 앱 URL Scheme — API가 아니라 링크라서 무료·키 불필요"""
    if store.get("lat") is None or store.get("lng") is None:
        return None
    return (
        f"nmap://route/walk?dlat={store['lat']}&dlng={store['lng']}"
        f"&dname={store['name']}&appname=woorisai"
    )


# --------------------------------------------------------------- 페이지
@app.get("/")
def page_index():
    return FileResponse(STATIC / "index.html")


@app.get("/{page}.html")
def page_any(page: str):
    target = STATIC / f"{page}.html"
    if target.exists():
        return FileResponse(target)
    return JSONResponse({"error": "not found"}, status_code=404)


# ----------------------------------------------------------- 점포 API
@app.get("/api/stores")
def api_stores(category: str | None = None):
    stores = db.get_stores()
    if category:
        stores = [s for s in stores if s["category"] == category]
    return [enrich(s) for s in stores]


@app.get("/api/stores/{store_id}")
def api_store(store_id: str):
    s = db.get_store(store_id)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    return enrich(s)


# ----------------------------------------------------------- 챗봇 API
@app.post("/api/chat")
def api_chat(payload: dict = Body(...)):
    """
    통합 챗봇 — 목업 4·5·17·18페이지를 한 창에서 처리한다.
      · 진행 중인 다중 턴 세션이 있으면 그 흐름을 이어간다 (session state)
      · 퀵리플라이가 보내는 mode 로 새 흐름을 시작할 수 있다
      · 그 외엔 기본 흐름(맥락 매칭 추천, 4페이지)으로 처리한다
    """
    text = payload.get("message", "")
    user_id = payload.get("user_id", "me")
    mode = payload.get("mode")
    campus = payload.get("campus") if payload.get("campus") in CAMPUSES else None
    if campus is None and DEMO_HOUR is not None:
        campus = DEMO_CAMPUS
    # 현재 위치(선택) — 주면 캠퍼스 대신 이 좌표 기준으로 도보시간을 계산한다
    try:
        lat = float(payload["lat"]) if payload.get("lat") is not None else None
        lng = float(payload["lng"]) if payload.get("lng") is not None else None
    except (TypeError, ValueError):
        lat = lng = None

    # ① 버튼으로 명시한 의도(mode)는 최우선. 진행 중이던 다른 세션을 끊고 새로 시작한다.
    #    (예: 예약 문의 도중 '이달의 설문' 버튼을 누르면 설문으로 넘어가야 한다)
    if mode in ("booking_start", "review_start", "survey_start"):
        SURVEY_SESSIONS.discard(user_id)
        BOOKING_SESSIONS.pop(user_id, None)
        REVIEW_SESSIONS.pop(user_id, None)
        if mode == "booking_start":
            return start_booking(user_id)
        if mode == "review_start":
            return start_review(user_id)
        return start_survey(user_id)

    # ② 타이핑 입력이 명백히 새 의도면 진행 중 세션을 끊는다 (맥락 누수 방지).
    if looks_like_new_intent(text):
        SURVEY_SESSIONS.discard(user_id)
        BOOKING_SESSIONS.pop(user_id, None)
        REVIEW_SESSIONS.pop(user_id, None)

    # ③ 진행 중 세션이 있으면 그 흐름의 답변으로 처리한다.
    if user_id in SURVEY_SESSIONS:
        return handle_survey_answer(user_id, text)
    if user_id in BOOKING_SESSIONS:
        return handle_booking_followup(user_id, text)
    if user_id in REVIEW_SESSIONS:
        return handle_review_followup(user_id, text)

    people = looks_like_booking(text)
    if people:
        return start_booking(user_id, people=people)

    lat, lng = demo_position(lat, lng)
    return recommend_reply(text, user_id, campus, lat, lng)


# 학교별 도보 상한(분) — 넘으면 "멀어서 실현 불가"로 보고 제외.
CAMPUS_WALK_LIMIT = {"경희대": 12, "한국외대": 15}

# 진행 중 세션을 끊어야 하는 '새 의도' 신호 (규칙 기반, AI 아님)
NEW_INTENT_HINTS = ("배고", "먹을", "밥", "카페", "커피", "공부", "책", "선물",
                    "프린트", "인쇄", "약국", "술", "심심", "추천", "놀", "사고 싶")


def looks_like_new_intent(text: str) -> bool:
    """
    예약/후기/설문 흐름 도중에 들어온 말이 '그 흐름의 답변'이 아니라
    완전히 새로운 요청인지 판별한다. 맥락 누수(P1-A)를 막는 탈출구.
      - 숫자·날짜·시간만 있는 말은 이어지는 답변으로 본다 ("25", "금요일 7시")
      - 추천 의도 키워드가 있으면 새 의도로 본다 ("배고파")
    """
    t = (text or "").strip()
    if not t:
        return False
    if re.fullmatch(r"[\d\s시분명일월화수목금토요:/~\.\-]+", t):
        return False
    return any(k in t for k in NEW_INTENT_HINTS)


# 용도별 '근거 단어' — 모델이 용도를 지어내도 원문에 근거가 없으면 되묻는다.
# (EXAONE이 빈 입력에 '급한일', "1시간 비어"에 '술'을 만들어낸 사례를 막기 위함)
PURPOSE_EVIDENCE = {
    "식사": ["밥", "먹", "점심", "저녁", "배고", "맛집", "식사", "한식", "중식", "일식", "양식", "분식"],
    "카페": ["카페", "커피", "음료", "디저트", "빵"],
    "술": ["술", "맥주", "치킨", "안주", "한잔", "호프", "포차"],
    "스터디": ["공부", "과제", "스터디", "독서실", "작업", "시험"],
    "선물": ["선물", "생일", "꽃", "기념"],
    "인쇄": ["프린트", "인쇄", "복사", "출력"],
    "서점": ["책", "서점", "도서"],
    "단체": ["회식", "총회", "모임", "단체", "엠티", "예약", "명"],
    "약국": ["약국", "약 사", "상비약", "두통약", "감기약", "소화제", "밴드"],
    "병원": ["병원", "의원", "치과", "진료", "아파", "몸살", "다쳤", "삐었"],
    "급한일": ["휴대폰", "충전", "급하", "편의점", "약 "],
    "생활": ["세탁", "안경", "화장품", "머리", "미용"],
    "레저": ["놀", "오락", "노래방", "당구", "피시", "게임", "운동", "심심"],
    "사진": ["사진", "필름", "현상", "인화", "네컷", "증명"],
    "의류": ["옷", "의류", "바지", "티셔츠", "쇼핑"],
}


def purpose_supported(text: str, purpose: str) -> bool:
    """모델이 뽑은 용도가 원문에 근거가 있는지 확인 (환각 차단)."""
    kws = PURPOSE_EVIDENCE.get(purpose)
    if not kws:
        return True          # 모르는 용도는 통과 — 과도한 차단 방지
    return any(k in (text or "") for k in kws)


def infer_purpose_from_text(text: str) -> str | None:
    """
    원문 근거만으로 용도를 직접 추론한다 (모델 오분류 교정용).
    예: EXAONE이 "필름 현상"을 '인쇄'로 보내면 근거검증에서 걸러지는데,
        그냥 버리면 되묻기가 되므로 여기서 '사진'으로 바로잡는다.
    """
    for purpose, kws in PURPOSE_EVIDENCE.items():
        if any(k in (text or "") for k in kws):
            return purpose
    return None


# 용도는 안 밝혔지만 '추천을 원한다'는 건 분명한 말들.
# 이걸 되묻기로 처리하면 대화가 막힌다 — 사용자는 이미 요청을 한 것이다.
OPEN_REQUEST_PAT = [
    "뭐 할", "뭐할", "뭐 하지", "뭐하지", "뭐 하나", "머 하지", "머할",
    "뭐 해", "뭐해", "머해", "뭐 하면", "뭐하면", "뭐 없", "뭐없",
    "추천", "심심", "할 거 없", "할거 없", "할 게 없", "할게 없",
    "어디 갈", "어디갈", "갈 데", "갈데", "뭐 있", "뭐있", "볼 거", "놀 거",
    "시간 남", "시간남", "시간 비", "할 만한", "할만한",
]

# 잡담. 추천 요청이 아니므로 후보를 만들지 않지만, 매번 같은 말로 막지도 않는다.
CHITCHAT_PAT = ["ㅋㅋ", "ㅎㅎ", "ㅇㅇ", "ㄱㄱ", "야", "안녕", "하이", "헬로",
                "고마", "감사", "미안", "잘가", "바이", "그래", "응", "네네"]


def looks_open_request(text: str) -> bool:
    """'뭐 할까' 처럼 용도는 없어도 추천을 원한 게 분명한가."""
    return any(p in (text or "") for p in OPEN_REQUEST_PAT)


def is_chitchat(text: str) -> bool:
    """추천 요청이 아닌 짧은 말인가. 길면 잡담으로 보지 않는다."""
    t = (text or "").strip()
    if not t or len(t) > 12:
        return False
    return any(p in t for p in CHITCHAT_PAT) or not any(c.isalnum() for c in t)


# 잡담 응답 후보. 매번 같은 문장이 나오면 대화가 아니라 벽처럼 느껴진다.
CHITCHAT_LINES = [
    "네, 듣고 있어요. 공강에 갈 만한 데 찾아드릴까요?",
    "지금 몇 분 비세요? 그 시간에 맞는 곳을 골라드릴게요.",
    "회기동에서 뭐 할지 고민이시면 편하게 말씀해주세요.",
    "밥, 카페, 인쇄, 사진 — 필요한 걸 말씀해주시면 찾아드려요.",
    "심심하시면 '뭐 할까'라고만 하셔도 골라드릴게요.",
]


def chitchat_reply(text: str, cond: dict | None = None) -> dict:
    """
    같은 문구 반복을 피한다. 무작위 대신 입력 문자열로 고르므로,
    같은 말엔 같은 답이 나오고(재현 가능) 다른 말엔 다른 답이 나온다.
    """
    # 단순히 ord 를 더하면 한글에서 잘 충돌한다("야"/"안녕"/"ㅋㅋㅋㅋ"가 같은 답).
    # 자리마다 다른 가중치를 줘서 흩는다.
    h = 0
    for i, ch in enumerate(text or ""):
        h = (h * 31 + ord(ch) + i) % 1_000_003
    line = CHITCHAT_LINES[h % len(CHITCHAT_LINES)]
    return clarify_reply(line, "잡담 -> 안내", cond)


# 열린 추천에서 한 번에 보여줄 가게 수
OPEN_PICK = 3

# 공강에 그냥 들러볼 수 있는 업종만 연다.
#
# 분산 점수는 '희소할수록 높은 점수'라, 그대로 두면 화장품(5곳)·꽃집(12곳)처럼
# 수가 적다는 이유만으로 1위가 된다. 실제로 학원·부동산이 추천으로 나왔다.
# 공강 20분에 부동산이나 학원을 권할 수는 없다. 그래서 분산은 '들를 수 있는
# 업종' 안에서만 시킨다 — 다양성을 늘리려다 엉뚱한 걸 권하면 신뢰를 잃는다.
OPEN_CATEGORIES = logic.CHAINABLE_CATEGORIES

# 라운드로빈 후보 풀 크기와, 사용자별 회전 위치.
# 물어볼 때마다 다른 조합이 나와야 "또 같은 소리"가 되지 않는다.
OPEN_ROTATE_POOL = 6
OPEN_ROTATION: dict[str, int] = {}


def open_recommend(text: str, cond: dict, user_id: str,
                   campus: str | None, lat, lng) -> dict:
    """
    용도를 안 정한 사람에게 주는 추천.

    정렬 기준이 일반 추천과 다르다. 용도가 없으니 '관련성'으로 줄 세울 수
    없고, 그렇다고 가까운 순으로 뽑으면 회기동 상권 구성상 식사·카페가
    화면을 다 덮는다(두 업종이 전체의 65%). 그래서 diversity_score 로
    정렬하고 업종 중복을 막는다 — 이 프로젝트가 하려던 소비 분산이
    실제로 작동하는 지점이다.
    """
    mins = cond.get("minutes")
    if mins is None:
        user = db.get_user(user_id)
        if user and user.get("timetable"):
            mins = next_free_minutes(user["timetable"])
    mins = mins or 60                       # 시간표도 없으면 한 시간 기준

    near = [enrich(s, campus=campus) for s in db.get_stores()]
    if lat is not None and lng is not None:
        near = apply_user_position(near, lat, lng)
    elif campus:
        lim = CAMPUS_WALK_LIMIT.get(campus, 15)
        near = [s for s in near if s.get("walk_min", 99) <= lim] or near

    fit = [s for s in near
           if s["category"] in OPEN_CATEGORIES and logic.fits_in_time(s, mins)]
    if not fit:
        return clarify_reply(
            f"지금 위치에서 {mins}분 안에 다녀올 만한 곳이 없네요. "
            f"시간이 더 있거나 학교 근처로 오시면 다시 찾아드릴게요.",
            "열린 추천 -> 후보 없음", cond)

    # 업종당 최고점 1곳만 남기고, 분산 점수로 줄을 세운다.
    best: dict[str, dict] = {}
    for s in fit:
        s["_div"] = logic.diversity_score(s)
        c = s["category"]
        if c not in best or s["_div"] > best[c]["_div"]:
            best[c] = s
    ranked = sorted(best.values(), key=lambda s: (-s["_div"], s["walk_min"]))

    # 여기서 그냥 상위 3개를 주면 물어볼 때마다 같은 답이 나온다.
    # ("실무·사진·꽃집"만 계속 나오는 문제) 상위권은 점수 차가 크지 않으므로,
    # 후보 풀 안에서 시작 지점을 돌린다(라운드로빈). 분산 실험에서 점수 정렬만
    # 썼을 때 특정 업종이 44%를 독점했는데, 이 회전을 넣어 HHI가 크게 떨어졌다.
    pool = ranked[:OPEN_ROTATE_POOL]
    n = OPEN_ROTATION.get(user_id, 0)
    OPEN_ROTATION[user_id] = n + 1
    picked = [pool[(n + i) % len(pool)] for i in range(min(OPEN_PICK, len(pool)))]

    kinds = " · ".join(s["category"] for s in picked)
    lead = (f"{mins}분 비시는군요. " if cond.get("minutes") else "")
    return {
        "condition": {**cond, "minutes": mins, "purpose": "열린추천"},
        "answer": f"{lead}딱 정하신 게 없으면 이런 곳은 어때요? ({kinds})\n"
                  f"평소 잘 안 가게 되는 업종 위주로, 지금 한산한 곳만 골랐어요.\n"
                  f"원하는 게 따로 있으면 말씀해주세요.",
        "stores": picked,
        "plan": {"remaining": mins,
                 "candidates": [s["name"] for s in picked], "itinerary": []},
        "pipeline": ["열린 추천", "분산 점수 정렬"],
    }


def clarify_reply(msg: str, pipeline: str, cond: dict | None = None) -> dict:
    """
    되묻기/안내 — 추천 카드를 만들지 않는다(폴백 환각 차단).
    단, 파싱된 조건은 그대로 돌려준다. 되물어도 이미 알아낸 시간·인원은
    버리지 않아야 다음 턴에서 다시 물어보지 않는다.
    """
    return {"condition": cond or {}, "answer": msg, "stores": [],
            "plan": {"remaining": None, "candidates": [], "itinerary": []},
            "pipeline": [pipeline]}


def recommend_reply(text: str, user_id: str, campus: str | None = None,
                    lat: float | None = None, lng: float | None = None) -> dict:
    """
    목업 4페이지 — 맥락 매칭 챗봇
      1) EXAONE   : 자연어 -> 조건
      2) 일반 코드 : 거리·시간 필터
      3) Chronos  : 혼잡도 (미리 계산된 값 조회)
      4) EXAONE   : 결과 -> 문장
    """
    # 빈 입력은 모델을 부르지 않는다 (모델이 빈 문자열에도 용도를 지어낸다)
    if not (text or "").strip():
        return clarify_reply(
            "무엇이 필요하신지 한 줄만 적어주세요.\n"
            '예) "40분 비는데 밥 먹을 데"', "빈 입력 -> 되묻기")

    cond = exaone.parse_query(text)                       # ① EXAONE

    # 용도를 못 뽑았거나, 뽑은 용도가 원문에 근거가 없으면(환각) 되묻는다.
    # (기존엔 purpose=None 이 '전체 통과'가 되어 "날씨/안녕"에 네일샵을 추천했다)
    if cond.get("purpose") and not purpose_supported(text, cond["purpose"]):
        # 버리기 전에 원문 근거로 교정 시도 (없으면 None -> 되묻기)
        cond["purpose"] = infer_purpose_from_text(text)
    if not cond.get("purpose"):
        # 모델이 용도를 아예 못 뽑았을 때도 원문 근거로 한 번 더 본다.
        # 예전에는 이 줄이 없어서 "심심해"가 그냥 되묻기로 빠졌다.
        # PURPOSE_EVIDENCE["레저"] 에 "심심"이 있는데도 조회조차 안 된 것이다.
        cond["purpose"] = infer_purpose_from_text(text)

    if not cond.get("purpose"):
        # 용도는 없지만 "뭐 할까"처럼 추천을 원한 게 분명하면, 되묻지 말고
        # 실제로 추천한다. 여기가 소비 분산이 작동해야 할 자리다 —
        # 용도를 안 정한 사람에게야말로 안 가본 업종을 보여줄 수 있다.
        if looks_open_request(text):
            return open_recommend(text, cond, user_id, campus, lat, lng)
        if is_chitchat(text):
            return chitchat_reply(text, cond)
        # 시간을 알려줬으면 막다른 되묻기 대신, 그 시간에 실제로 갈 수 있는 곳을
        # 업종을 섞어 보여주고 고르게 한다. (지어내지 않고 실제 후보만 제시)
        mins = cond.get("minutes")
        if mins:
            near = [enrich(s, campus=campus) for s in db.get_stores()]
            if lat is not None and lng is not None:
                near = apply_user_position(near, lat, lng)
            elif campus:
                lim = CAMPUS_WALK_LIMIT.get(campus, 15)
                near = [s for s in near if s.get("walk_min", 99) <= lim] or near
            fit = [s for s in near if logic.fits_in_time(s, mins)]
            picked, seen = [], set()
            for s in sorted(fit, key=lambda s: (s["congestion"], s["walk_min"])):
                if s["category"] in seen:
                    continue
                seen.add(s["category"]); picked.append(s)
                if len(picked) == 3:
                    break
            if picked:
                kinds = " · ".join(s["category"] for s in picked)
                return {"condition": cond,
                        "answer": f"{mins}분이면 이 정도 다녀올 수 있어요. ({kinds})\n"
                                  f"뭐가 필요한지 알려주시면 더 정확히 찾아드릴게요.",
                        "stores": picked,
                        "plan": {"remaining": None,
                                 "candidates": [s["name"] for s in picked], "itinerary": []},
                        "pipeline": ["시간 기준 후보 제시"]}
        return clarify_reply(
            "어떤 게 필요하신지 알려주시면 딱 맞는 곳을 찾아드릴게요.\n"
            '예) "40분 비는데 밥 먹을 데", "조용한 카페", "프린트 어디서 해"',
            "용도 불명확 -> 되묻기", cond)

    # 시간표와 대조한다.
    #   · 시간을 안 밝혔으면  -> 다음 수업까지 남은 시간을 대신 쓴다
    #   · 밝혔는데 수업과 겹치면 -> 실제 남은 시간으로 줄이고, 왜 줄였는지 알려준다
    #
    # "3시간 남았어" 를 그대로 믿으면 다음 수업 시각을 넘겨 계획하게 된다.
    # 시간표를 들고 있으면서 그걸 안 보는 건 우리 서비스가 할 일이 아니다.
    time_note = None
    user = db.get_user(user_id)
    tt = (user or {}).get("timetable")
    if tt:
        win = free_window(tt)
        if cond.get("minutes") is None:
            cond["minutes"] = win["minutes"]
            time_note = class_note(tt, win)
        elif cond["minutes"] > win["minutes"]:
            said = cond["minutes"]
            cond["minutes"] = win["minutes"]
            time_note = class_note(tt, win, said=said)
        else:
            # 말한 시간이 시간표 안에 들어가면 그대로 쓰되, 근거는 같이 보여준다.
            # "왜 이 시간이냐"를 매번 알 수 있어야 추천을 믿을 수 있다.
            if win["in_class"] or win["next_class"] is not None:
                time_note = class_note(tt, win, used=cond["minutes"])

    # 학교 기준으로 도보시간 계산 (경희대↔외대 거리 차이 반영)
    stores = [enrich(s, campus=campus) for s in db.get_stores()]

    if lat is not None and lng is not None:
        # 현재 위치를 알면 그 자리 기준으로 도보시간을 다시 계산한다.
        # 이때 캠퍼스 상한은 적용하지 않는다 — 기준점이 학교가 아니라 사용자이기 때문.
        stores = apply_user_position(stores, lat, lng)
    elif campus:
        # 위치를 모를 때만 학교 기준 상한 적용
        # ("외대인데 경희대 상권 가라" 같은 비현실적 추천 방지)
        limit = CAMPUS_WALK_LIMIT.get(campus, 15)
        near = [s for s in stores if s.get("walk_min", 99) <= limit]
        stores = near or stores          # 다 멀면(예외) 원본 유지

    matched = logic.filter_stores(stores, cond)           # ② 일반 코드
    matched.sort(key=lambda s: (s["congestion"], s["walk_min"]))  # 덜 붐비고 가까운 순
    top = matched[:3]                                     # ③ 후보 3곳 (선택지 보장)

    # 후보가 0곳이면 EXAONE 을 부르지 않는다.
    # 빈 목록을 주면 모델이 없는 상호("카페 드림" 등)를 지어내기 때문. (환각 차단)
    if not top:
        mins = cond.get("minutes")
        # 왜 못 가는지, 얼마면 갈 수 있는지를 실제 후보로 계산해 알려준다.
        # (없는 곳을 지어내지 않으면서도 "갈 수 없다"는 사실은 분명히 전달)
        pool = [s for s in stores if logic.match_purpose(s, cond.get("purpose"))]
        if mins and pool:
            nearest = min(pool, key=lambda s: s.get("walk_min", 99))
            walk = nearest.get("walk_min", 0)
            need = walk * 2 + logic.dwell_for(nearest)
            msg = (f"지금 위치에서 {mins}분 안에 다녀올 수 있는 곳이 없어요.\n"
                   f"가장 가까운 곳이 {nearest['name']}인데 편도 {walk}분이라 "
                   f"왕복만 {walk * 2}분입니다.\n"
                   f"{need}분쯤 여유가 있으면 다녀오실 수 있어요.")
            if time_note:
                msg = time_note + "\n" + msg
            why = "시간 부족 -> 추천 없음 + 사유 안내"
        elif pool:
            msg = ("조건에 맞는 곳을 찾지 못했어요.\n"
                   "시간이나 원하시는 걸 조금 바꿔서 다시 말씀해 주세요.")
            why = "조건 불충족 -> 추천 없음"
        else:
            msg = ("회기동에 그런 곳은 아직 등록돼 있지 않아요.\n"
                   "다른 걸 찾아볼까요?")
            why = "해당 업종 없음 -> 추천 없음"
        return clarify_reply(msg, why, cond)

    # ④ 남는 시간 계산 + 이어가기 활동 동선 (순수 계산)
    plan = logic.build_plan(cond, top, stores)

    # ⑤ EXAONE — 후보 3곳을 다 제시하고, 시간 남으면 동선까지
    answer = exaone.compose_recommendation(cond, top, plan)
    if time_note:
        # 시간표 근거를 맨 앞에 둔다. 왜 이 시간으로 잡았는지 먼저 알아야
        # 뒤따르는 추천이 납득된다.
        # 앞줄에서 이미 남은 시간을 말했으므로 본문의 "N분 있으시네요"는 뺀다.
        body = re.sub(r"^\d+분\s*있으시네요\.\s*", "", answer)
        answer = time_note + "\n\n" + body

    # 화면 노출: 첫 활동 후보 3곳을 먼저, 그 뒤에 이어가기 동선
    shown = list(top)                                     # 밥집 등 후보 3곳
    for f in plan.get("followups", []):
        if all(f["store"]["id"] != s["id"] for s in shown):
            shown.append(f["store"])

    return {"condition": cond, "answer": answer, "stores": shown,
            "plan": {"remaining": plan.get("remaining"),
                     "primary_dwell": plan.get("primary_dwell"),
                     "candidates": [s["name"] for s in top],
                     "itinerary": [f["store"]["name"] for f in plan.get("followups", [])]},
            "pipeline": ["EXAONE 파싱", "코드 필터", "Chronos 조회",
                         "동선 계산", "EXAONE 생성"]}


# ---- 목업 5페이지 — 단체예약, 여러 턴에 걸친 대화 ----
def looks_like_booking(text: str) -> int | None:
    """인원 수 + 예약 관련 키워드가 같이 있으면 단체예약 의도로 판단 (규칙 기반, AI 아님)"""
    m = re.search(r"(\d+)\s*명", text)
    if not m:
        return None
    keywords = ["예약", "총회", "모임", "회식", "엠티", "대관", "자리 있", "가능한"]
    return int(m.group(1)) if any(k in text for k in keywords) else None


def start_booking(user_id: str, people: int | None = None) -> dict:
    if people is None:
        BOOKING_SESSIONS[user_id] = {"step": "await_people"}
        return {"answer": "몇 분이서 모이시나요?", "stores": [],
                "pipeline": ["단체예약 시작"]}
    BOOKING_SESSIONS[user_id] = {"step": "await_when", "people": people}
    return {"answer": "언제로 예약하시나요?", "stores": [],
            "pipeline": ["단체예약 · 인원 확인"]}


def handle_booking_followup(user_id: str, text: str) -> dict:
    sess = BOOKING_SESSIONS[user_id]

    if sess["step"] == "await_people":
        m = re.search(r"(\d+)", text)
        if not m:
            return {"answer": "인원 수를 숫자로 알려주세요. 예) 25명", "stores": [],
                    "pipeline": ["단체예약 · 재질문"]}
        sess["people"] = int(m.group(1))
        sess["step"] = "await_when"
        return {"answer": "언제로 예약하시나요?", "stores": [],
                "pipeline": ["단체예약 · 인원 확인"]}

    # step == "await_when" — 이번 메시지를 날짜·시간으로 간주
    people = sess["people"]
    when_text = text
    del BOOKING_SESSIONS[user_id]

    stores = [enrich(s) for s in db.get_stores()
              if s.get("capacity", 0) >= people and s["category"] in GROUP_CATEGORIES]
    stores.sort(key=lambda s: (s["capacity"] - people, s["walk_min"]))
    top = stores[:3]

    answer = exaone.compose_booking_result(people, when_text, top)   # EXAONE
    return {"answer": answer, "stores": top,
            "pipeline": ["단체예약 필터", "EXAONE 생성"]}


# ---- 목업 17페이지 — 후기 수집, 챗봇 대화형 ----
def start_review(user_id: str) -> dict:
    REVIEW_SESSIONS[user_id] = {"step": "await_store"}
    return {"answer": "어느 가게 얘기예요? 상호명을 말씀해주세요.", "stores": [],
            "pipeline": ["후기 수집 시작"]}


def handle_review_followup(user_id: str, text: str) -> dict:
    sess = REVIEW_SESSIONS[user_id]

    if sess["step"] == "await_store":
        match = next((s for s in db.get_stores()
                     if s["name"] in text or text.strip() in s["name"]), None)
        if not match:
            return {"answer": "어느 가게인지 못 찾았어요. 정확한 이름으로 다시 말씀해주실래요?",
                    "stores": [], "pipeline": ["후기 · 가게 미매칭"]}
        sess["store_id"], sess["store_name"] = match["id"], match["name"]
        sess["step"] = "await_text"
        return {"answer": f"{match['name']}, 어땠어요? 편하게 말씀해주세요.",
                "stores": [], "pipeline": ["후기 · 가게 확인됨"]}

    # step == "await_text"
    store_id, store_name = sess["store_id"], sess["store_name"]
    del REVIEW_SESSIONS[user_id]

    category = logic.classify_review_category(text)               # 규칙 기반, AI 아님
    db.add_review(store_id, text)
    existing = db.get_reviews(store_id)
    count = sum(1 for r in existing if logic.classify_review_category(r["text"]) == category)

    answer = exaone.compose_review_ack(store_name, category, count)   # EXAONE
    return {"answer": answer, "stores": [],
            "pipeline": ["규칙 분류", "EXAONE 생성"]}


# ---- 목업 18페이지 — 월간 설문, 챗봇 ----
def start_survey(user_id: str) -> dict:
    SURVEY_SESSIONS.add(user_id)
    return {"answer": SURVEY_QUESTION, "stores": [], "pipeline": ["월간 설문 시작"]}


def handle_survey_answer(user_id: str, text: str) -> dict:
    SURVEY_SESSIONS.discard(user_id)
    db.add_survey_response(text, now().date().isoformat())

    responses = db.get_survey_responses()
    yes_words = ["네", "알아", "응", "맞아", "알고"]
    yes_count = sum(1 for r in responses if any(w in r["text"] for w in yes_words))
    pct = round(yes_count / len(responses) * 100) if responses else 0

    answer = exaone.compose_survey_ack(text, len(responses), pct)     # EXAONE
    return {"answer": answer, "stores": [],
            "pipeline": ["설문 집계", "EXAONE 생성"]}


@app.get("/api/chat/today")
def api_chat_today(user_id: str = "me", campus: str | None = None,
                   day: str | None = None, start: int | None = None,
                   end: int | None = None):
    """
    챗봇을 열면 학생이 묻기 전에, 공강을 보고 먼저 활동을 제안한다.
      시간표 → 연속 공강 → build_plan(동선) → EXAONE 안내 문장

    day/start/end 를 주면 그 구간으로 제안한다.
    친구 시간표에서 "이 시간에 갈 곳 찾기"로 넘어오는 경우가 그렇다 —
    화면에는 '월요일 13-16시'가 떠 있는데 챗봇이 오늘(목요일)로 다시 계산하면
    같은 화면에서 다른 요일을 말하게 된다.
    """
    campus = campus if campus in CAMPUSES else None
    user = db.get_user(user_id)
    if not user or not user.get("timetable"):
        return {"has_free": False,
                "answer": "시간표를 등록하면 공강 시간에 맞춰 먼저 추천해드릴게요."}

    if day and start is not None and end is not None and end > start:
        # 화면이 이미 고른 구간을 그대로 쓴다 (오늘로 다시 계산하지 않는다).
        #
        # 한 번에 계획하는 건 3시간까지만 잡는다. 그때 끝 시각도 같이 줄여야
        # "11시부터 22시까지 약 180분" 처럼 앞뒤가 안 맞는 문장이 안 나온다.
        minutes = min((end - start) * 60, 180)
        block = {"day": day, "start": start,
                 "end": start + minutes // 60, "minutes": minutes}
    else:
        block = logic.today_free_block(user["timetable"], now())
    if not block:
        return {"has_free": False,
                "answer": "오늘은 지금 이후로 비는 시간이 넉넉하진 않네요. "
                          "필요할 때 물어봐 주세요."}

    # 공강 시간을 조건으로 삼아, 밥부터 시작하는 동선 추천 (요청 없이 선제 제안)
    cond = {"minutes": block["minutes"], "purpose": "식사", "people": 1}
    stores = [enrich(s, campus=campus) for s in db.get_stores()]
    if campus:
        limit = CAMPUS_WALK_LIMIT.get(campus, 15)
        stores = [s for s in stores if s.get("walk_min", 99) <= limit] or stores
    matched = logic.filter_stores(stores, cond)
    matched.sort(key=lambda s: (s["congestion"], s["walk_min"]))
    top = matched[:3]
    plan = logic.build_plan(cond, top, stores)

    intro = (f"{block['day']}요일 {block['start']}시부터 {block['end']}시까지 "
             f"약 {block['minutes']}분 비네요. 이 시간에 이렇게 보내보시는 건 어때요?\n\n")
    # 자동 추천이라 앞의 "N분 있으시네요" 중복은 빼고 붙인다
    body = exaone.compose_recommendation(cond, top, plan)
    body = re.sub(r"^\d+분\s*있으시네요\.\s*", "", body)
    answer = intro + body

    followups = plan.get("followups", [])
    shown = [plan["primary"]] if plan.get("primary") else top[:1]
    for f in followups:
        if all(f["store"]["id"] != s["id"] for s in shown):
            shown.append(f["store"])

    return {"has_free": True, "block": block, "answer": answer,
            "stores": shown, "pipeline": ["시간표 공강 계산", "동선 계산", "EXAONE 생성"]}


def next_class_hour(timetable: dict, at: datetime | None = None) -> int | None:
    """오늘 남은 수업 중 가장 이른 시각. 없으면 None."""
    at = at or now()
    if at.weekday() > 4:
        return None
    classes = sorted(timetable.get(WEEKDAY_KR[at.weekday()], []))
    later = [h for h in classes if h > at.hour]
    return later[0] if later else None


def free_window(timetable: dict, at: datetime | None = None) -> dict:
    """
    시간표에서 '쓸 수 있는 시간'을 찾는다.

    지금 수업 중이면 그 수업이 끝난 뒤부터 잡는다. 수업 중이라고 0분을 돌려주면
    "조건에 맞는 곳이 없다"로 끝나버려서, 정작 필요한 안내(언제부터 비는지)를 못 준다.

    반환: {"minutes", "start", "next_class", "in_class"}
    """
    # 활동 추천이 현실적인 마지막 시각. 상한을 분 단위로 두지 않고
    # "몇 시까지 열려 있나"로 잡아야 5시간 넘는 공강도 그대로 나온다.
    END_HOUR = 21
    at = at or now()
    if at.weekday() > 4:
        # 주말 — 수업 개념이 없으니 지금부터 END_HOUR 까지
        return {"minutes": max((END_HOUR - at.hour) * 60 - at.minute, 0),
                "start": at.hour, "next_class": None, "in_class": False}

    classes = sorted(timetable.get(WEEKDAY_KR[at.weekday()], []))
    hour = at.hour

    if hour in classes:                       # 수업 중 — 연속 수업이 끝나는 시각까지 민다
        end = hour
        while end + 1 in classes:
            end += 1
        start = end + 1
        nxt = next((h for h in classes if h > start), None)
        # 남은 수업이 없으면 21시까지를 활동 가능 시간으로 본다(최대 300분).
        minutes = (nxt - start) * 60 if nxt else max((END_HOUR - start) * 60, 0)
        return {"minutes": minutes, "start": start,
                "next_class": nxt, "in_class": True}

    nxt = next((h for h in classes if h > hour), None)
    minutes = ((nxt - hour) * 60 - at.minute if nxt
               else max((END_HOUR - hour) * 60 - at.minute, 0))
    return {"minutes": max(minutes, 0), "start": hour,
            "next_class": nxt, "in_class": False}


def class_note(timetable: dict, win: dict, said: int | None = None,
               used: int | None = None) -> str | None:
    """
    추천 앞에 붙일 한 줄 — '다음 수업까지 얼마 남았는지'를 먼저 말한다.

    추천만 던지면 "왜 하필 이만큼이지" 를 알 수 없다. 시간표를 근거로
    남은 시간을 먼저 밝히고, 그 시간에 맞춰 고른 결과를 뒤에 붙인다.
    said(사용자가 말한 시간)가 실제보다 길면 줄인 이유도 함께 밝힌다.
    """
    # used 를 주면 그 값으로 말한다. 사용자가 더 짧게 말했을 때
    # "40분"이라 해놓고 "120분으로 잡았어요"가 되는 걸 막는다.
    mins = used if used is not None else win["minutes"]
    nxt, start = win["next_class"], win["start"]

    if win["in_class"]:
        head = f"지금 수업 중이라 {start}시에 끝나요."
        body = (f" 다음 수업이 {nxt}시라 그 사이 {mins}분 비어요."
                if nxt else f" 그 뒤로는 수업이 없어서 {mins}분으로 잡았어요.")
    elif nxt is not None:
        head = f"다음 수업이 {nxt}시예요."
        body = f" 지금부터 {mins}분 남았어요."
    else:
        head = "오늘 남은 수업은 없어요."
        body = f" {start}시 기준 {mins}분으로 잡았어요."

    if said is not None and said > mins:
        return f"{head}{body} ({said}분이라고 하셨지만 그 안으로 맞췄어요.)"
    return head + body


def next_free_minutes(timetable: dict, at: datetime | None = None) -> int | None:
    """지금부터 다음 수업 시작까지 남은 분 — 순수 계산, AI 아님.
    기준 시각은 now() 가 준다(데모 모드면 고정 시각)."""
    at = at or now()
    if at.weekday() > 4:
        return 120
    day = WEEKDAY_KR[at.weekday()]
    classes = sorted(timetable.get(day, []))
    if at.hour in classes:
        return 0
    upcoming = [h for h in classes if h > at.hour]
    if not upcoming:
        return 120
    return (upcoming[0] - at.hour) * 60 - at.minute


# --------------------------------------------------------- 시간표 API
@app.get("/api/timetable/{user_id}")
def api_get_timetable(user_id: str):
    user = db.get_user(user_id)
    if not user:
        return {"user_id": user_id, "timetable": {}, "name": user_id}
    return {"user_id": user_id, "name": user.get("name"),
            "timetable": user.get("timetable", {}),
            "major": user.get("major", ""), "campus": user.get("campus", ""),
            "free": logic.free_slots(user.get("timetable", {}))}


@app.post("/api/timetable")
def api_save_timetable(payload: dict = Body(...)):
    """
    학생 온보딩 — 시간표(표 직접 입력) + 전공(자연어).
      - 시간표: AI 없이 표 그대로가 정확한 데이터
      - 전공 문장: 그대로 저장(BGE-M3 프로젝트 매칭의 프로필로 쓰임)
        + 학교(경희대/한국외대)를 추론해 이후 추천 거리 계산에 사용
    """
    major = (payload.get("major") or "").strip()
    campus = infer_campus(major)
    db.save_timetable(payload.get("user_id", "me"),
                      payload.get("name", ""),
                      payload.get("timetable", {}),
                      major=major or None,
                      campus=campus)
    return {"ok": True, "major": major, "campus": campus}


@app.get("/api/friends/intersect")
def api_intersect(users: str = "me"):
    """목업 7페이지 — 친구 시간표 겹쳐보기. 저장된 표끼리 비교만 하므로 AI 불필요."""
    ids = [u.strip() for u in users.split(",") if u.strip()]
    tables, names = [], []
    for uid in ids:
        u = db.get_user(uid)
        if u:
            tables.append(u.get("timetable", {}))
            names.append(u.get("name", uid))
    common = logic.intersect(tables)
    return {"members": names, "common_free": common,
            "blocks": logic.to_blocks(common)}


@app.get("/api/friends")
def api_friends(user_id: str = "me"):
    return [{"id": u["id"], "name": u["name"]} for u in db.get_users()]


# ------------------------------------------------------- 프로젝트 API
@app.get("/api/projects")
def api_projects(user_id: str = "me"):
    """
    목업 19페이지 — 프로젝트 매칭
      ① BGE-M3   : 과제 텍스트 <-> 학생 전공 의미 유사도
      ② 일반 코드 : 공강 시간 >= 과제 소요시간 인지 확인
    """
    user = db.get_user(user_id) or {}
    profile = f"{user.get('major','')} {user.get('interests','')}".strip()
    free = logic.free_slots(user.get("timetable", {}))
    max_block = max((len(v) for v in free.values()), default=0)

    out = []
    for p in db.get_projects():
        sim = bge.similarity(f"{p['title']} {p['description']}", profile)   # ①
        time_ok = max_block >= 2                                            # ②
        out.append({**p, "similarity": sim, "time_ok": time_ok,
                    "reason_major": f"내 전공({user.get('major','')})과 맞아요" if sim >= 0.6 else None,
                    "reason_time": f"공강 {max_block}시간에 가능해요" if time_ok else None})
    out.sort(key=lambda p: p["similarity"], reverse=True)
    return out


@app.post("/api/projects")
def api_add_project(payload: dict = Body(...)):
    """목업 20페이지 — 상인 과제 등록"""
    pid = f"p{len(db.get_projects()) + 100}"
    db.add_project({**payload, "id": pid})
    return {"ok": True, "id": pid}


# ---------------------------------------------------------- 상인 API
@app.post("/api/merchant/store")
def api_add_store(payload: dict = Body(...)):
    """목업 15페이지 — 3분이면 끝나는 등록. POS 연동 없음."""
    sid = f"s{len(db.get_stores()) + 300}"
    db.add_store({**payload, "id": sid})
    return {"ok": True, "id": sid}


@app.get("/api/merchant/dashboard/{store_id}")
def api_dashboard(store_id: str):
    """목업 10페이지 — 시간대별 유입 현황"""
    store = db.get_store(store_id)
    if not store:
        return JSONResponse({"error": "not found"}, status_code=404)
    today = now()
    hourly = []
    for hour in range(10, 22):
        raw = chronos.get_congestion(store_id, today.weekday(), hour)
        corr = logic.correction_factor(today.date(), db.get_calendar())
        score = logic.apply_correction(raw, corr["factor"])
        hourly.append({"hour": hour, "score": score,
                       "label": chronos.to_label(score)})
    return {"store": store, "hourly": hourly}


def build_timetable_insight() -> dict:
    """
    등록된 학생 시간표 전체 + 학사일정을 종합해, 사장님 리포트의 근거 블록을 만든다.
      - 어느 요일에 공강이 몰려 방문이 많고, 어느 요일이 한산한지
      - 어느 시간대에 공강 학생이 가장 많은지
      - 방학·시험기간·축제 때 어떻게 달라지는지 (학사일정 기준)
    """
    timetables = db.get_student_timetables()    # 합성 120명 + 실제 등록 학생
    if not timetables:
        return {}

    agg = logic.aggregate_timetables(timetables)
    by_day, by_hour = agg["by_day"], agg["by_hour"]
    busiest_day = max(by_day, key=by_day.get)
    quietest_day = min(by_day, key=by_day.get)
    busiest_hour = max(by_hour, key=by_hour.get)

    # 낮(점심~오후) 시간대 피크 — 저녁 전원공강(19시+)을 빼고 실제 영업에 쓸모있는 피크
    day_hours = {h: v for h, v in by_hour.items() if 9 <= h <= 18}
    lunch_peak = max(day_hours, key=day_hours.get) if day_hours else busiest_hour

    # 오늘이 학사일정상 어떤 시기인지 + 다가오는 학사일정(며칠 뒤)
    cal = db.get_calendar()
    today = now().date()
    today_iso = today.isoformat()
    period = "평상시"
    upcoming = None      # (라벨, 며칠 뒤)
    for univ, sched in cal.items():
        if not isinstance(sched, dict):
            continue
        for kind, items in (("방학", sched.get("vacation", [])),
                            ("시험기간", sched.get("exam", [])),
                            ("축제", sched.get("event", []))):
            for p in items:
                if p["start"] <= today_iso <= p["end"]:
                    period = kind
                # 30일 안에 시작하는 이벤트 = 미리 대비 대상
                try:
                    d0 = date.fromisoformat(p["start"])
                    days_to = (d0 - today).days
                    if 0 < days_to <= 30:
                        if upcoming is None or days_to < upcoming[1]:
                            upcoming = (f"{univ} {p.get('label', kind)}", days_to)
                except Exception:
                    pass

    calendar_note = {
        "방학": "지금은 방학이라 학생 유입이 학기 중보다 약 9.5% 줄어드는 시기입니다.",
        "시험기간": "지금은 시험기간이라 스터디카페·카페 수요는 늘지만 저녁 회식 수요는 줄어드는 경향입니다.",
        "축제": "지금은 대학 축제 기간이라 평소보다 학생 유입이 크게 늘어나는 시기입니다.",
        "평상시": "지금은 학기 중 평상시로, 요일별 공강 분포가 그대로 방문 패턴에 반영됩니다.",
    }[period]
    upcoming_note = ""
    if upcoming:
        upcoming_note = f" {upcoming[1]}일 뒤 '{upcoming[0]}'이 예정돼 있어 미리 대비가 필요합니다."

    prompt_block = (
        f"[학생 공강 종합 — 등록 학생 {agg['n_students']}명 시간표 집계]\n"
        f"- 요일별 평균 공강 학생 수: "
        + ", ".join(f"{d} {by_day[d]}명" for d in logic.WEEK) + "\n"
        f"- 공강이 가장 많은 요일(방문 몰림): {busiest_day} / 가장 적은 요일(한산): {quietest_day}\n"
        f"- 낮 시간대 공강 피크(점심·오후 영업 대비): {lunch_peak}시\n"
        f"[학사일정] 오늘은 '{period}'. {calendar_note}{upcoming_note}"
    )
    return {
        "n_students": agg["n_students"],
        "by_day": by_day, "by_hour": by_hour,
        "busiest_day": busiest_day, "quietest_day": quietest_day,
        "busiest_hour": busiest_hour, "lunch_peak": lunch_peak,
        "period": period, "calendar_note": calendar_note,
        "upcoming": upcoming[0] if upcoming else None,
        "upcoming_days": upcoming[1] if upcoming else None,
        "prompt_block": prompt_block,
    }


@app.get("/api/merchant/report/{store_id}")
def api_report(store_id: str):
    """
    목업 14·21페이지 — 컨설팅 리포트
      회기동 실데이터 추이(Chronos) + 요일·시간대 프로파일 + 누적 후기
      + 학생 시간표 종합 공강 분포 + 학사일정
      -> EXAONE이 맥락을 판단해 문장으로 작성. 사장님이 요청할 때만 생성한다.
    """
    store = db.get_store(store_id)
    if not store:
        return JSONResponse({"error": "not found"}, status_code=404)

    today = now().date()
    corr = logic.correction_factor(today, db.get_calendar())

    # ① 회기동 실데이터 기반 분기 추이 (업종 단위, 데이터 짧으면 유사 업종 대체)
    trend = chronos.predict_trend(category=map_category_for_store(store))
    trend_text = logic.trend_sentence(trend)

    # ①-b 월별 생활인구 추이(사람 수) + 매출과의 연결(전환율·교차검증)
    pop = chronos.predict_population()
    link = chronos.link_population_sales()
    pop_link_text = logic.population_sales_sentence(pop, link, trend)

    # ② 실제 요일·시간대 프로파일에서 피크 탐색
    profile = chronos.profile_summary()
    best, best_score = None, -1
    for wd in range(5):
        for hour in (12, 13, 18, 19):
            s = chronos.get_congestion(store_id, wd, hour)
            if s > best_score:
                best_score, best = s, f"{WEEKDAY_KR[wd]}요일 {hour}시"

    # ③ 점주 실측으로 캘리브레이션된 계수
    reports = db.get_daily_reports(store_id)
    preds = {r["date"]: chronos.get_congestion(store_id, 2, 13) for r in reports}
    calib = logic.calibrate(reports, preds, db.get_calibration().get(store_id))

    # ④ 학생 시간표 종합 + 학사일정 (요청하신 핵심 근거)
    insight = build_timetable_insight()

    reviews = db.get_reviews(store_id)
    analysis = exaone.analyze_reviews(reviews)

    # ⑤ 학생 목소리 — 후기에서 키워드/의도/트렌드를 뽑아 '비전 카드'로 만든다.
    #    판단은 전부 voice.py(코드)가 하고, EXAONE은 결과를 문장으로 옮기기만 한다.
    #    IDF 계산에 상권 전체 후기가 필요하므로 db.get_reviews()를 통째로 넘긴다.
    voice_report = voice.build_voice_report(reviews, db.get_reviews())

    text = exaone.compose_merchant_report(
        store, {"peak_label": best, "peak_score": best_score,
                "trend": trend_text, "pop_link": pop_link_text,
                "borrowed_from": trend.get("borrowed_from")}, reviews, insight,
        voice_report
    )
    return {"store": store, "report": text, "analysis": analysis,
            "voice": voice_report,
            "correction": corr, "review_count": len(reviews),
            "trend": trend, "trend_text": trend_text,
            "population": pop, "pop_link": link, "pop_link_text": pop_link_text,
            "profile": profile, "calibration": calib,
            "timetable_insight": {k: insight.get(k) for k in
                                  ("n_students", "by_day", "by_hour",
                                   "busiest_day", "quietest_day",
                                   "busiest_hour", "lunch_peak",
                                   "period", "calendar_note")}
                                  if insight else None}


# 앱 업종명 -> 서울시 상권분석 업종명 (실제 보유 24개 업종에 맞춰 매핑)
CATEGORY_MAP = {
    "식사": "한식음식점",      # 대표(세부는 아래 detail 매핑으로 정밀화)
    "가볍게": "커피-음료",
    "편의점": "편의점", "의류": "일반의류", "미용실": "미용실",
    "학원": "일반교습학원", "화장품": "화장품", "꽃집": "화초",
    "의료": "의약품", "가정": "안경", "레저": "노래방",
    # 실무(서점·스터디·문구·인쇄)는 매칭 상권업종 없음 -> 전체 시계열 사용
}

# category_detail -> 상권분석 업종명 (통합 업종을 세부 업종의 실제 매출 시계열로 정밀 매핑)
DETAIL_SALES = [
    (("커피", "카페", "음료", "제과", "베이커리", "빵", "주스"), "커피-음료"),
    (("주점", "호프", "맥주", "포차", "바"), "호프-간이주점"),
    (("치킨", "닭"), "치킨전문점"),
    (("분식", "김밥", "떡볶이", "토스트"), "분식전문점"),
    (("중식", "중국"), "중식음식점"),
    (("일식", "초밥", "돈가스", "돈까스", "라멘", "우동", "스시"), "일식음식점"),
    (("피자", "파스타", "스테이크", "햄버거", "양식", "경양식"), "양식음식점"),
    (("한식", "백반", "한정식", "국밥", "찌개", "구이", "찜"), "한식음식점"),
    (("약국",), "의약품"), (("안경",), "안경"), (("화장품",), "화장품"),
    (("노래", ), "노래방"), (("당구",), "당구장"), (("pc", "피시"), "PC방"),
    (("꽃", "화훼"), "화초"), (("네일",), "네일숍"), (("신발",), "신발"),
    (("학원", "교습", "독서실", "스터디"), "일반교습학원"),
    (("슈퍼", "마트"), "슈퍼마켓"),
]


def map_category_for_store(store: dict) -> str | None:
    """가게의 category_detail 로 실제 업종 매출 시계열을 고른다. 없으면 category 기반."""
    sales = chronos.data.get("sales_by_category") or {}
    det = store.get("category_detail", "")
    for keys, name in DETAIL_SALES:
        if any(k in det for k in keys):
            return name if name in sales else None
    return map_category(store.get("category"))


def map_category(app_category: str) -> str | None:
    """앱 업종명 -> 서울시 상권분석 업종명. 없으면 None(상권 전체 시계열 사용)."""
    name = CATEGORY_MAP.get(app_category)
    if name and name in (chronos.data.get("sales_by_category") or {}):
        return name
    return None


@app.post("/api/merchant/daily")
def api_daily_report(payload: dict = Body(...)):
    """
    점주 일일 보고 — 자연어로 입력받아 EXAONE이 수치로 변환.
    이 실측값이 Chronos 예측을 교정하는 유일한 근거가 된다.
    """
    store_id = payload["store_id"]
    text = payload.get("text", "")
    parsed = exaone.parse_daily_report(text)                       # EXAONE
    today = now().date().isoformat()
    db.add_daily_report(store_id, today, parsed, text)

    # 누적 실측으로 보정계수 재계산 (모델 재학습 아님)
    reports = db.get_daily_reports(store_id)
    preds = {r["date"]: chronos.get_congestion(store_id, 2, 13) for r in reports}
    store_calib = db.get_calibration()
    calib = logic.calibrate(reports, preds, store_calib.get(store_id))
    store_calib[store_id] = calib
    db.save_calibration(store_calib)

    return {"ok": True, "parsed": parsed, "calibration": calib,
            "total_reports": len(reports)}


@app.get("/api/merchant/trend/{store_id}")
def api_trend(store_id: str):
    """회기동 실데이터 기반 업종별 추이 — 수치보다 방향성"""
    store = db.get_store(store_id)
    if not store:
        return JSONResponse({"error": "not found"}, status_code=404)
    cat = map_category_for_store(store)
    trend = chronos.predict_trend(category=cat)
    return {"store": store, "mapped_category": cat,
            "trend": trend, "sentence": logic.trend_sentence(trend),
            "vacation_effect": chronos.data.get("vacation_effect")}


@app.get("/api/nearby")
def api_nearby(lat: float, lng: float, category: str | None = None, limit: int = 20):
    """
    현재 위치 기준 실제 도보 거리·시간.
    좌표는 브라우저 Geolocation API 가 준다 (별도 발급 불필요).
    """
    lat, lng = demo_position(lat, lng)
    stores = db.get_stores()
    if category:
        stores = [s for s in stores if s["category"] == category]
    near = routing.walk_from(lat, lng, stores, limit=limit)
    return [enrich(s) for s in near]


@app.get("/api/route")
def api_route(lat: float, lng: float, store_id: str):
    """한 점포까지의 상세 경로 — 앱 안에서 보여준다 (외부 앱으로 넘기지 않음)"""
    lat, lng = demo_position(lat, lng)     # 데모 모드면 경희대 정문에서 출발
    store = db.get_store(store_id)
    if not store or store.get("lat") is None:
        return JSONResponse({"error": "좌표 없음"}, status_code=404)
    detail = routing.route_detail(lat, lng, store)
    return {"store": store, **detail}


@app.get("/api/free-now")
def api_free_now(user_id: str = "me"):
    """
    지금 몇 분 비는지 — 홈 상단 배너용.

    화면이 브라우저 시계로 따로 계산하면 챗봇 답변과 어긋난다(데모 시각도 무시된다).
    그래서 챗봇이 쓰는 free_window() 를 그대로 돌려 한 곳에서 계산한다.
    """
    user = db.get_user(user_id)
    tt = (user or {}).get("timetable")
    if not tt:
        return {"has": False, "text": "시간표를 등록해 주세요",
                "sub": "등록하면 공강에 맞춰 추천해드려요"}

    at = now()
    if at.weekday() > 4:
        return {"has": False, "text": "오늘은 주말이에요",
                "sub": f"{at.hour}시 기준"}

    win = free_window(tt, at)
    mins, nxt, start = win["minutes"], win["next_class"], win["start"]

    if win["in_class"]:
        text = f"{start}시부터 {mins // 60}시간 공강이에요" if mins >= 60 \
               else f"{start}시부터 {mins}분 공강이에요"
        sub = f"지금 수업 중 · 다음 수업 {nxt}시" if nxt else "지금 수업 중 · 이후 수업 없음"
    else:
        text = f"지금 {mins // 60}시간 공강이에요" if mins >= 60 \
               else f"지금 {mins}분 공강이에요"
        sub = f"다음 수업 {nxt}시 시작" if nxt else f"오늘 남은 수업 없음 · {at.hour}시 기준"

    # 이 숫자가 시간표 어디에서 나왔는지 화면이 그대로 보여줄 수 있게 근거를 같이 준다.
    # (저장이 안 된 건지, 화면이 옛 응답을 그리는 건지 눈으로 갈린다)
    day = WEEKDAY_KR[at.weekday()]
    classes = sorted(tt.get(day, []))
    basis = (f"{day} 수업 {'·'.join(f'{h}시' for h in classes)}" if classes
             else f"{day} 수업 없음")
    return {"has": True, "text": text, "sub": sub,
            "day": day, "classes": classes,
            "basis": f"{basis} · {at.hour}시 기준", **win}


@app.get("/api/config")
def api_config():
    """
    화면이 알아야 할 실행 설정.

    데모 모드일 때 브라우저가 GPS 를 못(안) 켜도 '가는 길'이 막히지 않도록,
    출발지를 여기서 내려준다. 서버도 같은 좌표로 덮어쓰므로 둘이 어긋나지 않는다.
    """
    demo = DEMO_HOUR is not None
    return {"demo": demo,
            "hour": DEMO_HOUR,
            "campus": DEMO_CAMPUS if demo else None,
            "lat": DEMO_LAT if demo else None,
            "lng": DEMO_LNG if demo else None}


@app.get("/download/hoegi-stores.csv")
def download_csv():
    """소상공인 상가정보 회기동 원본 — UTF-8 BOM 이라 Excel 에서 바로 열린다"""
    path = BASE / "data" / "raw" / "회기동_상가정보.csv"
    if not path.exists():
        return JSONResponse({"error": "scripts/extract_smallbiz.py 를 먼저 실행하세요"},
                            status_code=404)
    return FileResponse(path, media_type="text/csv; charset=utf-8",
                        filename="회기동_상가정보.csv")


@app.get("/api/hoegi/stores")
def api_hoegi_stores():
    """소상공인시장진흥공단 상가정보에서 추출한 회기동 점포 원본"""
    path = BASE / "data" / "raw" / "회기동_상가정보.json"
    if not path.exists():
        return JSONResponse({"error": "scripts/extract_smallbiz.py 를 먼저 실행하세요"},
                            status_code=404)
    import json as _json
    return _json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/hoegi/profile")
def api_profile():
    """회기동 실데이터 프로파일 — 어떤 요일·시간이 붐비는가"""
    return {**chronos.profile_summary(),
            "meta": chronos.data.get("meta"),
            "vacation_effect": chronos.data.get("vacation_effect")}


# ------------------------------------------------------------ 후기 API
@app.get("/api/reviews")
def api_reviews(store_id: str | None = None):
    return db.get_reviews(store_id)


@app.post("/api/reviews")
def api_add_review(payload: dict = Body(...)):
    """목업 17페이지 — 챗봇으로 후기 수집. 별점·사진 없이 한 줄이면 끝."""
    db.add_review(payload["store_id"], payload["text"])
    return {"ok": True}


# ------------------------------------------------------------ 시스템
@app.get("/api/system")
def api_system():
    """모델 로드 상태와 실제 추론 지연시간 — 상태 화면이 이 값을 그대로 표시한다"""
    from app.ai import USE_STUB, STATUS

    gpu = {"available": False}
    try:
        import torch
        if torch.cuda.is_available():
            gpu = {
                "available": True,
                "name": torch.cuda.get_device_name(0),
                "count": torch.cuda.device_count(),
                "allocated_gb": round(torch.cuda.memory_allocated(0) / 1024**3, 2),
                "reserved_gb": round(torch.cuda.memory_reserved(0) / 1024**3, 2),
                "total_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1),
            }
    except Exception:
        pass

    meta = {
        "EXAONE": {"id": exaone.MODEL_ID, "role": "채널 · 자연어→조건 파싱, 리포트 작성",
                   "active_stub": exaone.use_stub},
        "Chronos": {"id": chronos.MODEL_ID, "role": "본체 · 분기 추이 예측",
                    "active_stub": chronos.use_stub},
        "BGE-M3": {"id": bge.MODEL_ID, "role": "매칭 · 과제↔학생 유사도",
                   "active_stub": bge.use_stub},
    }
    models = {k: {**meta[k], **STATUS[k]} for k in meta}

    return {
        "mode": "real" if not USE_STUB else "stub",
        "gpu": gpu,
        "models": models,
        "hint": "실제 모델로 켜려면: WOORISAI_REAL=1 uvicorn main:app",
    }


@app.get("/api/backtest")
def api_backtest(category: str | None = None, holdout: int = 4):
    """
    검증 설계에서 정한 기준을 실제로 판정한다.
      베이스라인(최근 4분기 평균) 대비 MAE 15% 이상 개선 -> 성공
    """
    return chronos.backtest(category=category, holdout=holdout)


@app.get("/api/backtest/yearly")
def api_backtest_yearly(series: str = "sales_quarterly"):
    """
    연도 기준 백테스트 — 2021~2024년 학습, 2025년(+2026) 테스트.
    series: "sales_quarterly"(2021~2025) 또는 "population_quarterly"(2021~2026Q1)
    """
    return chronos.year_backtest(series_name=series)


@app.get("/api/backtest/augmentation")
def api_backtest_augmentation(n_test: int = 5):
    """
    데이터 증강 검증 — 제공 유동인구만(A) vs 생활인구로 이력을 늘린 경우(B) vs 단순평균(C).
    타깃은 제공 유동인구(2026Q1 실측 보유)라 정답 비교가 가능하다.
    """
    return chronos.augmentation_backtest(n_test=n_test)


@app.post("/api/batch/predict")
def api_batch():
    """Chronos 배치 실행 — 실제로는 스케줄러가 하루 4~6회 호출"""
    result = [chronos.predict_batch(s["id"]) for s in db.get_stores()]
    return {"ok": True, "stores": len(result),
            "note": "예측값을 캐시에 저장했습니다. 학생 조회 시엔 이 값을 읽기만 합니다."}
