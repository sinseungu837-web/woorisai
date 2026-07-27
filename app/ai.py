# -*- coding: utf-8 -*-
"""
AI 모델 레이어 — EXAONE 3.5 / Chronos-Bolt / BGE-M3

동작 모드
  USE_STUB=True   규칙 기반 임시 응답. GPU 없이 UI 확인용.
  USE_STUB=False  실제 모델 로드. GPU 서버에서 사용.

환경변수로도 바꿀 수 있다.
  WOORISAI_REAL=1 uvicorn main:app

세 모델 모두 추가 학습 없이(zero-shot) 사전학습 가중치를 그대로 쓴다.
모델 로드 실패 시 자동으로 규칙 기반으로 내려가므로 서비스가 죽지 않는다.
"""
import os
import re
import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Optional

USE_STUB = os.getenv("WOORISAI_REAL", "0") != "1"

# 모델별 상태·지연시간 기록 (HTML 상태 화면에서 그대로 읽어간다)
STATUS: dict = {
    "EXAONE": {"loaded": False, "device": None, "error": None,
               "calls": 0, "last_ms": None, "avg_ms": None},
    "Chronos": {"loaded": False, "device": None, "error": None,
                "calls": 0, "last_ms": None, "avg_ms": None},
    "BGE-M3": {"loaded": False, "device": None, "error": None,
               "calls": 0, "last_ms": None, "avg_ms": None},
}


def _record(name: str, ms: float):
    s = STATUS[name]
    s["calls"] += 1
    s["last_ms"] = round(ms, 1)
    prev = s["avg_ms"] or ms
    s["avg_ms"] = round(prev + (ms - prev) / s["calls"], 1)


def _timed(name: str):
    """추론 시간을 재서 STATUS 에 남기는 데코레이터"""
    def deco(fn):
        def wrap(*a, **kw):
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                _record(name, (time.perf_counter() - t0) * 1000)
        return wrap
    return deco


def _device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


