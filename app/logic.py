# -*- coding: utf-8 -*-
"""
로직 레이어 — AI가 아닌 일반 코드

정확도가 생명인 계산은 모델이 아니라 여기서 처리한다.
  - 공강/교집합 계산   : 저장된 시간표끼리 비교만 하면 되므로 AI 불필요
  - 거리·시간 필터     : 왕복시간 + 체류시간 <= 남은시간  (단순 비교)
  - 보정계수           : 1 + Σδ_i(t),  학사일정 조회 후 규칙 적용
"""
import re
from datetime import date

# 업종별 평균 체류시간(분) — 파일럿 데이터 쌓이면 실측값으로 교체
# 학생 기준 실제 체류시간 (점심은 30분보다 짧게, 파일럿 데이터로 교체 예정)
DWELL_MINUTES = {
    "꽃집": 10, "편의점": 5, "사진": 15, "공방": 60, "의류": 20,
    "미용실": 60, "학원": 90, "화장품": 15,
    "부동산": 20, "숙박": 30, "반려동물": 15,
    # 통합 그룹 (세부 업종은 category_detail 로 dwell_for 에서 더 정밀히)
    "식사": 25,    # 한·중·일·양
    "가볍게": 20,  # 카페·분식(짧음) / 술·치킨은 아래 detail 로 길게
    "의료": 15,    # 약국5~병원30 중간
    "가정": 15,    # 통신20·세탁5·안경20
    "실무": 25,    # 서점15·스터디90·문구10·인쇄5 — 학생 체류 중심 중간값
    "레저": 60,    # 오락·스포츠
}
DEFAULT_DWELL = 20

# 통합 업종 안에서 category_detail 로 체류시간 보정 (술자리는 길다)
DWELL_DETAIL = [(("주점", "호프", "맥주", "포차", "치킨", "닭"), 80)]


def dwell_for(store: dict) -> int:
    """가게의 체류시간(분). 통합 업종은 category_detail 로 더 정밀히 잡는다."""
    det = store.get("category_detail", "")
    for keys, mins in DWELL_DETAIL:
        if any(k in det for k in keys):
            return mins
    return DWELL_MINUTES.get(store.get("category"), DEFAULT_DWELL)


# ----------------------------------------------------------- 시간표
WEEK = ["월", "화", "수", "목", "금"]
DAY_HOURS = list(range(9, 22))          # 9~21시


def free_slots(timetable: dict) -> dict:
    """시간표(수업 있는 칸)를 뒤집어 공강 칸을 만든다."""
    out = {}
    for day, hours in timetable.items():
        out[day] = [h for h in range(9, 22) if h not in hours]
    return out


def aggregate_timetables(timetables: list) -> dict:
    """
    여러 학생 시간표를 종합해 '요일×시간대별 공강 학생 수'를 집계한다.
    사장님 리포트의 근거 — 어느 요일·시간에 학생이 학교 밖으로 나올 수 있는지.

    반환:
      by_day    : {요일: 그 요일 평균 공강 학생 수}       (요일 비교용)
      by_hour   : {시각: 그 시각 평균 공강 학생 수}       (시간대 비교용)
      grid      : {요일: {시각: 공강 학생 수}}            (상세)
      n_students: 집계에 쓴 학생 수
    """
    n = len(timetables)
    grid = {d: {h: 0 for h in DAY_HOURS} for d in WEEK}
    for tt in timetables:
        for d in WEEK:
            classes = set(tt.get(d, []))            # 그 요일 수업(키 없으면 종일 공강)
            for h in DAY_HOURS:
                if h not in classes:
                    grid[d][h] += 1

    by_day = {d: round(sum(grid[d].values()) / len(DAY_HOURS), 1) for d in WEEK}
    by_hour = {h: round(sum(grid[d][h] for d in WEEK) / len(WEEK), 1) for h in DAY_HOURS}
    return {"by_day": by_day, "by_hour": by_hour, "grid": grid, "n_students": n}


def intersect(timetables: list) -> dict:
    """여러 명의 공강을 교집합 — 목업 7페이지 '친구 시간표 겹쳐보기'"""
    if not timetables:
        return {}
    frees = [free_slots(t) for t in timetables]
    result = {}
    for day in ["월", "화", "수", "목", "금"]:
        common = set(frees[0].get(day, []))
        for f in frees[1:]:
            common &= set(f.get(day, []))
        if common:
            result[day] = sorted(common)
    return result


