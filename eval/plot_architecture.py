"""
'우리사이' 시스템 아키텍처 — PPT 본문과 같은 톤.

참고한 스타일 (우리사이 구현 PPT):
  · 16:9, 흰 배경
  · 머리말: 로고(초록) + 구분선(초록), 그 아래 굵고 큰 검정 제목
  · 본문: 연회색 라운드 카드 + 흰 알약 라벨(남색 볼드)
  · 강조: 흰 배경 + 남색 테두리
  · 화살표: 굵은 회색
  · 서체: Pretendard (assets/fonts 에 동봉)

내용은 코드·데이터로 검증한 값만 쓴다:
  · 분산 점수 4항(관련성×신규성×혼잡×타임딜)
  · 학사일정 보정은 혼잡도에만 적용 — 예측 경로는 미반영
  · 타임딜 등록 UI는 아직 없음 -> '예정'
  · 점포 898곳 / 매출 20분기 / 유동 21분기
  · EXAONE 은 입출력만 담당(판단 없음)

실행
  python eval/plot_architecture.py
출력
  eval/시스템_아키텍처.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
for _f in sorted(_FONT_DIR.glob("Pretendard-*.otf")):
    fm.fontManager.addfont(str(_f))
_HAS = any(f.name == "Pretendard" for f in fm.fontManager.ttflist)
plt.rcParams["font.family"] = "Pretendard" if _HAS else "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "시스템_아키텍처.png"

GREEN, NAVY = "#2d7533", "#2e4c89"
INK, MUTED = "#1a1a1a", "#595959"
CARD = "#ebebeb"
GREEN_TINT, NAVY_TINT = "#e8f2e9", "#e7ecf6"
ARROW = "#9a9a9a"

# 글자 크기 — 여기만 고치면 전체가 같이 커진다
T_LOGO, T_HEAD, T_TITLE = 20, 19, 40
T_PILL, T_BODY, T_SUB, T_NOTE = 19, 18, 17, 14

W, H = 16.0, 9.0
fig = plt.figure(figsize=(W, H), dpi=170)
fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")


def card(x, y, w, h, fc=CARD, ec="none", lw=0, r=0.18):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle=f"round,pad=0.02,rounding_size={r}",
                                facecolor=fc, edgecolor=ec, linewidth=lw))


def pill(cx, y, w, text, color=NAVY, fs=None):
    ax.add_patch(FancyBboxPatch((cx - w / 2, y), w, 0.52,
                                boxstyle="round,pad=0.02,rounding_size=0.26",
                                facecolor="white", edgecolor="none"))
    ax.text(cx, y + 0.26, text, fontsize=fs or T_PILL, color=color,
            fontweight="bold", ha="center", va="center")


def chevron(x, y, w=0.60):
    ax.add_patch(FancyArrowPatch((x, y), (x + w, y), arrowstyle="-|>",
                                 mutation_scale=30, linewidth=6,
                                 color=ARROW, shrinkA=0, shrinkB=0))


def route(points, color, lw=3.0, ls="-"):
    for a, b in zip(points[:-2], points[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, linewidth=lw,
                linestyle=ls, solid_capstyle="round", zorder=1)
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>",
                                 mutation_scale=22, linewidth=lw, color=color,
                                 linestyle=ls, shrinkA=0, shrinkB=0, zorder=1))


# ------------------------------------------------------------ 머리말
ax.text(0.38, 8.82, "우리사이", fontsize=T_LOGO, color=GREEN,
        fontweight="bold", va="top")
ax.text(1.85, 8.80, "시스템 구성", fontsize=T_HEAD, color=INK, va="top")
ax.plot([0.38, 15.62], [8.40, 8.40], color=GREEN, linewidth=2.0)

ax.text(0.38, 8.10, "학생과 상인이 하나의 엔진을 공유합니다",
        fontsize=T_TITLE, color=INK, fontweight="bold", va="top")

# ------------------------------------------------------------ 열 제목
ax.text(2.10, 6.92, "① 입력", fontsize=T_BODY, color=MUTED, ha="center", va="top")
ax.text(8.05, 6.92, "② 공통 엔진", fontsize=T_BODY, color=MUTED, ha="center", va="top")
ax.text(13.92, 6.92, "③ 양면 출력", fontsize=T_BODY, color=MUTED, ha="center", va="top")

# ------------------------------------------------------------ ① 입력
# 세로 배치는 위(6.55)에서 아래로 쌓는다. 카드끼리 0.34 씩 띄운다.
IN = [("학생", ["시간표 · 위치 · 질문"]),
      ("학사일정", ["방학 · 시험 · 축제"]),
      ("상권 데이터", ["점포 898곳 · 16업종", "매출 20분기 · 유동 21분기"])]
y = 6.55
for title, lines in IN:
    h = 1.20 if len(lines) == 1 else 1.66
    y -= h
    card(0.38, y, 3.45, h)
    pill(1.32, y + h - 0.62, 1.72, title)
    ty = y + h - 0.86
    for ln in lines:
        ax.text(0.68, ty, ln, fontsize=T_SUB, color=INK, va="top")
        ty -= 0.46
    y -= 0.34

chevron(4.05, 3.90)

# ------------------------------------------------------------ ② 공통 엔진
# 바깥 0.90~6.65 안에 세 장을 0.20 간격으로 넣는다.
card(4.90, 0.90, 6.35, 5.75)

# A. EXAONE  5.15 ~ 6.55
card(5.16, 5.15, 5.83, 1.40, fc="white")
pill(6.75, 5.93, 3.30, "EXAONE 3.5 · 자연어")
ax.text(5.46, 5.70, "질문 이해  ·  문장 생성", fontsize=T_SUB, color=INK, va="top")
ax.text(5.46, 5.32, "입출력만 담당 · 판단 없음", fontsize=T_NOTE, color=MUTED, va="top")

# B. 추천 로직  2.75 ~ 4.95
card(5.16, 2.68, 5.83, 2.27, fc="white", ec=NAVY, lw=2.2)
pill(6.38, 4.33, 2.50, "추천 로직")
ax.text(5.46, 4.06, "시간 제약     도보+체류 ≤ 공강", fontsize=T_SUB, color=INK, va="top")
ax.text(5.46, 3.66, "분산 점수     관련성×신규성×혼잡×타임딜",
        fontsize=T_SUB - 2.5, color=INK, va="top")
ax.text(5.46, 3.26, "동선 체이닝   라운드로빈 회전", fontsize=T_SUB, color=INK, va="top")
ax.text(5.46, 2.94, "→ 신규 업종으로 확장", fontsize=T_SUB, color=GREEN,
        fontweight="bold", va="top")

# C. Chronos  1.05 ~ 2.55
card(5.16, 1.05, 5.83, 1.50, fc="white")
pill(6.66, 1.93, 3.12, "Chronos-Bolt · 예측")
ax.text(5.46, 1.70, "학사일정 보정 · 혼잡도", fontsize=T_SUB, color=INK, va="top")
ax.text(5.46, 1.34, "예측 경로는 미반영 · 모두 zero-shot", fontsize=T_NOTE,
        color=MUTED, va="top")

chevron(11.44, 5.55)
chevron(11.44, 2.30)

# ------------------------------------------------------------ ③ 출력
card(12.28, 4.05, 3.34, 2.50, fc=GREEN_TINT)
pill(13.16, 5.93, 1.62, "학생", color=GREEN)
for i, t in enumerate(["추천 카드", "동선 제안", "단체 예약"]):
    ax.text(12.58, 5.62 - i * 0.48, f"· {t}", fontsize=T_SUB, color=INK, va="top")
ax.text(12.58, 4.28, "→ 공강에 한 곳 더", fontsize=T_SUB, color=GREEN,
        fontweight="bold", va="top")

card(12.28, 0.90, 3.34, 2.75, fc=NAVY_TINT)
pill(13.16, 3.03, 1.62, "상인", color=NAVY)
for i, t in enumerate(["수요 예측 그래프", "학생 목소리 리포트", "타임딜 등록 (예정)"]):
    ax.text(12.58, 2.72 - i * 0.48, f"· {t}", fontsize=T_SUB,
            color=MUTED if "예정" in t else INK, va="top")
ax.text(12.58, 1.20, "→ 방학 · 유휴시간 대응", fontsize=T_SUB, color=NAVY,
        fontweight="bold", va="top")

route([(15.20, 4.05), (15.20, 3.88), (15.20, 3.72)], GREEN, lw=3.2)
ax.text(15.02, 3.90, "후기", fontsize=T_NOTE, color=GREEN,
        fontweight="bold", ha="right", va="center")

# ------------------------------------------------------------ 순환 — 아래 레인
route([(12.28, 1.55), (11.92, 1.55), (11.92, 0.38), (2.10, 0.38), (2.10, 1.35)],
      GREEN, lw=3.0)
ax.add_patch(FancyBboxPatch((4.45, 0.12), 5.40, 0.52,
                            boxstyle="round,pad=0.02,rounding_size=0.26",
                            facecolor=GREEN_TINT, edgecolor="none", zorder=2))
ax.text(7.15, 0.38, "후기가 다음 추천의 근거로", fontsize=T_NOTE, color=GREEN,
        fontweight="bold", ha="center", va="center", zorder=3)

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"저장: {OUT}")
