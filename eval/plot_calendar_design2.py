"""
'유동인구 예측 — 학사일정 보정' 실험 설계 슬라이드 (표 포함, 결과 없음).

설계 시점의 내용만 담는다. 목표는 MAPE 8%대 -> 4%대.
실제 결과 수치는 다음 장에서 다룬다.

실행
  python eval/plot_calendar_design2.py
출력
  eval/실험설계_유동인구예측_표.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험설계_유동인구예측_표.png"

INK, MUTED, LINE = "#0b0b0b", "#6b6a66", "#dcdad3"
GREEN, ORANGE, SOFT = "#3a7d44", "#c8551f", "#f6f5f1"

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")


def box(x, y, w, h, text, sub="", fc="white", ec=LINE, tc=INK, fs=11.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.02,rounding_size=0.09",
                                facecolor=fc, edgecolor=ec, linewidth=1.2))
    ax.text(x + w / 2, y + h / 2 + (0.10 if sub else 0), text,
            fontsize=fs, color=tc, ha="center", va="center")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.17, sub, fontsize=9,
                color=MUTED, ha="center", va="center")


def arrow(x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=12, linewidth=1.2,
                                 color=MUTED, shrinkA=0, shrinkB=0))


def table(x, y, w, h, head, rows, widths, title, accent=None, accent_rows=None):
    """
    제목 + 표. widths 는 합이 1이 되는 비율.
    accent 열은 accent_rows 에 든 행만 강조한다 — '동일'처럼 안 바뀐 칸까지
    주황으로 칠하면 무엇이 달라졌는지 잘못 읽힌다.
    """
    ax.text(x, y + h + 0.30, title, fontsize=15, color=INK, va="top")
    n = len(rows) + 1
    rh = h / n
    cx = [x + w * sum(widths[:i]) for i in range(len(widths) + 1)]
    for r in range(n):
        ry = y + h - (r + 1) * rh
        if r == 0:
            ax.add_patch(Rectangle((x, ry), w, rh, facecolor="#eceae3", edgecolor="none"))
        elif r % 2 == 0:
            ax.add_patch(Rectangle((x, ry), w, rh, facecolor=SOFT, edgecolor="none"))
        ax.plot([x, x + w], [ry, ry], color=LINE, linewidth=0.8)
        cells = head if r == 0 else rows[r - 1]
        for c, txt in enumerate(cells):
            col = MUTED if r == 0 else INK
            if (r > 0 and accent is not None and c == accent
                    and (accent_rows is None or (r - 1) in accent_rows)):
                col = ORANGE
            ax.text(cx[c] + 0.16, ry + rh / 2, txt, fontsize=11,
                    color=col, va="center")
    ax.plot([x, x + w], [y + h, y + h], color=LINE, linewidth=0.8)


# ------------------------------------------------------------------ 머리말
ax.text(0.55, 8.74, "우리사이", fontsize=13, color=GREEN, va="top")
ax.text(1.60, 8.72, "검증 설계", fontsize=12, color=MUTED, va="top")
ax.plot([0.55, 15.45], [8.46, 8.46], color=GREEN, linewidth=1.6)

ax.text(0.55, 8.20, "실험 설계 및 지표 정의", fontsize=24, color=INK, va="top")
ax.text(5.90, 8.14, "유동인구 예측 — 학사일정 보정", fontsize=18, color=GREEN, va="top")

# ------------------------------------------------------------------ 흐름도
box(0.60, 6.82, 2.45, 0.78, "Chronos-Bolt", "예측값 산출")
arrow(3.15, 7.21, 3.55, 7.21)

box(3.65, 7.22, 2.20, 0.56, "Before  ·  그대로", fc=SOFT)
box(3.65, 6.60, 2.20, 0.56, "After  ·  × 보정계수",
    fc="#fdf0e8", ec=ORANGE, tc=ORANGE)
arrow(5.95, 7.50, 6.40, 7.30)
arrow(5.95, 6.88, 6.40, 7.12)

box(6.50, 6.82, 1.85, 0.78, "실측과 비교", "MAE · MAPE")

# 보정계수 산출 — 방학이 학기보다 '적다'
ax.add_patch(Rectangle((8.75, 6.55), 6.70, 1.30, facecolor=SOFT, edgecolor="none"))
ax.text(9.00, 7.72, "보정계수 산출", fontsize=12.5, color=GREEN, va="top")
ax.text(9.00, 7.36, "방학 분기 (Q1·Q3) 평균 유동인구", fontsize=11, color=INK, va="top")
ax.text(13.35, 7.36, "2,296 만", fontsize=11, color=INK, va="top")
ax.text(9.00, 7.06, "학기 분기 (Q2·Q4) 평균 유동인구", fontsize=11, color=INK, va="top")
ax.text(13.35, 7.06, "2,536 만", fontsize=11, color=INK, va="top")
ax.text(9.00, 6.76, "보정계수 = 방학 평균 ÷ 학기 평균 = 0.905",
        fontsize=11.5, color=ORANGE, va="top")

# ------------------------------------------------------------------ 표 1
table(0.60, 2.55, 7.15, 3.05,
      ["항목", "Before", "After"],
      [["예측 모델", "Chronos-Bolt", "Chronos-Bolt (동일)"],
       ["입력 데이터", "유동인구 21분기", "동일"],
       ["학사일정", "반영 안 함", "예측 후 보정계수 적용"],
       ["산출식", "예측값 그대로", "예측값 × 보정계수"],
       ["검증 방식", "확장 윈도우 1스텝 8회", "동일"]],
      [0.24, 0.34, 0.42], "실험 조건", accent=2, accent_rows={2, 3})

# ------------------------------------------------------------------ 표 2
table(8.30, 2.55, 7.15, 3.05,
      ["지표", "정의", "목표"],
      [["MAPE", "평균 절대 백분율 오차", "8%대 → 4%대"],
       ["MAE", "평균 절대 오차", "감소"],
       ["층화 오차", "방학 / 학기 분기 각각", "방학 개선 > 학기 개선"],
       ["승률", "오차가 준 분기 수 ÷ 8", "5개 이상"],
       ["비교 대상", "naive · 계절 naive", "둘 다 상회"]],
      [0.20, 0.42, 0.38], "측정 지표", accent=2)

# ------------------------------------------------------------------ 목표
ax.add_patch(Rectangle((0.60, 0.75), 14.85, 1.15, facecolor="#fdf0e8", edgecolor="none"))
ax.text(0.95, 1.70, "설계 목표", fontsize=13, color=ORANGE, va="top")
ax.text(3.05, 1.72, "MAPE  8%대  →  4%대", fontsize=20, color=INK, va="top")
ax.text(7.55, 1.66,
        "보정 없이 예측했을 때의 오차가 8%대. 학사일정 보정으로 이를 절반 수준까지 낮추는 것을 목표로 설계",
        fontsize=11.5, color=INK, va="top")
ax.text(3.05, 1.14, "결과를 보기 전에 확정한 목표이며, 미달 시 미달로 보고한다",
        fontsize=10.5, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