def _runs(hours: list) -> list:
    """[10,11,12,15,16] -> [(10,13),(15,17)] 처럼 연속 구간 [시작, 끝) 목록으로."""
    runs = []
    hours = sorted(hours)
    i = 0
    while i < len(hours):
        start = hours[i]
        while i + 1 < len(hours) and hours[i + 1] == hours[i] + 1:
            i += 1
        runs.append((start, hours[i] + 1))
        i += 1
    return runs


def to_blocks(slots: dict) -> list:
    """{요일: [빈 시각들]} -> '15~18시' 같은 연속 구간 목록."""
    blocks = []
    for day, hours in slots.items():
        for start, end in _runs(hours):
            blocks.append({"day": day, "start": start, "end": end,
                           "length": end - start})
    return [b for b in blocks if b["length"] >= 1]


def today_free_block(timetable: dict, now=None) -> dict | None:
    """
    오늘, 지금 이후로 남은 '가장 긴 연속 공강'을 찾는다 — 챗봇 자동 추천의 기준.
      반환: {"day","start","end","minutes"} 또는 None(주말/공강 없음)
    """
    from datetime import datetime
    now = now or datetime.now()
    if now.weekday() > 4:                       # 주말은 수업 개념 없음
        return None
    day = ["월", "화", "수", "목", "금"][now.weekday()]
    classes = set(timetable.get(day, []))

    # 지금 시각 이후(9~21시)에서 수업 없는 시각만
    cur = now.hour + (1 if now.minute > 30 else 0)   # 30분 넘었으면 다음 시각부터
    free_hours = [h for h in range(max(cur, 9), 22) if h not in classes]
    if not free_hours:
        return None

    runs = _runs(free_hours)
    start, end = max(runs, key=lambda r: r[1] - r[0])   # 가장 긴 연속 구간
    end = min(end, 21)                          # 활동 추천은 21시까지만 현실적
    if end <= start:
        return None
    # 지금이 그 구간 안이면 '남은 시간'은 지금부터 계산
    real_start_min = now.hour * 60 + now.minute
    begin = max(real_start_min, start * 60)
    minutes = end * 60 - begin
    if minutes < 20:                            # 20분 미만은 추천 의미 없음
        return None
    # 상한은 두되 넉넉히 — 공강이 길면 그만큼 더 많은 활동을 붙일 수 있어야 한다
    minutes = min(minutes, 720)
    return {"day": day, "start": start, "end": end, "minutes": minutes}


