"""
'유동인구 예측 정확도 개선 실험' — 결과 (단순 버전).

핵심 수치는 한 번만 크게 보여주고, 근거 세 가지를 아래 한 줄로 받친다.
8분기 상세는 부록으로 뺀다.

실행
  python eval/plot_calendar_result3.py
출력
  eval/실험결과_유동인구_단순.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험결과_유동인구_단순.png"

NAVY, INK, MUTED = "#1f3b73", "#1a1a1a", "#6b6a66"
LINE, CARD, BG = "#e2e0da", "#fbfaf8", "#f6f5f2"
GREEN, RED, GRAY = "#1f7a4d", "#b03030", "#c2c0ba"

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")


def card(x, y, w, h, fc=CARD, ec=LINE, lw=1.1, r=0.12):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle=f"round,pad=0.02,rounding_size={r}",
                                facecolor=fc, edgecolor=ec, linewidth=lw))


# ------------------------------------------------------------------ 머리말
ax.text(0.62, 8.62, "실험 결과", fontsize=13, color=NAVY, va="top")
ax.text(0.62, 8.22, "유동인구 예측 정확도 개선 실험", fontsize=27, color=INK, va="top")
ax.plot([0.62, 15.38], [7.62, 7.62], color=LINE, linewidth=1.0)

# ------------------------------------------------------------------ 핵심 수치
card(0.62, 4.05, 14.76, 3.10, fc=BG)

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

# 막대 — 크기 차이를 눈으로
BX, BW = 8.40, 5.90
for i, (label, val, col) in enumerate(
        [("보정 없음", 8.42, GRAY), ("보정 적용", 3.87, NAVY)]):
    by = 5.72 - i * 0.92
    ax.text(BX, by + 0.62, label, fontsize=12, color=MUTED, va="center")
    ax.add_patch(Rectangle((BX, by), BW * val / 8.42, 0.44,
                           facecolor=col, edgecolor="none"))
    ax.text(BX + BW * val / 8.42 + 0.20, by + 0.22, f"{val:.2f}%",
            fontsize=15, color=INK, va="center")

# ------------------------------------------------------------------ 근거 3가지
FACTS = [
    ("효과가 방학에 집중",
     ["방학 분기   11.49%  →  3.43%      -70%",
      "학기 분기    5.35%  →  4.32%      -19%"],
     "학사일정이 원인이라는 설명과 일치", NAVY),
    ("8분기 중 6분기 개선",
     ["2분기(2024Q2·2024Q4)는 오히려 악화",
      "원본 예측이 이미 정확했던 분기"],
     "평균은 이기지만 매번 이기지는 않음", RED),
    ("검증 방식",
     ["확장 윈도우 1스텝 예측 8회",
      "매 시점 이전 데이터로만 계수 재계산"],
     "미래 정보를 쓰지 않음", MUTED),
]

fx, fw, fgap, fy, fh = 0.62, 4.79, 0.20, 1.55, 2.10
for i, (title, lines, note, ncol) in enumerate(FACTS):
    x = fx + i * (fw + fgap)
    card(x, fy, fw, fh)
    ax.text(x + 0.32, fy + fh - 0.32, title, fontsize=14, color=INK, va="top")
    yy = fy + fh - 0.92
    for ln in lines:
        ax.text(x + 0.32, yy, ln, fontsize=11.5, color=MUTED, va="top")
        yy -= 0.34
    ax.text(x + 0.32, yy - 0.10, f"→ {note}", fontsize=12, color=ncol, va="top")

# ------------------------------------------------------------------ 각주
ax.text(0.62, 1.15,
        "※ 8분기 확장 윈도우 예측의 평균값 — 분기별 상세는 부록에서 제시",
        fontsize=11, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
