"""
'실험 설계 및 지표 정의' — PPT 한 페이지.

4개 모듈의 검증 가설 · 비교 대상 · 핵심 지표 · 성공 기준을 한 표로 정리한다.
성공 기준은 결과를 보기 전에 정한 값만 적는다(사후 조정 금지).

실행
  python eval/plot_design_onepage.py
출력
  eval/실험설계_한장.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험설계_한장.png"

INK, MUTED, LINE = "#0b0b0b", "#6b6a66", "#dcdad3"
GREEN, ORANGE, SOFT = "#3a7d44", "#c8551f", "#f7f6f2"

# 모듈, 검증 가설, 비교 대상, 핵심 지표, 성공 기준
ROWS = [
    ["시간표 · 의도 파싱",
     "비정형 입력을 정확히 구조화한다",
     "정규식",
     "슬롯 F1\n슬롯 정확도",
     "F1 0.85 이상"],
    ["동선 추천",
     "제한시간 내 실행 가능한\n다점포 코스를 만든다",
     "거리순 상위 3개",
     "시간 제약 위반율\n노출 업종 수 · HHI",
     "위반 0%\nHHI baseline 대비 하락"],
    ["수요 예측",
     "학사일정을 반영하면\n특수기간 오차가 준다",
     "naive · 계절 naive",
     "MAE · MAPE\n(방학/학기 층화)",
     "baseline 대비 15% 이상 감소"],
    ["전략 생성",
     "예측값에 근거한 실행안을 만든다\n(지어내지 않는다)",
     "일반 질의",
     "근거 포함률\n환각률",
     "환각 0%\n모든 제안에 근거 후기 첨부"],
]
HEAD = ["모듈", "검증 가설", "비교 대상", "핵심 지표", "성공 기준"]

# 하단 — 재현에 필요한 조건
FOOT = [
    ("실험 데이터 수",
     "슬롯 40문항 · 챗봇 20입력 / 추천 750건 / 예측 8분기 / 후기 171건(가게 6곳)"),
    ("train / test 조건",
     "시간순 분할 (학습 ~2024 · 검증 2025 · 테스트 2026Q1) · 예측은 확장 윈도우, 매 시점 계수 재추정"),
    ("동일 입력 사용",
     "두 방식에 같은 입력 · 같은 시점 · 같은 후보 풀을 사용 (seed 42 고정)"),
    ("성공·실패 판정",
     "사전 기준 충족 시 달성, 미달은 미달로 보고 — 결과를 보고 기준을 바꾸지 않는다"),
]

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")

# ------------------------------------------------------------------ 머리말
ax.text(0.55, 8.72, "우리사이", fontsize=13, color=GREEN, va="top")
ax.text(1.60, 8.70, "검증 설계", fontsize=12, color=MUTED, va="top")
ax.plot([0.55, 15.45], [8.42, 8.42], color=GREEN, linewidth=1.6)

ax.text(0.55, 8.10, "실험 설계 및 지표 정의", fontsize=26, color=INK, va="top")
ax.text(0.55, 7.42,
        "각 모듈의 성공 기준을 먼저 정의하고, 더 단순한 기준모델과 동일 조건에서 비교했습니다",
        fontsize=13, color=MUTED, va="top")

# ------------------------------------------------------------------ 표
tb_ax = fig.add_axes([0.033, 0.275, 0.935, 0.505]); tb_ax.axis("off")
tb = tb_ax.table(cellText=ROWS, colLabels=HEAD, cellLoc="left",
                 colWidths=[.145, .255, .145, .215, .240],
                 bbox=[0, 0, 1, 1])
tb.auto_set_font_size(False)
tb.set_fontsize(12)
for (r, c), cell in tb.get_celld().items():
    cell.set_linewidth(0)
    cell.get_text().set_ha("left")
    cell.PAD = 0.035
    cell.visible_edges = "horizontal"
    cell.set_edgecolor(LINE)
    cell.set_linewidth(0.9)
    if r == 0:
        cell.set_facecolor("white")
        cell.set_text_props(color=MUTED)
        cell.set_fontsize(11.5)
        continue
    cell.set_facecolor("white" if r % 2 else SOFT)
    if c == 0:
        cell.set_text_props(color=INK)
    elif c == 4:
        cell.set_text_props(color=ORANGE)
    else:
        cell.set_text_props(color=INK if c == 1 else MUTED)

# ------------------------------------------------------------------ 하단 조건
ax.add_patch(Rectangle((0.55, 0.55), 14.90, 1.62, facecolor=SOFT, edgecolor="none"))
ax.text(0.85, 2.02, "재현 조건", fontsize=12, color=GREEN, va="top")
yy = 1.72
for name, desc in FOOT:
    ax.text(0.85, yy, f"· {name}", fontsize=11, color=INK, va="top")
    ax.text(3.10, yy, desc, fontsize=11, color=MUTED, va="top")
    yy -= 0.335

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