# ----------------------------------------------------- 거리·시간 필터
# 현재 위치 -> 도보시간 환산 계수.
# 회기동 실측 898곳(Valhalla 보행경로)으로 보정한 값:
#   실제 보행거리 / 직선거리 = 1.17,  보행속도 = 88 m/분
DETOUR, WALK_MPM = 1.17, 88.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 직선거리(m)."""
    import math
    R, p = 6371000.0, math.pi / 180
    dlat, dlng = (lat2 - lat1) * p, (lng2 - lng1) * p
    x = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def walk_min_from(lat: float, lng: float, store: dict) -> int | None:
    """현재 위치에서 가게까지 도보 분(추정). 좌표가 없으면 None."""
    if store.get("lat") is None or store.get("lng") is None:
        return None
    meters = haversine_m(lat, lng, store["lat"], store["lng"]) * DETOUR
    return max(1, round(meters / WALK_MPM))


# ---------------------------------------------- 소비 분산 스코어
# 회기동 추정매출 20분기 누적 기준 업종별 비중(%). 이 값이 클수록 이미 소비가 쏠린 곳.
# 신규성(novelty) 계산의 기준이 된다. (출처: 서울 상권분석 추정매출 2021Q1~2025Q4)
CATEGORY_SHARE = {
    "식사": 32.5,      # 한식24.7 + 중식2.6 + 일식2.6 + 양식2.6
    "가볍게": 32.6,    # 커피12.2 + 호프12.9 + 분식3.0 + 제과4.1 + 치킨0.4
    "의료": 16.0,      # 의약품
    "편의점": 7.5,     # 슈퍼마켓5.8 + 편의점1.7
    "미용실": 3.5,
    "가정": 1.7,       # 안경
    "의류": 1.2,
    "레저": 1.5,       # 노래방0.9 + PC방0.4 + 당구장0.2
    "화장품": 0.2,
    "꽃집": 0.4,
    "학원": 0.1,
    "실무": 0.3,
    "사진": 0.3,
    "숙박": 0.2,
    "부동산": 0.2,
    "반려동물": 0.1,
}
DEFAULT_SHARE = 1.0
NOVELTY_FLOOR, NOVELTY_CAP = 0.7, 2.2      # 신규성 가중 범위


def novelty(category: str) -> float:
    """
    신규성 — 이미 소비가 쏠린 업종은 낮게, 덜 알려진 업종은 높게.
    share 가 클수록 1보다 작아지고, 작을수록 커진다(상·하한으로 과보정 방지).
    """
    share = CATEGORY_SHARE.get(category, DEFAULT_SHARE)
    v = (5.0 / max(share, 0.1)) ** 0.35        # 완만한 역비례
    return max(NOVELTY_FLOOR, min(NOVELTY_CAP, v))


def congestion_penalty(store: dict) -> float:
    """혼잡할수록 감점. 붐빔(1.0) -> 0.6, 한산(0.0) -> 1.0"""
    return 1.0 - 0.4 * float(store.get("congestion", 0.5))


def timedeal_bonus(store: dict) -> float:
    """
    타임딜 보너스 — 사장님이 한산한 시간대에 등록한 프로모션이 있으면 가산.
    지금은 등록 필드가 없으므로, '한산한 가게'를 타임딜 후보로 보고 소폭 가산한다.
    (상인이 실제 타임딜을 등록하면 store['timedeal'] 로 대체)
    """
    if store.get("timedeal"):
        return 1.3
    return 1.1 if float(store.get("congestion", 0.5)) < 0.33 else 1.0


def diversity_score(store: dict, relevance: float = 1.0) -> float:
    """
    분산 추천 점수 = 관련성 x 신규성 x 혼잡도 페널티 x 타임딜 보너스

    관련성만으로 정렬하면 이미 쏠린 업종(식사·가볍게)이 계속 상위를 차지한다.
    신규성으로 덜 소비된 업종을 끌어올리되, 관련성이 0이면 전체가 0이라
    "엉뚱한 업종을 억지로 추천"하는 일은 생기지 않는다.
    """
    return (relevance
            * novelty(store.get("category", ""))
            * congestion_penalty(store)
            * timedeal_bonus(store))


def fits_in_time(store: dict, minutes: int) -> bool:
    """
    왕복 도보 + '최소 체류시간'이 남은 시간 안에 들어오는가.

    DWELL_MINUTES 는 '평균 체류'지 '최소 체류'가 아니다. 평균을 그대로 요구하면
    "20분 안에 커피"(왕복10+카페20=30) 처럼 충분히 가능한 요청이 전부 걸러진다.
    그래서 판정에는 절반(최소 10분)만 요구하고, 동선 계산에는 원래 평균을 쓴다.
    """
    if minutes is None:
        return True
    walk_round = store.get("walk_min", 5) * 2
    min_stay = max(10, round(dwell_for(store) * 0.5))
    return walk_round + min_stay <= minutes


# 공강에 그냥 들러볼 수 있는 업종.
#
# 분산 점수는 '희소할수록 높은 점수'라 그대로 두면 화장품(5곳)·부동산처럼
# 수가 적다는 이유만으로 상위에 온다. 공강 20분에 학원이나 부동산을 권할 수는
# 없다. 그래서 분산은 이 목록 안에서만 시킨다.
#
# 추천 경로(main.open_recommend)와 검증 실험(eval/ablation.py)이 같은 정의를
# 봐야 한다 — 실험이 배포된 동작과 다른 걸 재면 그 수치는 의미가 없다.
CHAINABLE_CATEGORIES = {"레저", "사진", "실무", "의류", "가볍게", "식사",
                        "편의점", "꽃집"}


PURPOSE_CATEGORIES = {
    "선물": ["꽃집", "사진", "실무"],
    "식사": ["식사"],                       # 한·중·일·양
    "카페": ["가볍게"],                      # 아래 detail 로 카페만
    "술": ["가볍게"],                        # 아래 detail 로 술·치킨만
    "인쇄": ["실무"],
    "스터디": ["실무"],                      # 스터디카페·서점
    "서점": ["실무"],
    "사진": ["사진"],
    "단체": ["식사", "가볍게"],
    "약국": ["의료"],
    "병원": ["의료"],
    "급한일": ["편의점"],                   # 편의점 — 약국은 별도 용도로 분리
    "생활": ["가정", "화장품"],            # 세탁·안경·통신·화장품 (의료는 약국/병원으로)
    "레저": ["레저"],
}

# 통합 업종(가볍게·실무 등) 안에서 category_detail 로 좁히는 세부 힌트.
# 힌트가 있으면 '업종 일치 + detail 일치'를 모두 만족해야 매칭.
PURPOSE_DETAIL = {
    "카페": ["커피", "카페", "음료", "제과", "베이커리", "빵", "차", "디저트", "주스", "아이스크림"],
    "술":   ["주점", "호프", "맥주", "포차", "치킨", "닭", "와인", "바"],
    "스터디": ["스터디", "독서실"],
    "서점": ["서점", "책"],
    "인쇄": ["복사", "출력", "인쇄", "명함", "간판"],
    "선물": ["문구", "팬시", "꽃", "화훼", "기념품", "사진", "네컷", "셀프"],
    "약국": ["약국", "약품"],
    "병원": ["병원", "의원", "치과", "한의원", "클리닉", "정형", "내과", "피부"],
}


# EXAONE이 enum(급한일·생활 등) 대신 흔히 뱉는 구체어 -> 통합 업종
PURPOSE_TO_CATEGORY = {
    "약국": "의료", "병원": "의료", "약": "의료", "의료": "의료",
    "통신": "가정", "휴대폰": "가정", "세탁": "가정", "안경": "가정", "가정": "가정",
    "오락": "레저", "스포츠": "레저", "노래방": "레저", "레저": "레저", "pc방": "레저",
    "서점": "실무", "문구": "실무", "인쇄": "실무", "프린트": "실무",
    "스터디카페": "실무", "독서실": "실무", "실무": "실무",
}


def match_purpose(store: dict, purpose: str) -> bool:
    if not purpose:
        return True
    # 모델이 복합 용도를 한 문자열로 주는 경우("카페|서점", "카페,서점") -> 하나라도 맞으면 통과
    if isinstance(purpose, str) and re.search(r"[|,/]", purpose):
        parts = [p.strip() for p in re.split(r"[|,/]", purpose) if p.strip()]
        return any(match_purpose(store, p) for p in parts)
    cats = PURPOSE_CATEGORIES.get(purpose)
    if cats is not None:
        if store.get("category") not in cats:
            return False
        hints = PURPOSE_DETAIL.get(purpose)
        if not hints:
            return True
        # 통합 업종 안에서 세부 업종으로 좁히기 (카페 검색에 치킨집 안 섞이게)
        det = store.get("category_detail", "")
        return any(h in det for h in hints)
    # enum 밖: 별칭으로 통합 업종에 매핑, 없으면 업종명 직접 매칭.
    # 모델이 enum을 못 지켜도 추천이 비지 않게 하는 안전장치.
    cat = store.get("category", "")
    target = PURPOSE_TO_CATEGORY.get(purpose)
    if target:
        return cat == target
    return purpose == cat or purpose in cat or cat in purpose


def filter_stores(stores: list, cond: dict) -> list:
    """조건에 맞는 가게만 추림 — AI 아님, 순수 비교 연산"""
    out = []
    for s in stores:
        if not fits_in_time(s, cond.get("minutes")):
            continue
        if not match_purpose(s, cond.get("purpose")):
            continue
        if cond.get("people", 1) > 1 and s.get("capacity", 0) < cond["people"]:
            continue
        out.append(s)
    return out


# 첫 활동을 마친 뒤 남는 시간을 채울 활동 흐름 (다양성 위주 순서).
# 박호연 학생 인용 "밥 먹고 카페 가면 끝" → 밥 다음은 카페부터, 시간 남으면 그 뒤로 확장.
#   (라벨, 해당 업종들, 둘러보기 소요분)  — 소요분은 정식 체류보다 짧게(잠깐 둘러보기)
# 남는 시간을 채울 이어가기 활동. (표시명, 용도, 둘러보는 시간(분))
#
# 예전에는 여기에 업종명을 직접 적었는데("카페", "서점", "문구", "공방", "오락"),
# 업종을 16개로 통합하면서 그 이름들이 데이터에서 사라졌다. 결과적으로 6개 활동
# 중 4개가 0곳이 되어 체이닝이 사진·의류 두 개로만 돌아가고 있었다.
# 그래서 업종명 대신 '용도'로 적고 match_purpose 에 판정을 맡긴다.
# match_purpose 는 통합 업종 + category_detail 을 함께 보므로,
# 같은 '가볍게' 안에서도 카페와 술집을 구분한다.
ACTIVITY_FLOW = [
    ("카페", "카페", 15),
    ("책 구경", "서점", 15),
    ("소품·문구", "인쇄", 12),
    ("인생네컷", "사진", 15),
    ("옷 구경", "의류", 15),
    ("오락", "레저", 35),
]
HOP_MIN = 4            # 근처 가게 간 이동으로 가정하는 도보(분)
MIN_SLOT = 12         # 활동 하나를 넣기 위한 최소 여유시간(이동+둘러보기)
# 이어가기 활동 개수는 남은 시간에 따라 늘어난다.
# 고정 3개로 두면 4시간이 비어도 3곳에서 멈춰, 공강이 길수록 다양해지지 않는다.
MIN_PER_ACTIVITY = 40      # 활동 하나에 대략 이만큼(이동+체류) 든다고 보고 개수를 잡는다
MAX_ACTIVITIES_CAP = len(ACTIVITY_FLOW)   # 준비된 활동 수까지     # ACTIVITY_FLOW 안에서 최대 몇 개까지


def max_activities(minutes: int | None) -> int:
    """남은 시간으로 이어가기 활동 개수를 정한다. 60분이면 1개, 4시간이면 5개."""
    if not minutes:
        return 1
    return max(1, min(MAX_ACTIVITIES_CAP, minutes // MIN_PER_ACTIVITY))


def build_plan(cond: dict, primary_stores: list, all_stores: list) -> dict:
    """
    첫 추천 가게 + 남는 시간 계산 + 남는 시간을 채우는 활동 '동선'을 만든다.
    시간이 넉넉하면 사용자가 요청하지 않아도 여러 활동을 순서대로 채워준다.
    전부 순수 계산이다. EXAONE 은 이 계산 결과를 문장으로 옮기기만 한다.

      남는시간 = 전체시간 - 첫가게까지_도보 - 첫활동_체류
      동선     = 남는시간이 다 찰 때까지, 겹치지 않는 다른 업종을 근처에서 하나씩 채움
    """
    if not primary_stores:
        return {"primary": None, "followups": [], "remaining": None}

    primary = primary_stores[0]
    minutes = cond.get("minutes")
    dwell = dwell_for(primary)
    plan = {
        "primary": primary, "primary_dwell": dwell,
        "minutes": minutes, "remaining": None, "followups": [],
    }
    if minutes is None:
        return plan

    remaining = minutes - primary.get("walk_min", 5) - dwell
    cap = max_activities(minutes)
    used_categories = {primary.get("category")}
    used_ids = {primary.get("id")}
    itinerary = []

    for label, purpose, browse in ACTIVITY_FLOW:
        if remaining < MIN_SLOT or len(itinerary) >= cap:
            break
        cost = HOP_MIN + browse
        if cost > remaining:
            continue                       # 이 활동은 시간이 안 맞음 → 다음 후보로
        cands = [s for s in all_stores
                 if match_purpose(s, purpose)
                 and s.get("category") not in used_categories
                 and s.get("id") not in used_ids]
        if not cands:
            continue
        cands.sort(key=lambda s: (s.get("congestion", 0.5), s.get("walk_min", 99)))
        pick = cands[0]
        itinerary.append({"label": label, "store": pick, "minutes": browse})
        used_categories.add(pick.get("category"))
        used_ids.add(pick.get("id"))
        remaining -= cost

    plan["remaining"] = remaining
    plan["followups"] = itinerary
    return plan


# ------------------------------------------------------------ 보정계수
# 방학 계수만 실측 근거 있음 (유동인구 -9.5% -> 1 + (-0.095) = 0.905)
VACATION_FACTOR = 0.91

# 시험기간·이벤트 δ 는 아직 근거 없음 → 파일럿 중 점주 리포트로 확정
DELTA = {
    "exam": 0.0,     # TODO: 파일럿 후 실측값으로 교체
    "event": 0.0,    # TODO: 파일럿 후 실측값으로 교체
    "normal": 0.0,
}


def correction_factor(target: date, calendar: dict) -> dict:
    """
    보정계수(t) = 1 + Σ(i=1..N) δ_i(t)
    N = 그 상권에 영향을 주는 주체 수 (회기동 = 대학 2개: 경희대·한국외대)
    여기에 방학 등 지역 전체 요인은 곱으로 별도 적용.
    """
    iso = target.isoformat()
    delta_sum = 0.0
    detail = []
    vacation_hits = 0

    # "_note" 같은 메타 키는 건너뛴다
    universities = {k: v for k, v in calendar.items()
                    if not k.startswith("_") and isinstance(v, dict)}

    for univ, sched in universities.items():
        state = "normal"
        for period in sched.get("exam", []):
            if period["start"] <= iso <= period["end"]:
                state = "exam"
        for period in sched.get("event", []):
            if period["start"] <= iso <= period["end"]:
                state = "event"
        for period in sched.get("vacation", []):
            if period["start"] <= iso <= period["end"]:
                vacation_hits += 1
        delta_sum += DELTA[state]
        detail.append({"university": univ, "state": state, "delta": DELTA[state]})

    factor = 1 + delta_sum
    # 모든 대학이 방학이면 지역 전체 요인으로 간주
    if universities and vacation_hits == len(universities):
        factor *= VACATION_FACTOR
        detail.append({"university": "전체", "state": "vacation",
                       "factor": VACATION_FACTOR, "source": "유동인구 실측 -9.5%"})

    return {"factor": round(factor, 3), "detail": detail}


def apply_correction(raw_score: float, factor: float) -> float:
    """최종 예측(t) = Chronos 원본 예측(t) × 보정계수(t)"""
    return round(min(1.0, raw_score * factor), 3)


# --------------------------------------------------- 캘리브레이션
# 점주가 말한 '한산/보통/붐빔'을 숫자로 환산
LEVEL_TO_SCORE = {"한산": 0.25, "보통": 0.5, "붐빔": 0.8}

# 지수평활 가중치 — 새 관측치를 얼마나 반영할지
# 초반엔 크게(빨리 배움), 데이터가 쌓이면 작게(노이즈에 덜 흔들림)
def smoothing_alpha(n_observations: int) -> float:
    return 0.5 if n_observations < 10 else 0.3 if n_observations < 30 else 0.2


def calibrate(reports: list, predictions: dict, current: dict | None = None) -> dict:
    """
    점주 실측 vs 예측을 비교해 보정계수를 갱신한다.
    모델을 재학습하는 게 아니라 계수만 조정하는 것 (캘리브레이션).

      관측된_배수 = 실측값 / 예측값
      새_계수 = α × 관측배수평균 + (1-α) × 기존계수
    """
    current = current or {}
    if not reports:
        return {"factor": current.get("factor", 1.0), "n": 0,
                "status": "실측 데이터 없음 — 기본값 사용"}

    ratios = []
    for r in reports:
        actual = LEVEL_TO_SCORE.get(r.get("level"), 0.5)
        predicted = predictions.get(r.get("date"))
        if predicted and predicted > 0.05:
            ratios.append(actual / predicted)

    if not ratios:
        return {"factor": current.get("factor", 1.0), "n": 0,
                "status": "비교 가능한 예측값 없음"}

    observed = sum(ratios) / len(ratios)
    alpha = smoothing_alpha(len(ratios))
    prev = current.get("factor", 1.0)
    updated = alpha * observed + (1 - alpha) * prev

    return {
        "factor": round(updated, 3),
        "observed_ratio": round(observed, 3),
        "previous": round(prev, 3),
        "alpha": alpha,
        "n": len(ratios),
        "status": f"실측 {len(ratios)}건으로 갱신 (α={alpha})",
    }


# --------------------------------------------------- 후기 분류 (규칙 기반)
# 카테고리 분류는 키워드 매칭으로 충분한 일이라 AI를 쓰지 않는다.
# EXAONE은 그 다음 단계(요약·제안 문장 생성)에서만 필요하다.
REVIEW_RULES = {
    "카드": "결제수단", "결제": "결제수단", "현금": "결제수단",
    "대기": "대기시간", "줄": "대기시간", "오래": "대기시간",
    "메뉴": "메뉴", "맛": "메뉴", "자리": "좌석", "좌석": "좌석",
}


def classify_review_category(text: str) -> str:
    """단건 후기를 카테고리로 분류 — 챗봇 즉석 응답과 상인 리포트가 공유하는 규칙."""
    return next((v for k, v in REVIEW_RULES.items() if k in text), "기타")


def trend_sentence(trend: dict) -> str:
    """
    사장님 화면에 나갈 문장.

    Chronos 예측은 그래프(밝은 막대)로 계속 보여준다 — 기획된 기능이고,
    흐름을 가늠하는 참고값으로서의 쓸모는 있다.
    다만 검증에서 방향 정확도가 50%였으므로 텍스트로 '증가/감소'를 단정하지 않는다.
    문장에는 검증이 필요 없는 '실측 사실'만 담는다(작년 동분기 대비).
    오차·MAPE 같은 검증 수치는 사장님 화면이 아니라 검증 보고서에 둔다.
    """
    if not trend.get("available"):
        return "매출 추이를 계산할 데이터가 부족합니다."

    hist = trend.get("history") or []
    parts = []
    if len(hist) >= 5 and hist[-5]:
        yoy = (hist[-1] - hist[-5]) / hist[-5] * 100
        move = "늘었" if yoy > 0 else "줄었"
        parts.append(f"이 업종 매출은 작년 같은 분기 대비 {abs(yoy):.1f}% {move}습니다")
    if len(hist) >= 4:
        recent4 = hist[-4:]
        hi, lo = max(recent4), min(recent4)
        if lo:
            parts.append(f"최근 4분기는 분기별로 {(hi - lo) / lo * 100:.0f}%까지 오르내렸습니다")

    base = ". ".join(parts) + "." if parts else "과거 매출 추이는 아래 그래프를 참고하세요."
    base += "\n\n아래 밝은 막대는 AI(Chronos-Bolt)가 그린 예상 구간입니다. 방향을 가늠하는 참고용으로만 봐주세요."
    borrowed = trend.get("borrowed_from")
    if borrowed:
        base += f" 이 업종은 데이터가 짧아 유사 업종 '{borrowed}' 추이를 참고했습니다."
    return base


def population_sales_sentence(pop: dict, link: dict, trend: dict) -> str:
    """
    '사람 수(생활인구)'와 '실제 소비(매출)'를 이어 하나의 문장으로.
      - 생활인구 추이(월별)로 회기동에 사람이 늘지/줄지
      - 상관이 확인될 때만 '함께 움직인다'고 말한다

    방향이 엇갈리는 경우에는 생활인구 추이만 말하고 끝낸다. 두 지표가 다르게
    움직인다는 사실만으로는 원인을 알 수 없기 때문이다(업종 구성 변화, 계절성,
    표본 차이 등 다른 설명이 많다). 확인 안 된 진단은 내지 않는다.
    """
    if not pop.get("available") and not link.get("available"):
        return ""
    parts = []
    if pop.get("available"):
        pd, pp = pop["direction"], abs(pop["change_pct"])
        move = {"증가": "늘고", "감소": "줄고", "보합": "비슷하고"}[pd]
        parts.append(f"회기동에 머무는 생활인구는 최근 {pp}% 수준으로 {move} 있습니다")
    if link.get("available"):
        corr = link["correlation"]
        rel = "강하게" if corr >= 0.7 else ("어느 정도" if corr >= 0.4 else "약하게")
        # 방향이 엇갈릴 때는 아무 말도 하지 않는다.
        # 인구와 매출의 방향이 다르다는 사실만으로 '소비 전환이 약해졌다'고
        # 진단할 수는 없다(업종 구성 변화, 계절성, 표본 차이 등 다른 설명이 많다).
        # 검증되지 않은 진단을 사장님이 믿고 움직이면 손해가 되므로, 확인된
        # 상관이 있을 때만 그 사실을 말한다.
        if not link.get("diverging"):
            parts.append(
                f"생활인구와 매출은 {rel} 함께 움직이며(상관 {corr}), "
                f"사람이 늘면 매출도 따라 오르는 구조입니다")
    return ". ".join(parts) + "."
