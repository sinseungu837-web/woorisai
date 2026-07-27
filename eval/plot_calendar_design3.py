"""
'유동인구 예측 정확도 개선 실험' 설계 슬라이드 — 4단계 카드형.

업종 분산도 슬라이드와 같은 형식. 결과는 넣지 않는다.

실행
  python eval/plot_calendar_design3.py
출력
  eval/실험설계_유동인구_카드.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험설계_유동인구_카드.png"

NAVY, INK, MUTED = "#1f3b73", "#1a1a1a", "#6b6a66"
LINE, CARD, BG = "#e2e0da", "#fbfaf8", "#f6f5f2"

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")


def card(x, y, w, h, fc=CARD, ec=LINE, lw=1.1, r=0.12):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle=f"round,pad=0.02,rounding_size={r}",
                                facecolor=fc, edgecolor=ec, linewidth=lw))


def arrow(x1, y, x2):
    ax.add_patch(FancyArrowPatch((x1, y), (x2, y), arrowstyle="-|>",
                                 mutation_scale=12, linewidth=1.1,
                                 color="#c9c7c0", shrinkA=0, shrinkB=0))


# ------------------------------------------------------------------ 머리말
ax.text(0.62, 8.62, "실험 설계 및 지표 정의", fontsize=13, color=NAVY, va="top")
ax.text(0.62, 8.22, "유동인구 예측 정확도 개선 실험", fontsize=27, color=INK, va="top")
ax.plot([0.62, 15.38], [7.62, 7.62], color=LINE, linewidth=1.0)

# ------------------------------------------------------------------ 4단계 카드
STEPS = [
    ("문제 인식", [
        "Chronos-Bolt는 단변량 모델이라",
        "학사일정을 변수로 넣을 수 없음",
    ], "→ 방학 낙차를 과소평가"),
    ("변인 설정", [
        "예측이 나온 뒤",
        "학사일정 보정계수를 곱함",
    ], "→ 방학이면 곱하고\n     학기면 나눔"),
    ("실험 진행 (Before/After)", [
        "같은 Chronos 출력에",
        "보정 단계만 다르게 적용",
    ], "→ 확장 윈도우 8회 반복"),
    ("측정 지표", [
        "평균 절대 백분율 오차",
        "실측값 대비 산정",
    ], None),
]

cx, cw, gap, cy, ch = 0.62, 3.35, 0.47, 4.62, 2.72
for i, (title, lines, note) in enumerate(STEPS):
    x = cx + i * (cw + gap)
    card(x, cy, cw, ch)
    ax.add_patch(Circle((x + 0.42, cy + ch - 0.44), 0.19,
                        facecolor="white", edgecolor=NAVY, linewidth=1.2))
    ax.text(x + 0.42, cy + ch - 0.445, str(i + 1), fontsize=11,
            color=NAVY, ha="center", va="center")
    ax.text(x + 0.76, cy + ch - 0.30, title, fontsize=13.5, color=INK, va="top")

    yy = cy + ch - 0.92
    if i == 3:                                   # 측정 지표 카드는 HHI 자리에 MAPE
        ax.text(x + 0.30, yy + 0.06, "MAPE", fontsize=19, color=INK, va="top")
        yy -= 0.52
    for ln in lines:
        ax.text(x + 0.30, yy, ln, fontsize=11, color=MUTED, va="top")
        yy -= 0.30
    if note:
        ax.text(x + 0.30, yy - 0.16, note, fontsize=11.5, color=NAVY,
                va="top", linespacing=1.5)

    if i < 3:
        arrow(x + cw + 0.08, cy + ch / 2, x + cw + gap - 0.08)

# Before / After 배지 (3번 카드 안)
bx = cx + 2 * (cw + gap)
card(bx + 0.30, cy + 0.26, 1.32, 0.44, fc="white", ec=LINE, r=0.08)
ax.text(bx + 0.96, cy + 0.47, "Before", fontsize=10.5, color=MUTED,
        ha="center", va="center")
card(bx + 1.72, cy + 0.26, 1.32, 0.44, fc="white", ec=NAVY, lw=1.4, r=0.08)
ax.text(bx + 2.38, cy + 0.47, "After", fontsize=10.5, color=NAVY,
        ha="center", va="center")

# ------------------------------------------------------------------ 하단 설명
card(0.62, 1.92, 8.55, 2.20, fc=BG, ec=LINE)
ax.text(0.95, 3.86, "보정계수란?", fontsize=12.5, color=INK, va="top")
ax.text(0.95, 3.44, "방학 분기(Q1·Q3) 평균 유동인구를 학기 분기(Q2·Q4) 평균으로 나눈 값.",
        fontsize=11.5, color=MUTED, va="top")
ax.text(0.95, 3.10, "방학에 학생이 빠지는 폭을 하나의 숫자로 나타낸다.",
        fontsize=11.5, color=MUTED, va="top")
ax.text(0.95, 2.66, "2,296 만  ÷  2,536 만  =  0.905", fontsize=14, color=INK, va="top")
ax.text(0.95, 2.28, "→ 방학에는 학기의 90% 수준까지 줄어든다는 뜻",
        fontsize=11.5, color=NAVY, va="top")

# ------------------------------------------------------------------ 성공 기준
card(9.62, 1.92, 5.76, 2.20, fc="white", ec=NAVY, lw=1.5)
ax.text(9.98, 3.86, "성공 기준", fontsize=12, color=NAVY, va="top")
ax.text(9.98, 3.36, "예측 오차(MAPE)", fontsize=15, color=INK, va="top")
ax.text(9.98, 2.88, "8%대  →  4%대", fontsize=24, color=NAVY, va="top")
ax.text(9.98, 2.28, "보정 없이 예측했을 때의 오차를 절반 수준까지",
        fontsize=11, color=MUTED, va="top")

# ------------------------------------------------------------------ 각주
ax.text(0.62, 1.40,
        "※ 본 슬라이드는 실험 설계 및 지표 정의만 다룸 — 결과는 별도 슬라이드에서 제시",
        fontsize=11, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
