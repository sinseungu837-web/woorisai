"""
'유동인구 예측 — 학사일정 보정 실험' 설계를 PPT 한 페이지로.

결과는 넣지 않는다. 변인 · 진행방식 · 측정 지표만 한눈에 보이게 한다.

실행
  python eval/plot_calendar_design.py
출력
  eval/실험설계_유동인구예측.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험설계_유동인구예측.png"

INK, MUTED, LINE = "#0b0b0b", "#6b6a66", "#dcdad3"
GREEN, ORANGE, BLUE, SOFT = "#3a7d44", "#c8551f", "#2a78d6", "#f7f6f2"

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")


def box(x, y, w, h, text, sub="", fc="white", ec=LINE, tc=INK, fs=12, lw=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.02,rounding_size=0.10",
                                facecolor=fc, edgecolor=ec, linewidth=lw))
    ax.text(x + w / 2, y + h / 2 + (0.11 if sub else 0), text,
            fontsize=fs, color=tc, ha="center", va="center")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.19, sub, fontsize=9.5,
                color=MUTED if tc == INK else tc, ha="center", va="center")


def arrow(x1, y1, x2, y2, color=MUTED):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=13, linewidth=1.3,
                                 color=color, shrinkA=0, shrinkB=0))


# ------------------------------------------------------------------ 머리말
ax.text(0.55, 8.72, "우리사이", fontsize=13, color=GREEN, va="top")
ax.text(1.60, 8.70, "검증 설계", fontsize=12, color=MUTED, va="top")
ax.plot([0.55, 15.45], [8.44, 8.44], color=GREEN, linewidth=1.6)

ax.text(0.55, 8.16, "실험 설계 및 지표 정의", fontsize=25, color=INK, va="top")
ax.text(6.05, 8.10, "유동인구 예측 — 학사일정 보정 실험",
        fontsize=19, color=GREEN, va="top")

# ------------------------------------------------------------------ 흐름도
box(0.60, 6.28, 2.35, 0.90, "분기 시계열", "회기동 유동인구 21분기")
arrow(3.05, 6.73, 3.55, 6.73)
box(3.65, 6.28, 2.30, 0.90, "Chronos-Bolt", "1스텝 예측")

# Before 갈래
arrow(6.05, 6.90, 6.55, 7.28)
box(6.65, 6.95, 3.00, 0.72, "Before  ·  보정 없음", fc=SOFT, ec=LINE, fs=12)
arrow(9.75, 7.31, 10.85, 7.05)

# After 갈래
arrow(6.05, 6.56, 6.55, 6.18)
box(6.65, 5.78, 3.00, 0.72, "After  ·  × 보정계수",
    fc="#fdf0e8", ec=ORANGE, tc=ORANGE, fs=12)
arrow(9.75, 6.14, 10.85, 6.42)

box(10.95, 6.28, 2.55, 0.90, "실측과 비교", "MAE · MAPE")

ax.text(6.68, 5.52, "보정계수 = 방학 분기 평균 ÷ 학기 분기 평균   "
                    "(방학이면 곱하고, 학기면 나눈다)",
        fontsize=10, color=MUTED, va="top")

# ------------------------------------------------------------------ 3단 정리
COLS = [
    ("변인", [
        "Chronos-Bolt는 단변량 모델이라",
        "학사일정을 변수로 넣을 수 없다",
        "",
        "그래서 '변수 투입 유무'가 아니라",
        "예측 후 보정 단계의 유무를 비교한다",
    ]),
    ("진행방식", [
        "1스텝 예측을 8회 반복 (확장 윈도우)",
        "",
        "보정 전·후에 같은 Chronos 출력 사용",
        "— 보정 단계만 다르게 적용",
        "",
        "각 시점 이전 데이터로만 계수 재계산",
        "— 미래 정보 차단",
        "",
        "검증 2024Q2~2025Q4 (7개)",
        "테스트 2026Q1 (1개)",
    ]),
    ("측정 지표", [
        "MAE · MAPE      예측 오차",
        "",
        "층화 오차          방학 / 학기 각각",
        "— 효과가 방학에 몰리는지 확인",
        "",
        "승률                 8분기 중 개선된 분기 수",
        "",
        "비교 대상          naive (직전 분기값)",
        "                       계절 naive (전년 동분기)",
    ]),
]

x0, colw, gap = 0.60, 4.83, 0.16
for i, (title, lines) in enumerate(COLS):
    x = x0 + i * (colw + gap)
    ax.add_patch(Rectangle((x, 1.55), colw, 3.35, facecolor=SOFT, edgecolor="none"))
    ax.add_patch(Rectangle((x, 4.78), colw, 0.12, facecolor=GREEN, edgecolor="none"))
    ax.text(x + 0.30, 4.55, title, fontsize=16, color=INK, va="top")
    yy = 3.98
    for ln in lines:
        if ln:
            col = ORANGE if ln.startswith("—") else INK
            fs = 10.5 if ln.startswith("—") else 11.5
            ax.text(x + 0.30, yy, ln, fontsize=fs, color=col, va="top")
        yy -= 0.252

# ------------------------------------------------------------------ 성공 기준
ax.add_patch(Rectangle((0.60, 0.60), 14.85, 0.70, facecolor="#fdf0e8", edgecolor="none"))
ax.text(0.92, 1.13, "성공 기준", fontsize=12.5, color=ORANGE, va="top")
ax.text(2.45, 1.16,
        "비교 대상 대비 MAPE 15% 이상 감소   ·   방학 개선율 > 학기 개선율   ·   "
        "8분기 중 5개 이상 개선",
        fontsize=12.5, color=INK, va="top")
ax.text(2.45, 0.86, "결과를 보기 전에 확정한 기준이며, 미달은 미달로 보고한다",
        fontsize=10.5, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