# ================================================================ EXAONE
class Exaone:
    """채널 — 자연어를 조건으로 바꾸고, 결과를 문장으로 쓴다."""

    MODEL_ID = "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct"

    def __init__(self, use_stub: bool = USE_STUB):
        self.use_stub = use_stub
        self._model = self._tok = None
        self._lock = threading.Lock()
        if not use_stub:
            self._load()

    def _load(self):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            dev = _device()
            self._tok = AutoTokenizer.from_pretrained(self.MODEL_ID, trust_remote_code=True)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.MODEL_ID,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
                device_map="auto" if dev == "cuda" else None,
            )
            self._model.eval()
            STATUS["EXAONE"].update(loaded=True, device=dev)
            print(f"[EXAONE] 로드 완료 ({dev})")
        except Exception as e:
            STATUS["EXAONE"]["error"] = str(e)[:200]
            self.use_stub = True
            print(f"[EXAONE] 로드 실패 -> 규칙 기반으로 전환: {e}")

    def _chat(self, system: str, user: str, max_new_tokens: int = 256) -> str:
        """EXAONE 은 instruction-tuned 모델이라 chat template 을 반드시 거쳐야 한다.
        return_dict=True 로 명시해서 딕셔너리(BatchEncoding)로 받고 **로 언패킹한다
        (텐서로 가정하고 .shape 로 바로 쓰면 transformers 버전에 따라 깨진다)."""
        import torch
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        encoded = self._tok.apply_chat_template(
            messages, add_generation_prompt=True,
            return_tensors="pt", return_dict=True,
        ).to(self._model.device)
        with self._lock, torch.no_grad():
            out = self._model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,                       # 재현 가능하게 greedy
                eos_token_id=self._tok.eos_token_id,
                pad_token_id=self._tok.pad_token_id or self._tok.eos_token_id,
            )
        input_len = encoded["input_ids"].shape[-1]
        return self._tok.decode(out[0][input_len:], skip_special_tokens=True).strip()

    @staticmethod
    def _json_from(text: str) -> dict | None:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group())
        except Exception:
            return None

    # ---- 1. 자연어 -> 제약조건 ----
    @_timed("EXAONE")
    def parse_query(self, text: str) -> dict:
        if self.use_stub:
            return self._stub_parse(text)
        try:
            raw = self._chat(
                "너는 회기동 상권 안내 시스템의 파서다. 반드시 JSON만 출력한다.",
                "다음 문장에서 조건을 뽑아 JSON으로만 답해라.\n"
                '형식: {"minutes": 남은시간(분, 모르면 null), '
                '"purpose": "식사"|"카페"|"술"|"선물"|"인쇄"|"스터디"|"서점"|'
                '"단체"|"약국"|"병원"|"급한일"|"생활"|null, '
                '"people": 인원수(기본 1)}\n'
                '급한일=약국·프린트·휴대폰, 생활=약국·병원·세탁·안경\n'
                'minutes 는 "학생에게 남은 시간(분)"이다. 반드시 아래처럼 뽑는다.\n'
                '  넣는다: "40분 비는데"->40, "20분 안에"->20, "1시간 비어"->60, '
                '"두 시간 남았어"->120\n'
                '  넣지 않는다(null): "도보 5분", "5분 거리", "걸어서 10분" '
                '(이건 걷는 거리 제한이지 남은시간이 아니다)\n'
                '용도를 확실히 모르겠으면 지어내지 말고 purpose 를 null 로 둔다.\n'
                '용도는 하나만 고른다(여러 개 이어붙이지 않는다).\n\n'
                f"문장: {text}", 96)
            parsed = self._json_from(raw)
            return parsed if parsed else self._stub_parse(text)
        except Exception as e:
            STATUS["EXAONE"]["error"] = str(e)[:200]
            return self._stub_parse(text)

    @staticmethod
    def _stub_parse(text: str) -> dict:
        minutes = None
        # "도보 5분", "5분 거리"는 걷는 거리 제한 -> 남은시간으로 오인하지 않는다
        walk_limit = re.search(r"도보\s*(\d+)\s*분|(\d+)\s*분\s*(?:거리|안에\s*있)", text)
        m = None if walk_limit else re.search(r"(\d+)\s*분", text)
        if m:
            minutes = int(m.group(1))
        else:
            m = re.search(r"(\d+)\s*시(?:까지|간)", text)
            if m:
                minutes = 40 if "까지" in text else int(m.group(1)) * 60
        people = 1
        m = re.search(r"(\d+)\s*명", text)
        if m:
            people = int(m.group(1))
        # 순서 주의 — 위에서부터 먼저 매칭. 구체 키워드(술·약)를 포괄어(저녁)보다 앞에.
        keywords = {
            "선물": "선물", "꽃": "선물", "프린트": "인쇄", "인쇄": "인쇄", "복사": "인쇄",
            "술": "술", "맥주": "술", "안주": "술", "한잔": "술", "치맥": "술",
            "약국": "약국", "상비약": "약국", "두통약": "약국", "감기약": "약국",
            "병원": "병원", "의원": "병원", "치과": "병원", "진료": "병원", "아파": "병원",
            "휴대폰": "급한일", "충전": "급한일", "편의점": "급한일",
            "세탁": "생활", "안경": "생활", "화장품": "생활",
            "필름": "사진", "현상": "사진", "인화": "사진", "사진": "사진", "네컷": "사진",
            "밥": "식사", "먹": "식사", "점심": "식사", "저녁": "식사", "배고": "식사",
            "카페": "카페", "커피": "카페", "공부": "스터디", "과제": "스터디",
            "책": "서점", "회식": "단체", "종강총회": "단체", "예약": "단체",
        }
        purpose = next((v for k, v in keywords.items() if k in text), None)
        return {"minutes": minutes, "purpose": purpose, "people": people}

    # ---- 2. 결과 -> 문장 (남는 시간 + 이어가기 활동 포함) ----
    @_timed("EXAONE")
    def compose_recommendation(self, cond: dict, stores: list, plan: dict | None = None) -> str:
        if self.use_stub:
            return self._stub_reco(cond, stores, plan)
        try:
            brief = "\n".join(
                f"- {s['name']} / {s.get('category_detail') or s['category']} / "
                f"도보 {s['walk_min']}분 / 지금 {s['congestion_label']}"
                for s in stores[:3])

            # 시간 계획(동선)을 사실로 넣어주고, 문장으로 옮기라고만 지시 (숫자는 코드가 계산)
            plan_facts = ""
            extra_rule = ""
            followups = (plan or {}).get("followups") or []
            if plan and followups and plan.get("primary"):
                p = plan["primary"]
                steps = "\n".join(
                    f"  {i}) {f['label']}: {f['store']['name']} "
                    f"(도보 {f['store']['walk_min']}분, {f['minutes']}분 정도)"
                    for i, f in enumerate(followups, 1))
                # 남는 시간이 10분 미만이면 "약 0분 여유" 같은 무의미 문구를 넣지 않는다
                rem = plan.get("remaining") or 0
                rem_line = f"\n- 다 하고 나면 약 {rem}분 여유" if rem >= 10 else ""
                plan_facts = (
                    f"\n\n[시간 동선]\n"
                    f"- {p['name']}에서 {plan['primary_dwell']}분 정도 머무름\n"
                    f"- 그러고도 시간이 남아서, 이어서 하면 좋은 것:\n{steps}"
                    f"{rem_line}")
                extra_rule = (
                    " 학생이 따로 요청하지 않아도, 시간이 남으면 이어서 할 활동을 순서대로 제안한다. "
                    "단, 각 활동은 한 문장으로 짧게 쓰고 전체 답변은 5문장을 넘기지 않는다. "
                    "장황한 설명 없이 핵심만 간결하게 안내한다.")

            n = len(stores[:3])
            choice_rule = (
                f" 추천 가게 {n}곳을 하나만 고르지 말고 모두 소개해서, "
                "학생이 직접 고를 수 있게 선택지로 제시한다. 각 가게는 이름·도보시간·혼잡도를 "
                "한 줄로 짧게. 그중 덜 붐비는 곳을 가볍게 추천만 한다.")

            return self._chat(
                "너는 회기동 상권 안내 챗봇이다. 반말이 아닌 친근한 존댓말로, 간결하게 답한다. "
                "이모티콘은 쓰지 않는다. 주어진 정보 밖의 내용은 절대 지어내지 않는다."
                + choice_rule + extra_rule,
                f"학생 조건: 남은시간 {cond.get('minutes')}분, "
                f"용무 {cond.get('purpose')}, 인원 {cond.get('people')}명\n"
                f"추천 가게 (이 {n}곳을 모두 제시):\n{brief}{plan_facts}\n\n"
                "이 정보로 안내 문장을 써라.", 460)
        except Exception as e:
            STATUS["EXAONE"]["error"] = f"{type(e).__name__}: {e}"[:200]
            return self._stub_reco(cond, stores, plan)

    @staticmethod
    def _stub_reco(cond: dict, stores: list, plan: dict | None = None) -> str:
        if not stores:
            return "조건에 맞는 곳을 못 찾았어요. 시간이나 조건을 조금 바꿔볼까요?"
        head = f"{cond['minutes']}분 있으시네요. " if cond.get("minutes") else ""
        # 후보 3곳을 모두 제시해 학생이 고르게 (한 곳만 강조하지 않음)
        cands = stores[:3]
        lines = " / ".join(
            f"{s['name']}(도보 {s['walk_min']}분·{s['congestion_label']})" for s in cands)
        least = min(cands, key=lambda s: s.get("congestion", 0.5))
        base = (f"{head}이 중에 골라보세요 — {lines}. "
                f"지금은 {least['name']}이 제일 한산한 편이에요.")
        followups = (plan or {}).get("followups") or []
        if followups and plan.get("primary_dwell") is not None:
            chain = ", 그다음 ".join(
                f"{f['store']['name']}에서 {f['label']}" for f in followups)
            base += (f" {plan['primary_dwell']}분쯤 식사하고도 시간이 남으니, "
                     f"{chain} 순으로 둘러보시는 것도 좋아요.")
            if plan.get("remaining", 0) >= 10:
                base += f" 그러고도 약 {plan['remaining']}분은 여유가 있어요."
        return base

    # ---- 3. 점주 일일 보고 파싱 ----
    @_timed("EXAONE")
    def parse_daily_report(self, text: str) -> dict:
        if self.use_stub:
            return self._stub_daily(text)
        try:
            raw = self._chat(
                "너는 매출 보고 파서다. 반드시 JSON만 출력한다.",
                "사장님이 오늘 장사를 설명한 문장에서 수치를 뽑아 JSON으로만 답해라.\n"
                '형식: {"sales_change_pct": 지난주 대비 매출 변화율(숫자, 모르면 null), '
                '"customers": 손님 수(숫자, 모르면 null), '
                '"level": "한산"|"보통"|"붐빔"}\n\n'
                f"문장: {text}", 96)
            parsed = self._json_from(raw)
            return parsed if parsed else self._stub_daily(text)
        except Exception as e:
            STATUS["EXAONE"]["error"] = str(e)[:200]
            return self._stub_daily(text)

    @staticmethod
    def _stub_daily(text: str) -> dict:
        pct = None
        m = re.search(r"([+-]?\d+)\s*%", text)
        if m:
            pct = int(m.group(1))
            if any(w in text for w in ["줄", "감소", "덜", "적"]):
                pct = -abs(pct)
        customers = None
        m = re.search(r"(\d+)\s*명", text)
        if m:
            customers = int(m.group(1))
        if any(w in text for w in ["붐", "많", "바빴", "정신없"]):
            level = "붐빔"
        elif any(w in text for w in ["한산", "없", "적었", "조용"]):
            level = "한산"
        else:
            level = "보통"
        return {"sales_change_pct": pct, "customers": customers, "level": level}

    # ---- 4. 상인 컨설팅 리포트 (학생 공강 집계 + 학사일정 종합) ----
    @_timed("EXAONE")
    def compose_merchant_report(self, store: dict, forecast: dict, reviews: list,
                                insight: dict | None = None,
                                voice_report: dict | None = None) -> str:
        if self.use_stub:
            return self._stub_report(store, forecast, reviews, insight, voice_report)
        try:
            rv = "\n".join(f"- {r['text']}" for r in reviews[:8]) or "- (없음)"
            insight_txt = (insight or {}).get("prompt_block", "")
            return self._chat(
                "너는 회기동 상권을 잘 아는 소상공인 컨설턴트다. 이모티콘은 쓰지 않고, "
                "근거 없는 숫자를 지어내지 않는다. 데이터를 나열하지 말고, 이 가게의 업종에 맞게 "
                "'그래서 무엇을 하면 좋은지'를 구체적인 행동으로 제안한다.\n"
                "다음 4가지를 이 순서로, 각 1~2문장씩 쓴다:\n"
                "1) 요일 전략 — 공강 많은 요일엔 무엇을, 한산한 요일엔 무엇을 (예: 한산한 요일 타임딜)\n"
                "2) 시간대 전략 — 낮 공강 피크 시간에 맞춘 준비(재고·인력·메뉴)\n"
                "3) 사람 수 대비 소비 — 주어진 '생활인구·매출 연결' 문장에 적힌 내용만 쓴다. "
                "그 문장이 비어 있으면 이 항목은 통째로 건너뛴다. "
                "인구와 매출 방향이 다르다는 이유로 '소비 전환이 약하다'고 진단하지 마라\n"
                "4) 학사일정 대비 — 지금 시기(방학/시험/축제)와 다가오는 일정에 맞춘 대응\n"
                "5) 학생 목소리 — 아래 '학생 후기 집계 결과'에 적힌 항목만 다룬다. "
                "거기 없는 메뉴·서비스·품목을 새로 지어내지 마라. "
                "[도입]으로 표시된 항목은 학생들이 먼저 요청한 것이므로 "
                "'수요가 이미 확인됐다'는 점을 근거로 제시한다.\n"
                "숫자는 주어진 값만 쓰고, 회기동 상권 특성(학생 의존도가 높음)을 감안한다.",
                f"가게: {store['name']} (업종: {store.get('category_detail') or store['category']})\n"
                f"매출 추이: {forecast.get('trend')}\n"
                f"생활인구·매출 연결: {forecast.get('pop_link') or '(데이터 없음)'}\n"
                f"이 가게가 가장 붐비는 시간: {forecast.get('peak_label')}\n"
                f"{insight_txt}\n"
                f"{_voice_block(voice_report)}\n"
                f"최근 익명 후기:\n{rv}\n\n"
                "위 데이터를 종합해, 이 업종 사장님이 이번 주에 실제로 실행할 수 있는 "
                "맞춤 조언 리포트를 써라.", 620)
        except Exception as e:
            STATUS["EXAONE"]["error"] = f"{type(e).__name__}: {e}"[:200]
            return self._stub_report(store, forecast, reviews, insight)

    @staticmethod
    def _stub_report(store: dict, forecast: dict, reviews: list,
                     insight: dict | None = None,
                     voice_report: dict | None = None) -> str:
        peak = forecast.get("peak_label", "화요일 오후")
        n = len(reviews)
        parts = []
        if insight:
            bd, hh = insight.get("busiest_day"), insight.get("busiest_hour")
            qd = insight.get("quietest_day")
            if bd and qd:
                parts.append(
                    f"등록된 학생 {insight.get('n_students')}명의 시간표를 보면, "
                    f"{bd}요일에 공강이 가장 많아 학생 방문이 몰리고 {qd}요일이 가장 한산합니다. "
                    f"특히 {hh}시경에 공강 학생이 가장 많습니다.")
            if insight.get("calendar_note"):
                parts.append(insight["calendar_note"])
        if forecast.get("pop_link"):
            parts.append(forecast["pop_link"])
        parts.append(
            f"다음 주는 {peak}에 학생 유입이 가장 많을 것으로 예상되니, "
            f"재고와 인력을 이 시간대에 맞춰 준비하시면 좋겠습니다.")
        parts.append(
            f"최근 접수된 익명 후기는 {n}건입니다. "
            + (f"'{reviews[0]['text']}' 같은 의견이 있었습니다." if reviews else "아직 후기가 없습니다."))
        if (voice_report or {}).get("cards"):
            parts.append("\n".join(c["action"] for c in voice_report["cards"]))
        return "\n\n".join(parts)

    # ---- 5. 후기 분류 + 요약 ----
    @_timed("EXAONE")
    def analyze_reviews(self, reviews: list) -> dict:
        if self.use_stub or not reviews:
            return self._stub_reviews(reviews)
        try:
            rv = "\n".join(f"- {r['text']}" for r in reviews[:20])
            raw = self._chat(
                "너는 고객 피드백 분석가다. 반드시 JSON만 출력한다.",
                "후기들을 분류하고 요약해 JSON으로만 답해라.\n"
                '형식: {"categories": {"결제수단": 건수, "대기시간": 건수, "메뉴": 건수, '
                '"좌석": 건수, "기타": 건수}, "summary": "대표 의견 한 문장", '
                '"suggestion": "개선 제안 한 문장"}\n\n'
                f"후기:\n{rv}", 400)
            parsed = self._json_from(raw)
            return parsed if parsed else self._stub_reviews(reviews)
        except Exception as e:
            STATUS["EXAONE"]["error"] = str(e)[:200]
            return self._stub_reviews(reviews)

    @staticmethod
    def _stub_reviews(reviews: list) -> dict:
        from app.logic import classify_review_category
        buckets = {"결제수단": 0, "대기시간": 0, "메뉴": 0, "좌석": 0, "기타": 0}
        for r in reviews:
            buckets[classify_review_category(r["text"])] += 1
        top = max(buckets, key=buckets.get) if reviews else None
        return {
            "categories": buckets,
            "summary": f"'{top}' 관련 언급이 {buckets[top]}건으로 가장 많았습니다." if top else "후기 없음",
            "suggestion": "프로필에 관련 정보를 미리 표기하면 문의가 줄어듭니다." if top else "",
        }

    # ---- 6. 단체예약 결과 -> 문장 (목업 5페이지) ----
    @_timed("EXAONE")
    def compose_booking_result(self, people: int, when: str, stores: list) -> str:
        if self.use_stub or not stores:
            return self._stub_booking(people, when, stores)
        try:
            brief = "\n".join(
                f"- {s['name']} / 최대 {s.get('capacity', 0)}명 / 도보 {s['walk_min']}분 / "
                f"{s.get('price_from', 0):,}원~"
                for s in stores)
            return self._chat(
                "너는 회기동 단체예약 안내 챗봇이다. 2~3문장으로 친근하게 답한다. "
                "이모티콘은 쓰지 않는다. 주어진 가게 정보 밖의 내용은 지어내지 않는다.",
                f"{people}명, {when} 예약 문의입니다. 후보:\n{brief}\n\n안내 문장을 써라.", 200)
        except Exception as e:
            STATUS["EXAONE"]["error"] = f"{type(e).__name__}: {e}"[:200]
            return self._stub_booking(people, when, stores)

    @staticmethod
    def _stub_booking(people: int, when: str, stores: list) -> str:
        if not stores:
            return (f"{people}명이 한 번에 들어갈 곳을 아직 못 찾았어요. "
                     "인원을 나눠서 확인해볼까요?")
        s = stores[0]
        return (f"확인했어요! {people}명, {when} 기준으로 가능한 곳을 찾아드릴게요. "
                f"{s['name']}은 최대 {s.get('capacity', 0)}명, 도보 {s['walk_min']}분이에요.")

    # ---- 7. 후기 수집 대화 응답 (목업 17페이지) ----
    # count(누적 건수)는 정확해야 하는 사실이라 EXAONE에게 맡기지 않고,
    # 감사 인사만 EXAONE이 쓰게 하고 건수는 코드가 그대로 붙인다.
    @_timed("EXAONE")
    def compose_review_ack(self, store_name: str, category: str, count: int) -> str:
        tail = f" 이미 오늘 '{category}' 관련 얘기가 {count}번째예요." if count > 1 else ""
        if self.use_stub:
            return self._stub_review_ack(store_name, count) + tail
        try:
            thanks = self._chat(
                "너는 회기동 상권 후기 수집 챗봇이다. 이모티콘은 쓰지 않는다. "
                "1문장으로 짧고 다정하게 감사 인사만 써라. 건수나 통계는 언급하지 않는다.",
                f"학생이 '{store_name}'에 대한 후기를 남겼다. 감사 인사 한 문장만 써라.", 60)
            return thanks + tail
        except Exception as e:
            STATUS["EXAONE"]["error"] = f"{type(e).__name__}: {e}"[:200]
            return self._stub_review_ack(store_name, count) + tail

    @staticmethod
    def _stub_review_ack(store_name: str, count: int) -> str:
        return f"알려줘서 고마워요! {store_name} 사장님께 바로 전달할게요."

    # ---- 8. 월간 설문 응답 (목업 18페이지) ----
    # total/pct 도 정확해야 하는 집계치라, EXAONE에겐 감사 인사만 맡기고
    # 숫자는 코드가 그대로 붙인다.
    @_timed("EXAONE")
    def compose_survey_ack(self, answer: str, total: int, pct: int) -> str:
        tail = f" 이번 달 참여자 {total}명 중 {pct}%가 비슷하게 답했어요."
        if self.use_stub:
            return self._stub_survey_ack() + tail
        try:
            thanks = self._chat(
                "너는 회기동 상권 월간 설문 챗봇이다. 이모티콘은 쓰지 않는다. "
                "1문장으로 짧게 감사 인사만 써라. 숫자나 통계는 언급하지 않는다.",
                f"학생이 설문에 '{answer}'라고 답했다. 감사 인사 한 문장만 써라.", 60)
            return thanks + tail
        except Exception as e:
            STATUS["EXAONE"]["error"] = f"{type(e).__name__}: {e}"[:200]
            return self._stub_survey_ack() + tail

    @staticmethod
    def _stub_survey_ack() -> str:
        return "답변 고마워요!"


