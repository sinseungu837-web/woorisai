"""
'유동 인구 예측 정확도 개선 실험' — 결과 비교 분석 슬라이드.

설계 슬라이드와 같은 형식(회색 카드 + 알약 라벨 + 남색 강조).
수치는 전부 8분기 백테스트 실측값.

실행
  python eval/plot_calendar_result.py
출력
  eval/실험결과_유동인구.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험결과_유동인구.png"

NAVY, INK, MUTED = "#3b4ba8", "#1a1a1a", "#5f5e5a"
CARD, DARK, GREEN, RED = "#ebebeb", "#a6a6a6", "#1f7a4d", "#b03030"

# 분기, 구분, 보정 없음, 보정 적용
ROWS = [
    ("2024Q2", "학기", 4.23, 4.93),
    ("2024Q3", "방학", 15.56, 6.36),
    ("2024Q4", "학기", 0.68, 9.52),
    ("2025Q1", "방학", 8.89, 0.37),
    ("2025Q2", "학기", 6.76, 2.57),
    ("2025Q3", "방학", 14.20, 5.12),
    ("2025Q4", "학기", 9.73, 0.25),
    ("2026Q1", "방학", 7.32, 1.85),
]

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")


def card(x, y, w, h, fc=CARD, r=0.10):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle=f"round,pad=0.02,rounding_size={r}",
                                facecolor=fc, edgecolor="none"))


def pill(x, y, w, text, fs=12):
    ax.add_patch(FancyBboxPatch((x, y), w, 0.46,
                                boxstyle="round,pad=0.02,rounding_size=0.23",
                                facecolor="white", edgecolor="none"))
    ax.text(x + w / 2, y + 0.22, text, fontsize=fs, color=INK,
            ha="center", va="center")


# ------------------------------------------------------------------ 머리말
ax.text(0.15, 8.90, "우리사이", fontsize=14, color=GREEN, va="top")
ax.text(1.35, 8.88, "|  검증 결과", fontsize=13, color=INK, va="top")
ax.plot([0.15, 15.85], [8.52, 8.52], color=GREEN, linewidth=1.4)

ax.text(0.15, 8.30, "실험 결과 비교 분석", fontsize=30, color=INK, va="top")
ax.text(0.15, 7.55, "유동 인구 예측 정확도 개선 실험", fontsize=19, color=INK, va="top")

# ------------------------------------------------------------------ 카드 4개
cx, cw, gap, cy, ch = 0.15, 3.72, 0.12, 4.55, 2.45
for i in range(4):
    card(cx + i * (cw + gap), cy, cw, ch)

# 1. 전체 결과
x = cx
pill(x + 0.22, cy + ch - 0.62, 1.85, "1. 전체 결과")
ax.text(x + 0.30, cy + ch - 0.95, "보정 없음", fontsize=12.5, color=MUTED, va="top")
ax.text(x + 2.10, cy + ch - 0.95, "8.42%", fontsize=13.5, color=INK, va="top")
ax.text(x + 0.30, cy + ch - 1.35, "보정 적용", fontsize=12.5, color=MUTED, va="top")
ax.text(x + 2.10, cy + ch - 1.35, "3.87%", fontsize=13.5, color=INK, va="top")
ax.text(x + 0.30, cy + ch - 1.92, "-> 오차 54.0% 감소", fontsize=13, color=NAVY, va="top")

# 2. 층화 분석
x = cx + (cw + gap)
pill(x + 0.22, cy + ch - 0.62, 1.85, "2. 층화 분석")
ax.text(x + 0.30, cy + ch - 0.95, "방학  11.49%  ->  3.43%", fontsize=12.5, color=INK, va="top")
ax.text(x + 0.30, cy + ch - 1.30, "학기   5.35%  ->  4.32%", fontsize=12.5, color=INK, va="top")
ax.text(x + 0.30, cy + ch - 1.87, "-> 효과가 방학에 집중", fontsize=13, color=NAVY, va="top")
ax.text(x + 0.30, cy + ch - 2.17, "   (방학 -70% / 학기 -19%)", fontsize=11.5, color=NAVY, va="top")

# 3. 승률
x = cx + 2 * (cw + gap)
pill(x + 0.22, cy + ch - 0.62, 1.55, "3. 승률")
ax.text(x + 0.30, cy + ch - 0.95, "8분기 중 6분기 개선", fontsize=12.5, color=INK, va="top")
ax.text(x + 0.30, cy + ch - 1.30, "2분기는 오히려 악화", fontsize=12.5, color=RED, va="top")
ax.text(x + 0.30, cy + ch - 1.87, "-> 평균적으로 이기지만", fontsize=13, color=NAVY, va="top")
ax.text(x + 0.30, cy + ch - 2.17, "   매 분기 이기지는 않음", fontsize=13, color=NAVY, va="top")

# 4. 목표 달성
x = cx + 3 * (cw + gap)
pill(x + 0.22, cy + ch - 0.62, 1.95, "4. 목표 달성")
ax.text(x + 0.30, cy + ch - 0.95, "목표    8%대 -> 4%대", fontsize=12.5, color=MUTED, va="top")
ax.text(x + 0.30, cy + ch - 1.30, "결과    8.42% -> 3.87%", fontsize=12.5, color=INK, va="top")
ax.text(x + 0.30, cy + ch - 1.87, "-> 목표 달성", fontsize=14, color=GREEN, va="top")

# ------------------------------------------------------------------ 대표값
# 8분기를 다 보여주지 않고 평균만 막대로 보여준다.
# 분기별 상세는 부록으로 빼고, 여기서는 크기 차이가 한눈에 들어오게 한다.
card(0.15, 0.90, 9.55, 3.20)
pill(0.42, 3.52, 1.85, "대표값")

BAR_X, BAR_MAX = 2.45, 6.30
for i, (label, val, col) in enumerate(
        [("보정 없음", 8.42, "#9a9a9a"), ("보정 적용", 3.87, NAVY)]):
    by = 2.72 - i * 0.78
    ax.text(0.62, by + 0.23, label, fontsize=13, color=INK, va="center")
    ax.add_patch(Rectangle((BAR_X, by), BAR_MAX * val / 8.42, 0.46,
                           facecolor=col, edgecolor="none"))
    ax.text(BAR_X + BAR_MAX * val / 8.42 + 0.20, by + 0.23, f"{val:.2f}%",
            fontsize=15, color=INK, va="center")

ax.plot([0.62, 9.25], [1.62, 1.62], color="#d2d2d2", linewidth=0.9)
ax.text(0.62, 1.28, "방학 분기", fontsize=12, color=MUTED, va="center")
ax.text(2.45, 1.28, "11.49%  ->  3.43%", fontsize=12.5, color=INK, va="center")
ax.text(5.90, 1.28, "-70%", fontsize=12.5, color=GREEN, va="center")
ax.text(0.62, 0.86, "학기 분기", fontsize=12, color=MUTED, va="center")
ax.text(2.45, 0.86, "5.35%  ->  4.32%", fontsize=12.5, color=INK, va="center")
ax.text(5.90, 0.86, "-19%", fontsize=12.5, color=GREEN, va="center")

# ------------------------------------------------------------------ 결론 박스
card(10.00, 0.90, 5.85, 3.00, fc=DARK, r=0.22)
ax.text(10.45, 3.58, "결과", fontsize=17, color="white", va="top")
ax.text(10.45, 3.02, ": 예측 오차(MAPE)", fontsize=15, color="white", va="top")
ax.text(10.75, 2.35, "8.42%  ->  3.87%", fontsize=25, color=NAVY, va="top")
ax.text(10.45, 1.66, "목표였던 4%대 아래로 진입", fontsize=13, color="white", va="top")
ax.text(10.45, 1.30, "방학 분기에서 오차가 가장 크게 줄어,", fontsize=11.5, color="white", va="top")
ax.text(10.45, 1.02, "학사일정이 원인이라는 설명과 일치", fontsize=11.5, color="white", va="top")

ax.text(0.15, 0.60,
        "※ 8분기 확장 윈도우 예측의 평균값. 8분기 중 6분기 개선, "
        "2분기(2024Q2·2024Q4)는 원본이 이미 정확해 보정이 손해 — 분기별 상세는 부록.",
        fontsize=10.5, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
