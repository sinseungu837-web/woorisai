"""
'유동인구 예측 정확도 개선 실험' — 결과 (핵심 수치 + 8분기 그래프).

위쪽은 대표 수치 하나, 아래쪽은 8회 예측 결과를 막대그래프로.
글자는 최소로 두고 방학 분기를 배경색으로만 구분한다.

실행
  python eval/plot_calendar_result4.py
출력
  eval/실험결과_유동인구_그래프.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험결과_유동인구_그래프.png"

NAVY, INK, MUTED = "#1f3b73", "#1a1a1a", "#6b6a66"
LINE, BG, GRID = "#e2e0da", "#f6f5f2", "#e6e4de"
GRAY = "#c2c0ba"

QUARTERS = ["2024Q2", "2024Q3", "2024Q4", "2025Q1",
            "2025Q2", "2025Q3", "2025Q4", "2026Q1"]
VAC = [False, True, False, True, False, True, False, True]
BEFORE = [4.23, 15.56, 0.68, 8.89, 6.76, 14.20, 9.73, 7.32]
AFTER = [4.93, 6.36, 9.52, 0.37, 2.57, 5.12, 0.25, 1.85]

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")

# ------------------------------------------------------------------ 머리말
ax.text(0.62, 8.62, "실험 결과", fontsize=13, color=NAVY, va="top")
ax.text(0.62, 8.22, "유동인구 예측 정확도 개선 실험", fontsize=27, color=INK, va="top")
ax.plot([0.62, 15.38], [7.62, 7.62], color=LINE, linewidth=1.0)

# ------------------------------------------------------------------ 핵심 수치
ax.add_patch(FancyBboxPatch((0.62, 4.05), 14.76, 3.10,
                            boxstyle="round,pad=0.02,rounding_size=0.12",
                            facecolor=BG, edgecolor=LINE, linewidth=1.1))

ax.text(1.15, 6.80, "예측 오차 (MAPE)", fontsize=14, color=MUTED, va="top")
ax.text(1.15, 6.22, "8.42%", fontsize=46, color=GRAY, va="top")
ax.text(3.55, 6.10, "→", fontsize=34, color=MUTED, va="top")
ax.text(4.55, 6.22, "3.87%", fontsize=46, color=NAVY, va="top")

ax.add_patch(FancyBboxPatch((1.15, 4.42), 3.10, 0.60,
                            boxstyle="round,pad=0.02,rounding_size=0.30",
                            facecolor=NAVY, edgecolor="none"))
ax.text(2.70, 4.72, "오차 54.0% 감소", fontsize=14, color="white",
        ha="center", va="center")
ax.text(4.60, 4.86, "목표였던 4%대 아래로 진입", fontsize=13, color=INK, va="top")

BX, BW = 8.40, 5.90
for i, (label, val, col) in enumerate(
        [("보정 없음", 8.42, GRAY), ("보정 적용", 3.87, NAVY)]):
    by = 5.72 - i * 0.92
    ax.text(BX, by + 0.62, label, fontsize=12, color=MUTED, va="center")
    ax.add_patch(Rectangle((BX, by), BW * val / 8.42, 0.44,
                           facecolor=col, edgecolor="none"))
    ax.text(BX + BW * val / 8.42 + 0.20, by + 0.22, f"{val:.2f}%",
            fontsize=15, color=INK, va="center")

# ------------------------------------------------------------------ 8분기 그래프
ax.text(0.62, 3.92, "8회 예측 결과", fontsize=14, color=INK, va="top")
ax.text(2.85, 3.88, "회색 배경 = 방학 분기", fontsize=11, color=MUTED, va="top")

# 범례
ax.add_patch(Rectangle((11.55, 3.66), 0.26, 0.20, facecolor=GRAY, edgecolor="none"))
ax.text(11.92, 3.76, "보정 없음", fontsize=11, color=MUTED, va="center")
ax.add_patch(Rectangle((13.30, 3.66), 0.26, 0.20, facecolor=NAVY, edgecolor="none"))
ax.text(13.67, 3.76, "보정 적용", fontsize=11, color=MUTED, va="center")

cax = fig.add_axes([0.043, 0.168, 0.915, 0.200])
cax.set_facecolor("white")
x = np.arange(len(QUARTERS))
w = 0.34

for i, v in enumerate(VAC):
    if v:
        cax.axvspan(i - 0.5, i + 0.5, color=BG, zorder=0)

cax.bar(x - w / 2, BEFORE, w, color=GRAY, zorder=3)
cax.bar(x + w / 2, AFTER, w, color=NAVY, zorder=3)

cax.set_xticks(x)
cax.set_xticklabels(QUARTERS, fontsize=10.5, color=MUTED)
cax.set_ylim(0, 17.5)
cax.set_yticks([0, 5, 10, 15])
cax.set_yticklabels(["0", "5", "10", "15%"], fontsize=10, color=MUTED)
cax.grid(axis="y", color=GRID, linewidth=0.8, zorder=1)
cax.set_axisbelow(True)
for s in ("top", "right", "left"):
    cax.spines[s].set_visible(False)
cax.spines["bottom"].set_color("#c9c7c0")
cax.tick_params(axis="both", length=0)

# ------------------------------------------------------------------ 한 줄 설명
ax.text(0.62, 0.90,
        "방학 분기에서 오차가 가장 크게 줄었다 — 학사일정이 원인이라는 설명과 일치",
        fontsize=13, color=NAVY, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