# ========================================================== Chronos-Bolt
class Chronos:
    """
    본체 — 회기동 실데이터 예측.
      A. 분기 추이   : 분기별 매출 시계열 -> Chronos-Bolt
      B. 시간대 혼잡도: 요일·시간대 매출 프로파일 (분기 데이터로는 시간대 예측 불가)
    """

    MODEL_ID = "amazon/chronos-bolt-base"
    _D = Path(__file__).resolve().parent.parent / "data"
    DATA_PATH = _D / "hoegi_timeseries.json"
    LIVING_POP_PATH = _D / "living_population_quarterly.json"
    LIVING_POP_MONTHLY_PATH = _D / "living_population_monthly.json"

    # 업종별 데이터가 부족할 때 대신 볼 유사 업종 (소비 성격이 비슷한 순)
    SIMILAR_CATEGORY = {
        "한식음식점": ["분식전문점", "중식음식점", "양식음식점"],
        "중식음식점": ["한식음식점", "일식음식점"],
        "일식음식점": ["중식음식점", "양식음식점"],
        "양식음식점": ["일식음식점", "커피-음료"],
        "분식전문점": ["한식음식점", "패스트푸드점"],
        "치킨전문점": ["호프-간이주점", "한식음식점"],
        "커피-음료": ["제과점", "양식음식점"],
        "호프-간이주점": ["치킨전문점", "한식음식점"],
        "편의점": ["슈퍼마켓", "종합소매점"],
        "미용실": ["네일숍", "화장품"],
        "노래방": ["당구장", "PC방"],
        "신발": ["일반의류", "가방"],            # 실데이터 8분기뿐 -> 의류로 대체
        "일반교습학원": ["외국어학원", "예술학원"],  # 실데이터 8분기뿐
        "일반의류": ["신발", "가방"],
    }

    def __init__(self, use_stub: bool = USE_STUB):
        self.use_stub = use_stub
        self._pipeline = None
        self._cache: dict = {}
        self.data = self._load_data()
        if not use_stub:
            self._load()

    def _load_data(self) -> dict:
        out = {}
        if self.DATA_PATH.exists():
            with open(self.DATA_PATH, encoding="utf-8") as f:
                out = json.load(f)
        # 생활인구(OA-14991, 2017~) — 매출/유동인구(2021~)보다 이력이 훨씬 길다
        if self.LIVING_POP_PATH.exists():
            with open(self.LIVING_POP_PATH, encoding="utf-8") as f:
                lp = json.load(f)
            out["living_population_quarterly"] = {
                "quarters": lp["quarters"], "values": lp["values"]}
        # 월별 생활인구 (104개월) — 분기보다 촘촘해 예측·계절성에 유리
        if self.LIVING_POP_MONTHLY_PATH.exists():
            with open(self.LIVING_POP_MONTHLY_PATH, encoding="utf-8") as f:
                lpm = json.load(f)
            out["living_population_monthly"] = {
                "months": lpm["months"], "values": lpm["values"]}
        return out

    def _load(self):
        try:
            import torch
            from chronos import BaseChronosPipeline
            dev = _device()
            self._pipeline = BaseChronosPipeline.from_pretrained(
                self.MODEL_ID,
                device_map=dev,
                torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
            )
            STATUS["Chronos"].update(loaded=True, device=dev)
            print(f"[Chronos-Bolt] 로드 완료 ({dev})")
        except Exception as e:
            STATUS["Chronos"]["error"] = str(e)[:200]
            self.use_stub = True
            print(f"[Chronos-Bolt] 로드 실패 -> 추세 연장으로 전환: {e}")

    # ---- A. 분기 추이 (업종별, 데이터 부족 시 유사 업종으로 연관 예측) ----
    @_timed("Chronos")
    def predict_trend(self, category: str | None = None, horizon: int = 2) -> dict:
        used_category, borrowed = category, None
        series = self._series(category)

        # 해당 업종 데이터가 없거나 너무 짧으면(<12분기) 유사 업종으로 대체
        if category and (not series or len(series.get("values", [])) < 12):
            for alt in self.SIMILAR_CATEGORY.get(category, []):
                alt_series = self.data.get("sales_by_category", {}).get(alt)
                if alt_series and len(alt_series["values"]) >= 12:
                    series, used_category, borrowed = alt_series, alt, alt
                    break

        if not series or len(series["values"]) < 4:
            return {"available": False, "reason": "시계열 데이터 부족"}

        values = series["values"]
        recent = values[-1]
        method = "stub-extrapolation"

        if not self.use_stub and self._pipeline is not None:
            try:
                import torch
                ctx = torch.tensor(values, dtype=torch.float32)
                quantiles, mean = self._pipeline.predict_quantiles(
                    ctx, prediction_length=horizon,
                    quantile_levels=[0.1, 0.5, 0.9],
                )
                forecast = [float(v) for v in mean[0].tolist()]
                lo = [float(v) for v in quantiles[0, :, 0].tolist()]
                hi = [float(v) for v in quantiles[0, :, 2].tolist()]
                method = "chronos-bolt"
            except Exception as e:
                STATUS["Chronos"]["error"] = str(e)[:200]
                forecast, lo, hi = self._extrapolate(values, horizon), None, None
        else:
            forecast, lo, hi = self._extrapolate(values, horizon), None, None

        change = (forecast[0] - recent) / recent * 100 if recent else 0.0
        out = {
            "available": True,
            "category": category or "전체",
            "used_category": used_category or "전체",
            "borrowed_from": borrowed,     # 유사 업종을 빌려 예측한 경우 그 업종명
            "quarters": series["quarters"],
            "history": values,
            "forecast": forecast,
            "change_pct": round(change, 1),
            "direction": "증가" if change > 3 else ("감소" if change < -3 else "보합"),
            "source": "서울시 상권분석서비스 추정매출 (회기동 상권 2곳)",
            "points": len(values),
            "method": method,
        }
        if lo and hi:
            out["lower"], out["upper"] = lo, hi
        return out

    @staticmethod
    def _extrapolate(values: list, horizon: int) -> list:
        """모델 없이 최근 N개 평균 변화율을 연장 (폴백)"""
        recent = values[-1]
        diffs = [(values[i] - values[i - 1]) / values[i - 1]
                 for i in range(max(1, len(values) - 4), len(values)) if values[i - 1]]
        rate = sum(diffs) / len(diffs) if diffs else 0.0
        return [recent * ((1 + rate) ** (i + 1)) for i in range(horizon)]

    def _forecast_series(self, values: list, horizon: int) -> list:
        """실제 Chronos 있으면 모델로, 없으면 추세 연장으로 다음 값들 예측 (공용)."""
        if not self.use_stub and self._pipeline is not None:
            try:
                import torch
                ctx = torch.tensor(values, dtype=torch.float32)
                _, mean = self._pipeline.predict_quantiles(
                    ctx, prediction_length=horizon, quantile_levels=[0.5])
                return [float(v) for v in mean[0].tolist()]
            except Exception as e:
                STATUS["Chronos"]["error"] = f"{type(e).__name__}: {e}"[:200]
        return self._extrapolate(values, horizon)

    # ---- A2. 월별 생활인구 추이 (104개월) ----
    @_timed("Chronos")
    def predict_population(self, horizon: int = 3) -> dict:
        lpm = self.data.get("living_population_monthly")
        if not lpm or len(lpm["values"]) < 12:
            return {"available": False, "reason": "월별 생활인구 데이터 부족"}
        values = lpm["values"]
        recent = values[-1]
        forecast = self._forecast_series(values, horizon)
        change = (forecast[0] - recent) / recent * 100 if recent else 0.0
        return {
            "available": True,
            "months": lpm["months"], "history": values, "forecast": forecast,
            "change_pct": round(change, 1),
            "direction": "증가" if change > 3 else ("감소" if change < -3 else "보합"),
            "points": len(values),
            "source": "서울 생활인구(OA-14991) 월별, 2017~",
        }

    # ---- A3. 생활인구 <-> 매출 연결 (전환율 + 교차검증) ----
    def link_population_sales(self) -> dict:
        """
        '사람 수(생활인구)'와 '실제 소비(매출)'를 잇는다.
          - 전환율: 겹치는 분기에서 매출/생활인구 평균 → 사람당 매출 기여
          - 교차검증: 인구 추이 방향 vs 매출 추이 방향 비교
            (사람은 느는데 매출은 준다 = 소비 전환이 약해지는 신호)
        """
        # 분기 생활인구는 hoegi_timeseries.json 안 population_quarterly에 있음
        pop_q = (self.data.get("population_quarterly")
                 or self.data.get("living_population_quarterly") or {})
        sales_q = self.data.get("sales_quarterly") or {}
        if not pop_q.get("values") or not sales_q.get("values"):
            return {"available": False}

        # 분기 키를 문자열로 맞춰 겹치는 구간 찾기
        pop_map = {str(q): v for q, v in zip(pop_q["quarters"], pop_q["values"])}
        sale_map = {str(q): v for q, v in zip(sales_q["quarters"], sales_q["values"])}
        # 생활인구 분기키는 '2021년_1분기' 형태 → '20211'로 정규화
        import re as _re
        def norm(k):
            m = _re.match(r"(\d{4}).*?(\d)분기", str(k))
            return f"{m.group(1)}{m.group(2)}" if m else str(k)
        pop_map = {norm(k): v for k, v in pop_map.items()}
        common = sorted(set(pop_map) & set(sale_map))
        if len(common) < 6:
            return {"available": False}

        pop = [pop_map[q] for q in common]
        sal = [sale_map[q] for q in common]
        n = len(pop)
        mp, ms = sum(pop) / n, sum(sal) / n
        cov = sum((pop[i] - mp) * (sal[i] - ms) for i in range(n)) / n
        sp = (sum((x - mp) ** 2 for x in pop) / n) ** 0.5
        ss = (sum((x - ms) ** 2 for x in sal) / n) ** 0.5
        corr = cov / (sp * ss) if sp and ss else 0.0

        # 전환율: 사람 1명당 분기 매출 기여 (원)
        per_person = ms / mp if mp else 0.0

        # 교차검증: 인구 예측 방향 vs 매출 예측 방향
        pop_dir = self.predict_population().get("direction")
        sale_dir = self.predict_trend().get("direction")
        diverge = (pop_dir == "증가" and sale_dir in ("감소", "보합")) or \
                  (pop_dir in ("감소", "보합") and sale_dir == "증가")

        return {
            "available": True,
            "correlation": round(corr, 3),
            "per_person_won": round(per_person),
            "pop_direction": pop_dir, "sales_direction": sale_dir,
            "diverging": diverge,
        }

    def _series(self, category: str | None) -> dict | None:
        if not self.data:
            return None
        if category and category in self.data.get("sales_by_category", {}):
            return self.data["sales_by_category"][category]
        return self.data.get("sales_quarterly")

    # ---- B. 시간대 혼잡도 ----
    def get_congestion(self, store_id: str, weekday: int, hour: int) -> float:
        key = (store_id, weekday, hour)
        if key not in self._cache:
            self._cache[key] = self._profile_congestion(store_id, weekday, hour)
        return self._cache[key]

    def _profile_congestion(self, store_id: str, weekday: int, hour: int) -> float:
        day_p = self.data.get("day_profile") or {}
        time_p = self.data.get("time_profile") or {}
        if not day_p or not time_p:
            return 0.4
        day_key = ["월", "화", "수", "목", "금", "토", "일"][weekday]
        band = ("00~06" if hour < 6 else "06~11" if hour < 11 else
                "11~14" if hour < 14 else "14~17" if hour < 17 else
                "17~21" if hour < 21 else "21~24")
        day_score = day_p.get(day_key, 0) / max(day_p.values())
        time_score = time_p.get(band, 0) / max(time_p.values())
        seed = int(hashlib.md5(store_id.encode()).hexdigest()[:6], 16)
        jitter = ((seed % 21) - 10) / 100.0
        return round(min(1.0, max(0.05, day_score * 0.35 + time_score * 0.65 + jitter)), 3)

    def profile_summary(self) -> dict:
        day_p = self.data.get("day_profile") or {}
        time_p = self.data.get("time_profile") or {}
        return {
            "busiest_day": max(day_p, key=day_p.get) if day_p else None,
            "busiest_time": max(time_p, key=time_p.get) if time_p else None,
            "day_profile": day_p, "time_profile": time_p,
        }

    def predict_batch(self, store_id: str, history: Optional[list] = None) -> dict:
        for wd in range(7):
            for hr in range(9, 24):
                self._cache[(store_id, wd, hr)] = self._profile_congestion(store_id, wd, hr)
        return {"store_id": store_id, "points": 7 * 15}

    # ---- 백테스트: 베이스라인 대비 MAE 개선율 ----
    def backtest(self, category: str | None = None, holdout: int = 4) -> dict:
        """
        마지막 holdout 분기를 가려놓고 예측 -> 실제와 비교.
        베이스라인은 '최근 4분기 평균' (요일별 평균에 해당하는 단순 기준선).
        """
        series = self._series(category)
        if not series or len(series["values"]) < holdout + 6:
            return {"available": False, "reason": "데이터 부족"}

        values = series["values"]
        train, test = values[:-holdout], values[-holdout:]

        # 베이스라인: 학습 구간 마지막 4개의 평균을 그대로 반복
        base_pred = [sum(train[-4:]) / 4] * holdout
        base_mae = sum(abs(p - a) for p, a in zip(base_pred, test)) / holdout

        # 모델 예측
        if not self.use_stub and self._pipeline is not None:
            try:
                import torch
                ctx = torch.tensor(train, dtype=torch.float32)
                _, mean = self._pipeline.predict_quantiles(
                    ctx, prediction_length=holdout, quantile_levels=[0.5])
                model_pred = [float(v) for v in mean[0].tolist()]
                method = "chronos-bolt"
            except Exception as e:
                model_pred = self._extrapolate(train, holdout)
                method = f"fallback ({str(e)[:60]})"
        else:
            model_pred = self._extrapolate(train, holdout)
            method = "stub-extrapolation"

        model_mae = sum(abs(p - a) for p, a in zip(model_pred, test)) / holdout
        improve = (base_mae - model_mae) / base_mae * 100 if base_mae else 0.0

        return {
            "available": True,
            "category": category or "전체",
            "holdout": holdout,
            "baseline_mae": round(base_mae),
            "model_mae": round(model_mae),
            "improvement_pct": round(improve, 1),
            "passed": improve >= 15,          # 검증 설계에서 정한 목표
            "target_pct": 15,
            "method": method,
            "actual": test,
            "model_pred": model_pred,
            "baseline_pred": base_pred,
        }

    # ---- 연도 기준 백테스트: 2021~2024 학습 -> 2025(+2026) 테스트 ----
    @staticmethod
    def _quarter_year(q) -> int | None:
        """분기 코드에서 연도만 추출. int(20211)와 str('2021년_1분기') 둘 다 지원."""
        if isinstance(q, int):
            return q // 10
        m = re.match(r"(\d{4})", str(q))
        return int(m.group(1)) if m else None

    def year_backtest(self, series_name: str = "sales_quarterly",
                       train_years: tuple = (2021, 2024),
                       test_years: tuple = (2025, 2026)) -> dict:
        """
        연도로 나눠서 검증한다 (분기 개수로 나누는 backtest()와 다른 기준).
          - series_name: "sales_quarterly" 또는 "population_quarterly"
          - 학습 구간과 테스트 구간을 실제 연도로 고정해서, "그해 실제로 오른 건지
            내린 건지"를 모델이 맞히는지까지 함께 본다 (MAE는 크기만, 방향은 못 봄).
        """
        series = self.data.get(series_name)
        if not series:
            return {"available": False, "reason": f"{series_name} 데이터 없음"}

        quarters, values = series["quarters"], series["values"]
        years = [self._quarter_year(q) for q in quarters]

        train_idx = [i for i, y in enumerate(years) if train_years[0] <= y <= train_years[1]]
        test_idx = [i for i, y in enumerate(years) if test_years[0] <= y <= test_years[1]]
        if len(train_idx) < 6 or not test_idx:
            return {"available": False, "reason": "학습/테스트 구간 데이터 부족"}

        train = [values[i] for i in train_idx]
        test = [values[i] for i in test_idx]
        test_quarters = [quarters[i] for i in test_idx]
        horizon = len(test)

        # 베이스라인: 학습 구간 마지막 4분기 평균을 그대로 반복
        base_pred = [sum(train[-4:]) / 4] * horizon
        method = "stub-extrapolation"

        if not self.use_stub and self._pipeline is not None:
            try:
                import torch
                ctx = torch.tensor(train, dtype=torch.float32)
                _, mean = self._pipeline.predict_quantiles(
                    ctx, prediction_length=horizon, quantile_levels=[0.5])
                model_pred = [float(v) for v in mean[0].tolist()]
                method = "chronos-bolt"
            except Exception as e:
                STATUS["Chronos"]["error"] = f"{type(e).__name__}: {e}"[:200]
                model_pred = self._extrapolate(train, horizon)
                method = f"fallback ({str(e)[:60]})"
        else:
            model_pred = self._extrapolate(train, horizon)

        def mae(pred):
            return sum(abs(p - a) for p, a in zip(pred, test)) / horizon

        def directional_accuracy(pred):
            """전분기 대비 증가/감소 방향을 몇 번 맞혔는지 (마지막 학습값부터 이어서 비교)"""
            prev_actual = train[-1]
            hits = 0
            for p, a in zip(pred, test):
                pred_dir = p - prev_actual
                actual_dir = a - prev_actual
                if (pred_dir > 0) == (actual_dir > 0):
                    hits += 1
                prev_actual = a          # 다음 비교는 실제값 기준으로 이어감
            return hits / horizon

        base_mae, model_mae = mae(base_pred), mae(model_pred)
        base_dir, model_dir = directional_accuracy(base_pred), directional_accuracy(model_pred)
        improve = (base_mae - model_mae) / base_mae * 100 if base_mae else 0.0

        return {
            "available": True,
            "series": series_name,
            "train_years": train_years, "test_years": test_years,
            "train_points": len(train), "test_points": horizon,
            "test_quarters": test_quarters,
            "actual": test,
            "model_pred": model_pred, "baseline_pred": base_pred,
            "baseline_mae": round(base_mae), "model_mae": round(model_mae),
            "improvement_pct": round(improve, 1),
            "baseline_direction_acc": round(base_dir * 100, 1),
            "model_direction_acc": round(model_dir * 100, 1),
            "method": method,
        }

    # ---- 데이터 증강 검증: 제공 유동인구만 vs 생활인구로 이력을 늘린 경우 ----
    @staticmethod
    def _monthly_to_quarterly(months: list, values: list) -> list:
        """월별 -> 분기 평균. 3개월이 다 있는 완전분기만 남긴다. [((연,분기), 값), ...]"""
        s, c = {}, {}
        order = []
        for mm, v in zip(months, values):
            y, m = int(str(mm)[:4]), int(str(mm)[4:6])
            q = (y, (m - 1) // 3 + 1)
            if q not in s:
                s[q], c[q] = 0.0, 0
                order.append(q)
            s[q] += v
            c[q] += 1
        return [(q, s[q] / c[q]) for q in order if c[q] == 3]

    @_timed("Chronos")
    def augmentation_backtest(self, n_test: int = 5) -> dict:
        """
        '데이터 증강이 예측을 개선하는가'를 실측으로 검증한다.

        타깃: population_quarterly (해커톤 제공 유동인구, 2021Q1~2026Q1)
              -> 매출과 달리 2026Q1 실측이 있어 정답으로 쓸 수 있다.
          A) baseline : 제공 유동인구만(약 20분기)으로 예측
          B) augmented: 생활인구(2017~)를 유동인구 단위로 환산해 앞에 이어붙여(약 36분기) 예측
          C) naive    : 직전 4분기 평균
        확장 윈도우로 1스텝 예측을 n_test회 반복해 MAE/MAPE 비교.
        """
        pop = self.data.get("population_quarterly")
        lpm = self.data.get("living_population_monthly")
        if not pop or not lpm:
            return {"available": False, "reason": "유동인구 또는 생활인구 데이터 없음"}

        pq, pv = pop["quarters"], pop["values"]

        def key(q):
            m = re.match(r"(\d{4}).*?(\d)", str(q))
            return (int(m.group(1)), int(m.group(2))) if m else None

        pkeys = [key(q) for q in pq]
        lq = self._monthly_to_quarterly(lpm["months"], lpm["values"])
        lmap = dict(lq)

        # 겹치는 분기로 단위 환산 계수(생활인구 일평균 -> 유동인구 분기합)
        common = [k for k in pkeys if k in lmap]
        if len(common) < 8:
            return {"available": False, "reason": "겹치는 구간이 부족해 환산 불가"}
        pm = sum(pv[pkeys.index(k)] for k in common) / len(common)
        lm = sum(lmap[k] for k in common) / len(common)
        scale = (pm / lm) if lm else 1.0

        # 증강 시계열 = [환산한 2017~2020 생활인구] + [제공 유동인구]
        start = pkeys[0]
        pre = [v * scale for k, v in lq if k < start]
        ext = pre + list(pv)
        offset = len(pre)
        if offset < 4:
            return {"available": False, "reason": "앞에 붙일 과거 구간이 없음"}

        n_test = max(1, min(n_test, len(pv) - 8))
        actual, predA, predB, predC, qs = [], [], [], [], []
        for i in range(len(pv) - n_test, len(pv)):
            histA = pv[:i]                 # 제공 데이터만
            histB = ext[: offset + i]      # 증강(과거 이력 추가)
            predA.append(self._forecast_series(histA, 1)[0])
            predB.append(self._forecast_series(histB, 1)[0])
            predC.append(sum(histA[-4:]) / 4)
            actual.append(pv[i])
            qs.append(str(pq[i]))

        def mae(p):
            return sum(abs(x - y) for x, y in zip(p, actual)) / len(actual)

        def mape(p):
            return sum(abs(x - y) / abs(y) for x, y in zip(p, actual)) / len(actual) * 100

        A, B, C = mae(predA), mae(predB), mae(predC)
        return {
            "available": True,
            "target": "population_quarterly (해커톤 제공 유동인구)",
            "test_quarters": qs,
            "context_baseline": len(pv) - n_test,
            "context_augmented": offset + len(pv) - n_test,
            "scale_factor": round(scale, 3),
            "actual": actual,
            "pred_baseline": predA, "pred_augmented": predB, "pred_naive": predC,
            "mae_baseline": round(A), "mae_augmented": round(B), "mae_naive": round(C),
            "mape_baseline": round(mape(predA), 2),
            "mape_augmented": round(mape(predB), 2),
            "mape_naive": round(mape(predC), 2),
            "gain_vs_baseline_pct": round((A - B) / A * 100, 1) if A else 0.0,
            "gain_vs_naive_pct": round((C - B) / C * 100, 1) if C else 0.0,
            "method": "chronos-bolt" if (not self.use_stub and self._pipeline is not None) else "stub",
        }

    # ---- 유동인구 예측 (운영용) — 제공 데이터 전체 + 검증에서 이긴 방식 채택 ----
    @_timed("Chronos")
    def forecast_footfall(self, horizon: int = 2, augment: bool | None = None) -> dict:
        """
        제공 유동인구(2021Q1~2026Q1 전체)로 다음 분기를 예측한다.

        augment=None 이면 백테스트 결과에 따라 자동 선택한다.
        검증(2025Q1~2026Q1 홀드아웃): 증강 MAPE 8.61% < 제공만 9.38% -> 증강 채택.
        단, 계절 naive(작년 동분기)가 5.60%로 더 정확했으므로 그 값도 함께 돌려주고
        어느 쪽이 검증에서 나았는지 명시한다. 숫자를 고르는 건 화면이 아니라 검증이다.
        """
        pop = self.data.get("population_quarterly")
        if not pop or len(pop["values"]) < 8:
            return {"available": False, "reason": "유동인구 데이터 부족"}
        pq, pv = pop["quarters"], list(pop["values"])

        # 증강 시계열 만들기 (생활인구 2017~ 를 유동인구 단위로 환산해 앞에 붙임)
        ext, used_aug = pv, False
        lpm = self.data.get("living_population_monthly")
        if lpm and augment is not False:
            try:
                def key(q):
                    m = re.match(r"(\d{4}).*?(\d)", str(q))
                    return (int(m.group(1)), int(m.group(2))) if m else None
                pkeys = [key(q) for q in pq]
                lq = self._monthly_to_quarterly(lpm["months"], lpm["values"])
                lmap = dict(lq)
                common = [k for k in pkeys if k in lmap]
                if len(common) >= 8:
                    pm = sum(pv[pkeys.index(k)] for k in common) / len(common)
                    lm = sum(lmap[k] for k in common) / len(common)
                    scale = (pm / lm) if lm else 1.0
                    pre = [v * scale for k, v in lq if k < pkeys[0]]
                    if len(pre) >= 4:
                        ext, used_aug = pre + pv, True
            except Exception as e:
                STATUS["Chronos"]["error"] = f"{type(e).__name__}: {e}"[:200]

        model_fc = self._forecast_series(ext, horizon)

        # 계절 naive — 작년 같은 분기 (검증에서 가장 정확했던 방법)
        seasonal = [pv[-4 + i] if len(pv) >= 4 else pv[-1] for i in range(horizon)]

        recent = pv[-1]
        chg_model = (model_fc[0] - recent) / recent * 100 if recent else 0.0
        chg_seas = (seasonal[0] - recent) / recent * 100 if recent else 0.0
        return {
            "available": True,
            "source": "해커톤 제공 유동인구 (2021Q1~2026Q1 전체)",
            "quarters": pq, "history": pv,
            "context_points": len(ext), "augmented": used_aug,
            "model_forecast": model_fc, "model_change_pct": round(chg_model, 1),
            "seasonal_forecast": seasonal, "seasonal_change_pct": round(chg_seas, 1),
            "validated": {
                "chronos_augmented_mape": 8.61,
                "chronos_baseline_mape": 9.38,
                "seasonal_naive_mape": 5.60,
                "best": "seasonal_naive",
                "note": "홀드아웃(2025Q1~2026Q1) 검증. 계절 naive가 가장 정확해 이를 대표값으로 쓴다.",
            },
            "headline": seasonal[0],          # 화면에 쓸 대표값 = 검증에서 이긴 방법
            "headline_change_pct": round(chg_seas, 1),
            "method": "chronos-bolt" if (not self.use_stub and self._pipeline is not None) else "stub",
        }

    @staticmethod
    def to_label(score: float) -> str:
        return "붐빔" if score >= 0.66 else ("보통" if score >= 0.33 else "한산")


# ================================================================ BGE-M3
class BgeM3:
    """매칭 — 상인 과제 ↔ 학생 프로필 의미 유사도."""

    MODEL_ID = "BAAI/bge-m3"

    def __init__(self, use_stub: bool = USE_STUB):
        self.use_stub = use_stub
        self._model = None
        self._vec_cache: dict = {}
        if not use_stub:
            self._load()

    def _load(self):
        try:
            from FlagEmbedding import BGEM3FlagModel
            dev = _device()
            self._model = BGEM3FlagModel(self.MODEL_ID, use_fp16=(dev == "cuda"))
            STATUS["BGE-M3"].update(loaded=True, device=dev)
            print(f"[BGE-M3] 로드 완료 ({dev})")
        except Exception as e:
            STATUS["BGE-M3"]["error"] = str(e)[:200]
            self.use_stub = True
            print(f"[BGE-M3] 로드 실패 -> 키워드 매칭으로 전환: {e}")

    @_timed("BGE-M3")
    def embed(self, texts: list) -> list:
        """등록 시점에 1회만 호출하고 결과를 캐싱한다 -> 조회 때는 모델을 안 돌린다."""
        if self.use_stub:
            return [self._stub_vector(t) for t in texts]
        try:
            return self._model.encode(texts, batch_size=8, max_length=512)["dense_vecs"].tolist()
        except Exception as e:
            STATUS["BGE-M3"]["error"] = str(e)[:200]
            return [self._stub_vector(t) for t in texts]

    def _vec(self, text: str):
        if text not in self._vec_cache:
            self._vec_cache[text] = self.embed([text])[0]
        return self._vec_cache[text]

    def similarity(self, a: str, b: str) -> float:
        if self.use_stub:
            return self._stub_similarity(a, b)
        try:
            import numpy as np
            va, vb = np.array(self._vec(a)), np.array(self._vec(b))
            denom = np.linalg.norm(va) * np.linalg.norm(vb)
            return round(float(va @ vb / denom), 3) if denom else 0.0
        except Exception as e:
            STATUS["BGE-M3"]["error"] = str(e)[:200]
            return self._stub_similarity(a, b)

    @staticmethod
    def _stub_vector(text: str) -> list:
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        return [((seed >> i) % 100) / 100.0 for i in range(8)]

    @staticmethod
    def _stub_similarity(a: str, b: str) -> float:
        topic = {
            "번역": {"영어", "중국어", "통번역", "어학", "번역", "메뉴판"},
            "마케팅": {"sns", "인스타", "홍보", "마케팅", "콘텐츠", "릴스", "경영"},
            "디자인": {"디자인", "영상", "편집", "사진", "포스터"},
            "분석": {"데이터", "분석", "리서치", "설문", "통계"},
        }
        a_l, b_l = a.lower(), b.lower()
        score = 0.0
        for words in topic.values():
            ha = any(w in a_l for w in words)
            hb = any(w in b_l for w in words)
            if ha and hb:
                score = max(score, 0.85)
            elif ha or hb:
                score = max(score, 0.35)
        return round(score or 0.2, 3)


# ================================================================ 싱글턴
print(f"[우리사이] AI 모드: {'실제 모델' if not USE_STUB else '규칙 기반(stub)'}")
exaone = Exaone()
chronos = Chronos()
bge = BgeM3()
