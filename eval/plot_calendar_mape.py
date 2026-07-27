"""
학사일정 보정 전후 MAPE 비교 그림 생성.

8분기 백테스트 결과(누수 없음 — 각 예측 시점 이전 데이터로만 계수 추정)를
막대그래프 + 표 한 장으로 만든다. 발표 자료에 그대로 붙일 용도.

실행
  python eval/plot_calendar_mape.py
출력
  eval/학사일정_보정_MAPE.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False        # 한글 폰트에 마이너스 글리프가 없다

OUT = Path(__file__).resolve().parent / "학사일정_보정_MAPE.png"

# 분기, 방학여부, 보정계수, Chronos 원본 MAPE(%), 보정 후 MAPE(%)
ROWS = [
    ("2024Q2", False, 0.913,  4.23, 4.93),
    ("2024Q3", True,  0.920, 15.56, 6.36),
    ("2024Q4", False, 0.907,  0.68, 9.52),
    ("2025Q1", True,  0.922,  8.89, 0.37),
    ("2025Q2", False, 0.909,  6.76, 2.57),
    ("2025Q3", True,  0.920, 14.20, 5.12),
    ("2025Q4", False, 0.905,  9.73, 0.25),
    ("2026Q1", True,  0.915,  7.32, 1.85),
]

BLUE, ORANGE = "#2a78d6", "#eb6834"
GREEN, RED = "#1baf7a", "#d03b3b"
INK, MUTED, GRID = "#0b0b0b", "#6b6a66", "#e1e0d9"

labels = [r[0] for r in ROWS]
before = np.array([r[3] for r in ROWS])
after = np.array([r[4] for r in ROWS])
vac = np.array([r[1] for r in ROWS])

mb, ma = before.mean(), after.mean()

fig = plt.figure(figsize=(12.2, 11.6), dpi=200)
fig.patch.set_facecolor("white")
# 제목 / 요약숫자 / 그래프 / 표를 각각 독립된 행에 둔다.
# 한 행에 제목과 숫자를 같이 넣었더니 긴 부제와 겹쳤다.
gs = fig.add_gridspec(4, 1, height_ratios=[0.42, 0.5, 3.0, 2.6], hspace=0.30)

# ---------------------------------------------------------------- 제목
ax0 = fig.add_subplot(gs[0]); ax0.axis("off")
ax0.text(0, 0.95, "학사일정 보정 전후 예측 오차율(MAPE) 변화",
         fontsize=20, color=INK, va="top")
ax0.text(0, 0.24, "회기동 유동인구 · 8분기 확장 윈도우 백테스트 "
                  "(각 예측 시점 이전 데이터로만 계수 추정 — 누수 없음)",
         fontsize=11, color=MUTED, va="top")

# ---------------------------------------------------------------- 요약 숫자
axm = fig.add_subplot(gs[1]); axm.axis("off")
axm.set_xlim(0, 1); axm.set_ylim(0, 1)
for i, (lab, val, col) in enumerate([
        ("보정 없음 평균", f"{mb:.2f}%", BLUE),
        ("보정 적용 평균", f"{ma:.2f}%", ORANGE),
        ("오차 감소", f"{(ma - mb) / mb * 100:.1f}%", GREEN),
        ("개선된 분기", f"{int((after < before).sum())} / {len(ROWS)}", INK)]):
    x0 = i * 0.25
    axm.add_patch(plt.Rectangle((x0, 0.02), 0.235, 0.96,
                                facecolor="#f7f6f2", edgecolor="none"))
    axm.text(x0 + 0.022, 0.84, lab, fontsize=10.5, color=MUTED, va="top")
    axm.text(x0 + 0.022, 0.56, val, fontsize=22, color=col, va="top")

# ---------------------------------------------------------------- 막대그래프
ax = fig.add_subplot(gs[2])
x = np.arange(len(ROWS)); w = 0.36

ax.bar(x - w / 2, before, w, label="Chronos 원본 (보정 없음)", color=BLUE, zorder=3)
ax.bar(x + w / 2, after, w, label="+ 학사일정 보정", color=ORANGE, zorder=3)

for xi, (b, a) in enumerate(zip(before, after)):
    ax.text(xi - w / 2, b + 0.28, f"{b:.2f}", ha="center", fontsize=9, color=BLUE)
    ax.text(xi + w / 2, a + 0.28, f"{a:.2f}", ha="center", fontsize=9, color=ORANGE)

# 방학 분기 배경 — 효과가 어디에 몰리는지 눈으로 보이게 한다
for xi, is_vac in enumerate(vac):
    if is_vac:
        ax.axvspan(xi - 0.5, xi + 0.5, color="#f1efe8", zorder=0)

ax.set_xticks(x)
ax.set_xticklabels([f"{l}\n{'방학' if v else '학기'}" for l, v in zip(labels, vac)],
                   fontsize=10, color=INK)
ax.set_ylabel("MAPE (%)", fontsize=11, color=MUTED)
ax.set_ylim(0, max(before.max(), after.max()) * 1.18)
ax.tick_params(axis="y", labelsize=10, colors=MUTED)
ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=1)
ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#c3c2b7")
ax.legend(fontsize=10, frameon=False, loc="upper right", ncol=2)
# 축 아래(-0.155)에 두면 두 줄짜리 x라벨 다음이라 표에 가린다.
# 왼쪽 위는 2024Q2 막대가 낮아 비어 있으므로 그 안에 넣는다.
ax.text(0.006, 0.985, "회색 배경 = 방학 분기. 보정 효과가 방학에 몰린다.",
        transform=ax.transAxes, fontsize=10, color=MUTED, va="top")

# ---------------------------------------------------------------- 표
ax2 = fig.add_subplot(gs[3]); ax2.axis("off")

head = ["분기", "구분", "보정계수", "보정 없음", "보정 적용", "변화"]
body, colors = [], []
for lab, is_vac, f, b, a in ROWS:
    d = a - b
    body.append([lab, "방학" if is_vac else "학기", f"{f:.3f}",
                 f"{b:.2f}%", f"{a:.2f}%",
                 ("+" if d > 0 else "") + f"{d:.2f}%p"])
    colors.append(GREEN if d < 0 else RED)

body.append(["평균", "", "", f"{mb:.2f}%", f"{ma:.2f}%",
             f"{ma - mb:.2f}%p ({(ma - mb) / mb * 100:.1f}%)"])
colors.append(GREEN)

tb = ax2.table(cellText=body, colLabels=head, cellLoc="center",
               colWidths=[.13, .10, .13, .16, .16, .22],
               bbox=[0.06, 0.22, 0.88, 0.80])
tb.auto_set_font_size(False); tb.set_fontsize(10.5)

for (r, c), cell in tb.get_celld().items():
    cell.set_edgecolor(GRID); cell.set_linewidth(0.8)
    if r == 0:                                     # 헤더
        cell.set_facecolor("#f1efe8"); cell.set_text_props(color=INK)
        continue
    row = r - 1
    if row == len(ROWS):                           # 평균 행
        cell.set_facecolor("#faf9f5")
    elif ROWS[row][1]:                             # 방학 분기
        cell.set_facecolor("#fbfaf7")
    if c == 5:
        cell.set_text_props(color=colors[row])
    elif c == 3:
        cell.set_text_props(color=BLUE)
    elif c == 4:
        cell.set_text_props(color=ORANGE)

vac_b, vac_a = before[vac].mean(), after[vac].mean()
sem_b, sem_a = before[~vac].mean(), after[~vac].mean()
ax2.text(0.5, 0.11,
         f"방학 4분기 평균  {vac_b:.2f}% → {vac_a:.2f}%  ({(vac_a-vac_b)/vac_b*100:.0f}%)     "
         f"학기 4분기 평균  {sem_b:.2f}% → {sem_a:.2f}%  ({(sem_a-sem_b)/sem_b*100:.0f}%)",
         transform=ax2.transAxes, ha="center", fontsize=11, color=INK)
ax2.text(0.5, 0.015,
         "2024Q2·2024Q4는 원본이 이미 잘 맞힌 분기라 보정이 오히려 손해였다. "
         "평균적으로 이기지만 매 분기 이기지는 않는다.",
         transform=ax2.transAxes, ha="center", fontsize=9.5, color=MUTED)

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
print(f"  보정 없음 {mb:.2f}% -> 보정 적용 {ma:.2f}%  ({(ma-mb)/mb*100:.1f}%)")
print(f"  개선 {int((after < before).sum())}/{len(ROWS)} 분기")
