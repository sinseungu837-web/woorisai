"""
'유동인구 예측 정확도 개선 실험' — 결과 비교 분석 (설계 페이지와 같은 형식).

8분기 결과를 다 늘어놓지 않고 대표값만 보여준다.
분기별 상세는 부록으로 뺀다.

실행
  python eval/plot_calendar_result2.py
출력
  eval/실험결과_유동인구_카드.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험결과_유동인구_카드.png"

NAVY, INK, MUTED = "#1f3b73", "#1a1a1a", "#6b6a66"
LINE, CARD, BG = "#e2e0da", "#fbfaf8", "#f6f5f2"
GREEN, RED, GRAY = "#1f7a4d", "#b03030", "#b9b7b1"

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")


def card(x, y, w, h, fc=CARD, ec=LINE, lw=1.1, r=0.12):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle=f"round,pad=0.02,rounding_size={r}",
                                facecolor=fc, edgecolor=ec, linewidth=lw))


# ------------------------------------------------------------------ 머리말
ax.text(0.62, 8.62, "실험 결과 비교 분석", fontsize=13, color=NAVY, va="top")
ax.text(0.62, 8.22, "유동인구 예측 정확도 개선 실험", fontsize=27, color=INK, va="top")
ax.plot([0.62, 15.38], [7.62, 7.62], color=LINE, linewidth=1.0)

# ------------------------------------------------------------------ 카드 4개
STEPS = [
    ("전체 결과", [("보정 없음", "8.42%"), ("보정 적용", "3.87%")],
     "→ 오차 54.0% 감소", NAVY),
    ("층화 분석", [("방학 분기", "11.49% → 3.43%"), ("학기 분기", "5.35% → 4.32%")],
     "→ 효과가 방학에 집중", NAVY),
    ("승률", [("개선", "8분기 중 6분기"), ("악화", "2분기")],
     "→ 평균은 이기지만\n     매번 이기지는 않음", RED),
    ("목표 달성", [("목표", "8%대 → 4%대"), ("결과", "3.87%")],
     "→ 목표 달성", GREEN),
]

cx, cw, gap, cy, ch = 0.62, 3.35, 0.47, 4.62, 2.72
for i, (title, pairs, note, ncol) in enumerate(STEPS):
    x = cx + i * (cw + gap)
    card(x, cy, cw, ch)
    ax.add_patch(Circle((x + 0.42, cy + ch - 0.44), 0.19,
                        facecolor="white", edgecolor=NAVY, linewidth=1.2))
    ax.text(x + 0.42, cy + ch - 0.445, str(i + 1), fontsize=11,
            color=NAVY, ha="center", va="center")
    ax.text(x + 0.76, cy + ch - 0.30, title, fontsize=13.5, color=INK, va="top")

    yy = cy + ch - 0.98
    for label, value in pairs:
        ax.text(x + 0.30, yy, label, fontsize=11, color=MUTED, va="top")
        ax.text(x + 1.32, yy, value, fontsize=12, color=INK, va="top")
        yy -= 0.36
    ax.text(x + 0.30, yy - 0.22, note, fontsize=12, color=ncol,
            va="top", linespacing=1.5)

# ------------------------------------------------------------------ 대표값 막대
card(0.62, 1.92, 8.55, 2.20, fc=BG)
ax.text(0.95, 3.86, "대표값 — 8분기 예측의 평균", fontsize=12.5, color=INK, va="top")

BX, BW = 2.75, 5.35
for i, (label, val, col) in enumerate(
        [("보정 없음", 8.42, GRAY), ("보정 적용", 3.87, NAVY)]):
    by = 3.02 - i * 0.68
    ax.text(0.95, by + 0.20, label, fontsize=11.5, color=MUTED, va="center")
    ax.add_patch(Rectangle((BX, by), BW * val / 8.42, 0.40,
                           facecolor=col, edgecolor="none"))
    ax.text(BX + BW * val / 8.42 + 0.18, by + 0.20, f"{val:.2f}%",
            fontsize=14, color=INK, va="center")

ax.text(0.95, 2.16, "→ 방학 분기에서 오차가 가장 크게 줄어, 학사일정이 원인이라는 설명과 일치",
        fontsize=11.5, color=NAVY, va="top")

# ------------------------------------------------------------------ 결론
card(9.62, 1.92, 5.76, 2.20, fc="white", ec=NAVY, lw=1.5)
ax.text(9.98, 3.86, "결과", fontsize=12, color=NAVY, va="top")
ax.text(9.98, 3.36, "예측 오차(MAPE)", fontsize=15, color=INK, va="top")
ax.text(9.98, 2.88, "8.42%  →  3.87%", fontsize=24, color=NAVY, va="top")
ax.text(9.98, 2.28, "목표였던 4%대 아래로 진입", fontsize=11.5, color=MUTED, va="top")

# ------------------------------------------------------------------ 각주
ax.text(0.62, 1.40,
        "※ 8분기 확장 윈도우 예측의 평균값 — 분기별 상세는 부록에서 제시",
        fontsize=11, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
