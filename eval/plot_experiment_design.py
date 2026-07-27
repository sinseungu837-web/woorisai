"""
'Chronos 예측 — 학사일정 보정 전/후' 실험 설계를 PPT 한 페이지로.

16:9 한 장에 실험 조건 · 데이터 분할 · 지표 정의 · 성공 기준을 담는다.

실행
  python eval/plot_experiment_design.py
출력
  eval/실험설계_학사일정.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "실험설계_학사일정.png"

INK, MUTED, LINE = "#0b0b0b", "#6b6a66", "#d8d6cf"
BLUE, ORANGE, GREEN, RED = "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"
SOFT = "#f7f6f2"

fig = plt.figure(figsize=(16, 9), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")


def panel(x, y, w, h, title):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                facecolor="white", edgecolor=LINE, linewidth=1.1))
    ax.text(x + 0.22, y + h - 0.30, title, fontsize=13, color=INK, va="top")


# ------------------------------------------------------------------ 제목
ax.text(0.55, 8.62, "Chronos 예측 — 학사일정 보정 전/후 실험 설계",
        fontsize=25, color=INK, va="top")
ax.text(0.55, 8.02,
        "Chronos-Bolt는 단변량이라 학사일정을 feature로 넣을 수 없다. "
        "따라서 '변수 투입 유무'가 아니라 '예측 후 보정 단계의 유무' 비교다.",
        fontsize=12, color=MUTED, va="top")

# ------------------------------------------------------- ① 실험 조건
panel(0.55, 3.55, 5.0, 4.05, "①  실험 조건 (arm)")
arms = [
    ("A0", "Chronos 원본", "before · 기준", MUTED),
    ("A1", "× 이분법 계수 (방학/학기)", "after · 현재 방식", ORANGE),
    ("A2", "× 연속 계수 (vacation_share)", "after · 개선안", ORANGE),
    ("B0", "naive (직전 분기값)", "하한 기준", MUTED),
    ("B1", "계절 naive (전년 동분기)", "진짜 경쟁자", RED),
]
yy = 6.90
for tag, how, role, col in arms:
    ax.add_patch(Rectangle((0.80, yy - 0.34), 0.52, 0.42, facecolor=SOFT, edgecolor="none"))
    ax.text(1.06, yy - 0.13, tag, fontsize=11.5, color=INK, ha="center", va="center")
    ax.text(1.48, yy - 0.02, how, fontsize=11.5, color=INK, va="center")
    ax.text(1.48, yy - 0.29, role, fontsize=10, color=col, va="center")
    yy -= 0.62

ax.text(0.80, 3.98,
        "B1이 핵심 — 유동인구에서 계절 naive가 MAPE 1.18%를 낸 적이 있다.\n"
        "이걸 못 이기면 Chronos+보정이라는 복잡한 구성을 쓸 이유가 없다.",
        fontsize=10, color=RED, va="top")

# ------------------------------------------------------- ② 데이터 분할
panel(5.85, 3.55, 4.55, 4.05, "②  데이터 분할 — 누수 차단")

ax.text(6.10, 7.00, "확장 윈도우 · 1스텝 예측 · 8회 반복",
        fontsize=11, color=INK, va="top")

# 확장 윈도우 도식 — 위에서 아래로 그린다(패널 제목과 겹치지 않게)
base_x, cell = 6.18, 0.34
for row in range(4):
    y = 6.55 - row * 0.30
    n_hist = 4 + row
    for i in range(n_hist):
        ax.add_patch(Rectangle((base_x + i * cell, y), cell - 0.05, 0.21,
                               facecolor="#cfe0f5", edgecolor="none"))
    ax.add_patch(Rectangle((base_x + n_hist * cell, y), cell - 0.05, 0.21,
                           facecolor=ORANGE, edgecolor="none"))
ax.text(base_x, 5.48, "학습 구간(파랑)          예측(주황)",
        fontsize=9.5, color=MUTED, va="top")

# 마이너스 기호(U+2212)는 Malgun Gothic 에 없어 네모로 나온다 -> ASCII 하이픈
ax.text(6.10, 5.20,
        "t 시점 예측 시\n"
        "  · Chronos 입력  = 처음 ~ t-1\n"
        "  · 보정계수 추정 = 처음 ~ t-1     ← 매 시점 재추정\n"
        "  · 정답 비교      = t 실측",
        fontsize=10.5, color=INK, va="top", linespacing=1.6)

ax.add_patch(Rectangle((6.10, 3.86), 4.05, 0.52, facecolor=SOFT, edgecolor="none"))
ax.text(6.28, 4.24,
        "검증 2024Q2~2025Q4 (7개)    ·    테스트 2026Q1 (1개)",
        fontsize=10.5, color=INK, va="top")
ax.text(6.28, 3.98, "최종 목표는 2026Q1. 나머지는 우연이 아님을 보이는 근거.",
        fontsize=9.5, color=MUTED, va="top")

# ------------------------------------------------------- ③ 지표 정의
panel(10.70, 3.55, 4.75, 4.05, "③  지표 정의")

ax.text(10.95, 7.02, "주 지표", fontsize=11, color=ORANGE, va="top")
ax.text(10.95, 6.72,
        "MAPE  =  (100/n) · Σ |y − ŷ| / |y|\n"
        "Skill  =  1 - MAE_model / MAE_B1",
        fontsize=11, color=INK, va="top", linespacing=1.9, family="monospace")
ax.text(10.95, 5.92,
        "MAPE 단독으로는 '3.87%가 좋은 값인가'에 답할 수 없다.\n"
        "Skill(계절 naive 대비)이 판단 가능한 숫자다.",
        fontsize=9.5, color=MUTED, va="top", linespacing=1.5)

ax.text(10.95, 5.36, "보조 지표", fontsize=11, color=ORANGE, va="top")
subs = [
    ("층화 MAPE", "방학 4분기 / 학기 4분기 각각 → H2 검증"),
    ("방향 정확도", "증감 부호가 실측과 일치한 비율"),
    ("승률", "|오차_A1| < |오차_A0| 인 분기 비율"),
    ("계수 안정성", "std(계수) / mean(계수)"),
]
yy = 5.06
for name, desc in subs:
    ax.text(10.95, yy, f"· {name}", fontsize=10.5, color=INK, va="top")
    ax.text(12.30, yy, desc, fontsize=10, color=MUTED, va="top")
    yy -= 0.33

ax.text(10.95, 3.78,
        "가설 H2 — 효과는 방학 분기에 집중된다.\n"
        "H1만 맞고 H2가 틀리면 메커니즘 설명이 무효다.",
        fontsize=9.5, color=INK, va="top", linespacing=1.5)

# ------------------------------------------------------- ④ 성공 기준
panel(0.55, 1.25, 14.90, 2.05, "④  성공 기준 — 결과 보기 전 확정")

crits = [
    ("MAPE (A1 vs A0)", "15% 이상 감소"),
    ("Skill vs 계절 naive", "0보다 큼"),
    ("층화 (H2)", "방학 개선 > 학기 개선"),
    ("승률", "8분기 중 5개 이상"),
    ("계수 변동계수", "0.05 미만"),
    ("테스트 2026Q1", "검증 구간과 같은 방향"),
]
for i, (name, crit) in enumerate(crits):
    x = 0.85 + i * 2.44
    ax.add_patch(Rectangle((x, 1.92), 2.28, 0.76, facecolor=SOFT, edgecolor="none"))
    ax.text(x + 0.16, 2.55, name, fontsize=10, color=MUTED, va="top")
    ax.text(x + 0.16, 2.26, crit, fontsize=11.5, color=INK, va="top")

ax.text(0.85, 1.72,
        "반증 조건 — 다음 중 하나면 가설 기각으로 보고한다:  "
        "계절 naive를 못 이김  ·  방학 개선율 ≤ 학기 개선율  ·  "
        "계수 변동계수 ≥ 0.05  ·  승률 4/8 이하",
        fontsize=10.5, color=RED, va="top")

# ------------------------------------------------------- 하단 재현
ax.text(0.55, 0.86,
        "재현   python eval/calendar_backtest.py --arms A0,A1,A2,B0,B1 --test 2026Q1        "
        "통제변수   chronos-bolt-base · 예측길이 1 · median(0.5) · seed 42 · "
        "코로나 구간(2021~22) 제외 버전 병행 산출",
        fontsize=9.5, color=MUTED, va="top")
ax.text(0.55, 0.50,
        "n=8은 통계 검정력이 낮다. p값을 주 근거로 쓰지 않고 효과 크기·승률·층화 패턴을 함께 보고한다.",
        fontsize=9.5, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
