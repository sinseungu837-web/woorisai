"""
알고리즘·모델 구조 + 기술 공백 해결 점검 도식.

세 개의 표를 한 장에 담는다.
  1) 쓴 모델 3종의 구조
  2) 우리가 직접 구현한 알고리즘 (모델이 못 하는 부분)
  3) 이전에 확인된 기술 공백이 해결됐는지 점검

실행
  python eval/plot_tech_stack.py
출력
  eval/기술스택_공백점검.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "기술스택_공백점검.png"

INK, MUTED, GRID = "#0b0b0b", "#6b6a66", "#e1e0d9"
GREEN, AMBER, RED, BLUE = "#1baf7a", "#c98500", "#d03b3b", "#2a78d6"

# ---------------------------------------------------------------- 1. 모델 구조
MODELS = [
    ["EXAONE 3.5 7.8B-Instruct", "Decoder-only Transformer\n(자기회귀 생성)",
     "질문 파싱 · 문장 생성", "그리디 디코딩\n(do_sample=False)"],
    ["Chronos-Bolt base", "T5 기반 Encoder-Decoder\n(패치 단위 입력)",
     "혼잡도 · 유동인구 · 매출", "분위수 직접 출력\n원본 대비 약 250배 빠름"],
    ["BGE-M3  (부수)", "XLM-RoBERTa-large Encoder\n24층 · hidden 1024",
     "프로젝트·팀 매칭", "[CLS] 풀링 → 1024차원\nL2 정규화 후 코사인"],
]
MODEL_HEAD = ["모델", "구조", "쓰는 곳", "사용 방식"]

# ---------------------------------------------------------- 2. 직접 구현 알고리즘
ALGOS = [
    ["말뭉치 투표 조사 제거", "voice.py",
     "어간이 맨몸으로 등장했거나\n서로 다른 조사 2종 이상을 달았을 때만 분리",
     "형태소 분석기 없이\n'와이파이→와이파' 파괴 방지"],
    ["TF-IDF 키워드 추출", "voice.py",
     "count × log((N+1)/(df+1)) + 1",
     "'커피' 같은 업종 일반명사 대신\n'두쫀쿠'를 상위로"],
    ["명사 필터 3중", "voice.py",
     "'요' 종결 + 활용어미 + 어간-불용어",
     "'좋았어요·때문에'가\n키워드로 올라오는 것 차단"],
    ["시간축 분할 트렌드", "voice.py",
     "기간(달력) 절반으로 분할 → 앞/뒤 등장 비교",
     "관측치 중앙값으로 나누면\n후기 몰린 시기로 경계가 끌림"],
    ["분산 점수", "logic.py",
     "관련성 × 신규성 × 혼잡도 × 타임딜\nnovelty = clamp((5/share)^0.35, 0.7, 2.2)",
     "곱셈이라 관련성 0이면 0점\n→ 엉뚱한 업종 강제 추천 차단"],
    ["라운드로빈 회전", "main.py",
     "상위 후보 풀 안에서 시작 지점 이동",
     "신규성 상한 동률(2.20) 6개를\n순번으로 풀어 독점 방지"],
    ["학사일정 보정", "코드 (산수)",
     "방학분기 평균 ÷ 학기분기 평균 = 계수\n확장 윈도우로 매 시점 재추정",
     "Chronos가 단변량이라\n외생변수를 못 받는 것을 우회"],
    ["도보시간 캘리브레이션", "logic.py",
     "직선거리 × 1.17 ÷ 88m/분",
     "실제 보행경로 898건으로\n계수를 실측 보정"],
]
ALGO_HEAD = ["알고리즘", "위치", "방법", "왜 필요했나"]

# ------------------------------------------------------------ 3. 기술 공백 점검
# (공백, 해결 수단, 검증 수치, 상태)  상태: 해결 / 부분 / 미해결
GAPS = [
    ["LLM이 없는 가게를 지어냄 (환각 45%)", "판단을 코드로 옮기고 근거 강제",
     "환각률 45% → 0%", "해결"],
    ["후기가 조사 때문에 흩어짐", "말뭉치 투표 조사 제거",
     "키워드 검출률 0% → 100%", "해결"],
    ["고정 5버킷이라 '무엇을' 원하는지 소실", "TF-IDF 키워드 + 의도·트렌드",
     "비전 카드 0장 → 23장", "해결"],
    ["형태소 분석기 의존성 추가 불가", "말뭉치 통계로 대체",
     "명사 20개 유지 / 서술어 15개 제거", "해결"],
    ["거리순 추천이 쏠림을 재생산", "분산 점수 + 라운드로빈",
     "HHI 2,733 → 1,251 (실험)", "부분"],
    ["Chronos가 학사일정을 못 받음(단변량)", "예측 후 계수 보정",
     "MAPE 8.42% → 3.87%", "부분"],
    ["Chronos 매출 예측이 naive보다 나쁨", "미해결 — 주장 강도를 낮춤",
     "MAE naive 대비 -10.3%, 방향 50%", "미해결"],
    ["stay_time 원본 100% 결측", "업종별 체류시간 상수로 대체",
     "실측 아님 — 파일럿 데이터 필요", "미해결"],
    ["footfall이 상권 단위(업종별 아님)", "미해결",
     "업종별 유동인구 산출 불가", "미해결"],
    ["날씨·공휴일 등 외부 통제변수 없음", "미해결",
     "계절성 외 변동 설명 불가", "미해결"],
]
GAP_HEAD = ["이전에 확인된 기술 공백", "해결 수단", "검증 수치", "상태"]
STATE_COLOR = {"해결": GREEN, "부분": AMBER, "미해결": RED}


def table(ax, head, body, widths, colors=None, fs=9.5, bbox=(0, 0, 1, 1)):
    tb = ax.table(cellText=body, colLabels=head, cellLoc="left",
                  colWidths=widths, bbox=list(bbox))
    tb.auto_set_font_size(False)
    tb.set_fontsize(fs)
    for (r, c), cell in tb.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.set_linewidth(0.8)
        cell.get_text().set_ha("left")
        cell.PAD = 0.04
        if r == 0:
            cell.set_facecolor("#f1efe8")
            cell.set_text_props(color=INK)
            continue
        if r % 2 == 0:
            cell.set_facecolor("#fbfaf7")
        if colors and c == len(head) - 1:
            cell.set_text_props(color=colors[r - 1])
        elif c == 0:
            cell.set_text_props(color=INK)
        else:
            cell.set_text_props(color=MUTED if c != 2 else INK)
    return tb


fig = plt.figure(figsize=(15.2, 17.2), dpi=170)
fig.patch.set_facecolor("white")
gs = fig.add_gridspec(7, 1,
                      height_ratios=[0.30, 0.10, 1.05, 0.10, 2.55, 0.10, 3.15],
                      hspace=0.05)

ax = fig.add_subplot(gs[0]); ax.axis("off")
ax.text(0, 0.92, "우리사이 · 알고리즘과 모델 구조, 그리고 기술 공백 점검",
        fontsize=21, color=INK, va="top")
ax.text(0, 0.18, "세 모델 모두 zero-shot(파인튜닝 없음) · 판단은 코드, LLM은 번역",
        fontsize=11.5, color=MUTED, va="top")

ax = fig.add_subplot(gs[1]); ax.axis("off")
ax.text(0, 0.3, "1.  쓴 모델의 구조", fontsize=14, color=INK, va="top")

ax = fig.add_subplot(gs[2]); ax.axis("off")
table(ax, MODEL_HEAD, MODELS, [.20, .27, .21, .32], fs=10)

ax = fig.add_subplot(gs[3]); ax.axis("off")
ax.text(0, 0.3, "2.  직접 구현한 알고리즘 — 모델이 못 하는 부분",
        fontsize=14, color=INK, va="top")

ax = fig.add_subplot(gs[4]); ax.axis("off")
table(ax, ALGO_HEAD, ALGOS, [.17, .10, .38, .35], fs=9.5)

ax = fig.add_subplot(gs[5]); ax.axis("off")
ax.text(0, 0.3, "3.  이전 기술 공백이 해결됐는가", fontsize=14, color=INK, va="top")

ax = fig.add_subplot(gs[6]); ax.axis("off")
table(ax, GAP_HEAD, GAPS, [.33, .25, .28, .09],
      colors=[STATE_COLOR[g[3]] for g in GAPS], fs=10)
n_ok = sum(1 for g in GAPS if g[3] == "해결")
n_part = sum(1 for g in GAPS if g[3] == "부분")
ax.text(0, -0.055,
        f"공백 {len(GAPS)}건 중  해결 {n_ok} · 부분 {n_part} · "
        f"미해결 {len(GAPS) - n_ok - n_part}."
        "   '부분'은 실험에서 검증됐으나 플랫폼 반영이 아직 덜 된 것 — "
        "분산은 열린 추천에만, 학사일정 보정은 예측 경로에 미반영.",
        transform=ax.transAxes, fontsize=10, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
