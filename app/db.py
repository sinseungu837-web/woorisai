# -*- coding: utf-8 -*-
"""
데이터 레이어 — 지금은 JSON 파일 기반 간이 DB.
실서비스 전환 시 이 모듈의 함수 시그니처만 유지하고 내부를 SQLite/Postgres로 교체하면 된다.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read(name: str):
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        return [] if name != "academic_calendar" else {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(name: str, payload):
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------- 점포
def get_stores() -> list:
    return _read("stores")


def get_store(store_id: str) -> dict | None:
    return next((s for s in get_stores() if s["id"] == store_id), None)


def add_store(store: dict):
    stores = get_stores()
    stores.append(store)
    _write("stores", stores)


# ----------------------------------------------------------- 사용자
def get_users() -> list:
    return _read("users")


def get_student_timetables() -> list:
    """집계용 학생 시간표 풀 (합성 120명 + 실제 등록 학생).
    named user(me/친구)는 데모용이라, 분포 통계는 이 풀 + 실제 시간표를 합쳐 쓴다."""
    pool = _read("student_timetables")          # [{요일: [시각]}, ...]
    real = [u["timetable"] for u in get_users() if u.get("timetable")]
    return pool + real


def get_user(user_id: str) -> dict | None:
    return next((u for u in get_users() if u["id"] == user_id), None)


def save_timetable(user_id: str, name: str, timetable: dict,
                   major: str | None = None, campus: str | None = None):
    users = get_users()
    user = next((u for u in users if u["id"] == user_id), None)
    if user:
        user["timetable"] = timetable
        user["name"] = name or user.get("name")
        if major is not None:
            user["major"] = major
        if campus is not None:
            user["campus"] = campus
    else:
        users.append({"id": user_id, "name": name or user_id,
                      "timetable": timetable, "major": major or "",
                      "campus": campus or "", "friends": []})
    _write("users", users)


def set_profile(user_id: str, major: str, interests: str = ""):
    users = get_users()
    user = next((u for u in users if u["id"] == user_id), None)
    if user:
        user["major"] = major
        user["interests"] = interests
        _write("users", users)


# --------------------------------------------------------- 학사일정
def get_calendar() -> dict:
    return _read("academic_calendar")


# ------------------------------------------------------------- 후기
def get_reviews(store_id: str | None = None) -> list:
    reviews = _read("reviews")
    return [r for r in reviews if r["store_id"] == store_id] if store_id else reviews


def add_review(store_id: str, text: str):
    # 날짜를 같이 남긴다 — 키워드 '트렌드'(신규/급상승/지속)는 후기를 시간축으로
    # 갈라서 판정하므로, 날짜가 없으면 흐름을 볼 수 없다.
    from datetime import date as _d
    reviews = _read("reviews")
    reviews.append({"store_id": store_id, "text": text,
                    "date": _d.today().isoformat()})
    _write("reviews", reviews)


# ----------------------------------------------- 점주 일일 보고 (실측)
def get_daily_reports(store_id: str | None = None) -> list:
    reports = _read("daily_reports")
    return [r for r in reports if r["store_id"] == store_id] if store_id else reports


def add_daily_report(store_id: str, when: str, parsed: dict, raw_text: str):
    reports = _read("daily_reports")
    reports.append({"store_id": store_id, "date": when,
                    "raw": raw_text, **parsed})
    _write("daily_reports", reports)


def get_calibration() -> dict:
    """캘리브레이션된 보정계수 (점주 실측으로 갱신되는 값)"""
    return _read("calibration") or {}


def save_calibration(payload: dict):
    _write("calibration", payload)


# --------------------------------------------------------- 월간 설문
def get_survey_responses() -> list:
    return _read("survey_responses")


def add_survey_response(text: str, when: str):
    responses = _read("survey_responses")
    responses.append({"text": text, "date": when})
    _write("survey_responses", responses)


# ------------------------------------------------------------- 과제
def get_projects() -> list:
    return _read("projects")


def add_project(project: dict):
    projects = get_projects()
    projects.append(project)
    _write("projects", projects)
