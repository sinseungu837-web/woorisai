"""
입력 제거(ablation) 결과 요약 그림.

eval/ablation.py 가 만든 ablation_result.json 을 읽어
"각 입력을 빼면 얼마나 나빠지는가"를 한 장으로 만든다.

실행
  python eval/ablation.py        # 먼저 실험을 돌려 json 을 만든다
  python eval/plot_ablation.py
출력
  eval/입력제거_실험.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
OUT = HERE / "입력제거_실험.png"
R = json.loads((HERE / "ablation_result.json").read_text(encoding="utf-8"))

BLUE, ORANGE = "#2a78d6", "#eb6834"
GREEN, RED = "#1baf7a", "#d03b3b"
INK, MUTED, GRID = "#0b0b0b", "#6b6a66", "#e1e0d9"

fig = plt.figure(figsize=(12.4, 10.2), dpi=200)
fig.patch.set_facecolor("white")
gs = fig.add_gridspec(3, 1, height_ratios=[0.34, 2.05, 2.4], hspace=0.34)

# ------------------------------------------------------------------ 제목
ax0 = fig.add_subplot(gs[0]); ax0.axis("off")
ax0.text(0, 0.95, "입력을 하나씩 빼면 결과가 얼마나 나빠지는가",
         fontsize=20, color=INK, va="top")
ax0.text(0, 0.20, "우리사이 플랫폼 · 입력 제거(ablation) 실험 4종 "
                  "— 전부 고정 시나리오라 몇 번 돌려도 같은 값이 나온다",
         fontsize=11, color=MUTED, va="top")

# ------------------------------------------------------------------ 요약 표
ax1 = fig.add_subplot(gs[1]); ax1.axis("off")

cal, tt, rv, ch = R["calendar"], R["timetable"], R["reviews"], R["chaining"]
head = ["뺀 입력", "무엇을 재나", "뺀 모델", "넣은 모델", "차이"]
body = [
    ["학사일정", "유동인구 예측 오차 (MAPE)",
     f"{cal['off']:.2f}%", f"{cal['on']:.2f}%",
     f"{(cal['on']-cal['off'])/cal['off']*100:.1f}%"],
    ["  └ 방학 분기만", "유동인구 예측 오차 (MAPE)",
     f"{cal['vac_off']:.2f}%", f"{cal['vac_on']:.2f}%",
     f"{(cal['vac_on']-cal['vac_off'])/cal['vac_off']*100:.0f}%"],
    ["시간표", "갈 수 있는데 안 보여준 비율",
     f"{tt['loss_rate']:.1f}%", "0.0%", f"{-tt['loss_rate']:.1f}%p"],
    ["시간표", "시나리오당 추천 가능 후보 수",
     f"{tt['cand_without']:.0f}곳", f"{tt['cand_with']:.0f}곳",
     f"+{tt['cand_with']-tt['cand_without']:.0f}곳"],
    ["학생 후기", "사장님이 받는 비전 카드",
     "0장", f"{rv['cards']}장", f"+{rv['cards']}장"],
    ["학생 후기", "근거로 붙는 후기 원문",
     "0건", f"{rv['evidence']}건", f"+{rv['evidence']}건"],
    ["체이닝+분산+회전", "추천 업종 집중도 (HHI)",
     f"{ch['단일']['hhi']:,}", f"{ch['체이닝+분산+회전']['hhi']:,}",
     f"{(ch['체이닝+분산+회전']['hhi']-ch['단일']['hhi'])/ch['단일']['hhi']*100:.1f}%"],
    ["체이닝+분산+회전", "노출된 업종 수",
     f"{ch['단일']['cats']}개", f"{ch['체이닝+분산+회전']['cats']}개",
     f"+{ch['체이닝+분산+회전']['cats']-ch['단일']['cats']}개"],
]
good = [True, True, True, True, True, True, True, True]

tb = ax1.table(cellText=body, colLabels=head, cellLoc="center",
               colWidths=[.19, .30, .15, .15, .15],
               bbox=[0.02, 0.02, 0.96, 0.96])
tb.auto_set_font_size(False); tb.set_fontsize(10.5)
for (r, c), cell in tb.get_celld().items():
    cell.set_edgecolor(GRID); cell.set_linewidth(0.8)
    if r == 0:
        cell.set_facecolor("#f1efe8"); cell.set_text_props(color=INK)
        continue
    if c in (0, 1):
        cell.get_text().set_ha("left")
        cell._text.set_x(0.03)
    if r % 2 == 0:
        cell.set_facecolor("#fbfaf7")
    if c == 2:
        cell.set_text_props(color=BLUE)
    elif c == 3:
        cell.set_text_props(color=ORANGE)
    elif c == 4:
        cell.set_text_props(color=GREEN if good[r - 1] else RED)

# ------------------------------------------------------------------ D 사다리
ax2 = fig.add_subplot(gs[2])
order = ["단일", "체이닝", "체이닝+분산", "체이닝+분산+회전"]
labels = ["단일 추천\n(체이닝 없음)", "+ 체이닝\n(거리순)",
          "+ 분산 점수", "+ 라운드로빈\n(현재 방식)"]
hhi = [ch[k]["hhi"] for k in order]
food = [ch[k]["food"] for k in order]
cats = [ch[k]["cats"] for k in order]
x = np.arange(len(order))

bars = ax2.bar(x, hhi, 0.5, color=[RED, RED, "#e8a33c", GREEN], zorder=3)
for xi, (h, f, c) in enumerate(zip(hhi, food, cats)):
    ax2.text(xi, h + 60, f"{h:,}", ha="center", fontsize=12, color=INK)
    ax2.text(xi, h / 2, f"요식업 {f:.0f}%\n업종 {c}개", ha="center", va="center",
             fontsize=10, color="white")

ax2.axhline(2500, color=MUTED, linestyle="--", linewidth=1, zorder=2)
ax2.text(len(order) - 0.45, 2560, "HHI 2,500 = 고집중 시장 기준",
         ha="right", fontsize=9.5, color=MUTED)

ax2.set_xticks(x); ax2.set_xticklabels(labels, fontsize=10.5, color=INK)
ax2.set_ylabel("업종 HHI (낮을수록 고르게 분산)", fontsize=11, color=MUTED)
ax2.set_ylim(0, max(hhi) * 1.25)
ax2.tick_params(axis="y", labelsize=10, colors=MUTED)
ax2.grid(axis="y", color=GRID, linewidth=0.8, zorder=1); ax2.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax2.spines[s].set_visible(False)
ax2.spines["bottom"].set_color("#c3c2b7")
ax2.set_title("D. 체이닝을 단계별로 켜면 — 요청 600건 시뮬레이션",
              fontsize=13, color=INK, loc="left", pad=12)
ax2.text(0.0, -0.20,
         "체이닝만으로는 분산이 안 된다(2,733 → 2,777). 가까운 순으로 이어 붙이면 또 밥집·카페가 걸리기 때문이다.\n"
         "분산 점수는 요식업 비중을 67%→23%로 낮추지만 희소 업종이 새로 독점해 HHI는 그대로다. "
         "회전까지 넣어야 실제로 고르게 퍼진다.",
         transform=ax2.transAxes, fontsize=10, color=MUTED, va="top")

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
