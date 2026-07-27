# -*- coding: utf-8 -*-
"""
발표 슬라이드 6장 "실행 및 결과" — 실측값으로 채운 표 PDF.

  python eval/make_slide6_pdf.py --out ../슬라이드6_실행및결과.pdf
"""
import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

SERIF, SANS = "HYSMyeongJo-Medium", "HYGothic-Medium"
pdfmetrics.registerFont(UnicodeCIDFont(SERIF))
pdfmetrics.registerFont(UnicodeCIDFont(SANS))

NAVY = colors.HexColor("#1F3864")
GREEN = colors.HexColor("#2E9F6B")
BAD = colors.HexColor("#B85042")
GRAY = colors.HexColor("#6B7280")
LINE = colors.HexColor("#D8DEE6")
BOX = colors.HexColor("#EEF2F8")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], fontName=SANS, fontSize=17,
                    textColor=NAVY, spaceAfter=2, leading=22)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontName=SERIF, fontSize=9,
                     textColor=GRAY, alignment=TA_CENTER, spaceAfter=12)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName=SANS, fontSize=11.5,
                    textColor=NAVY, spaceBefore=12, spaceAfter=5)
BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontName=SERIF, fontSize=9,
                      leading=14, spaceAfter=4)
NOTE = ParagraphStyle("NOTE", parent=BODY, fontSize=8, textColor=GRAY, leading=12)
KEY = ParagraphStyle("KEY", parent=ss["Normal"], fontName=SANS, fontSize=11,
                     textColor=colors.white, leading=16)


def table(data, widths, size=8.2, head=NAVY):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), SANS),
        ("FONTNAME", (0, 1), (-1, -1), SERIF),
        ("FONTSIZE", (0, 0), (-1, -1), size),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), head),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
    ]))
    return t


def build(out: Path):
    doc = SimpleDocTemplate(str(out), pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="슬라이드 6 — 실행 및 결과")
    S = []
    S.append(Paragraph("6. 실행 및 결과", H1))
    S.append(Paragraph("평가: ① 비교 대상 대비 결과  ② 실험 조건이 재현 가능하게 기술", SUB))

    # ---------- 6-1 ----------
    S.append(Paragraph("6-1. 실험 설계 — Ablation(제거 실험) 3종", H2))
    S.append(Paragraph("변인을 하나씩 빼서 \"그게 없으면 얼마나 나빠지나\"를 보인다.", NOTE))
    S.append(table([
        ["실험", "비교 대상 (baseline)", "측정 지표", "문제정의 연결"],
        ["A. 학사일정 효과",
         "Chronos 예측만 vs\n예측 + 학사일정 보정",
         "유동인구 예측 MAE", "시간 구조성"],
        ["B. 체이닝 효과",
         "거리순 / 인기순 추천 vs\n체이닝(탐색슬롯) 추천",
         "신규업종 노출률,\n추천 업종 HHI", "발견 실패(다양화)"],
        ["C. 신규성 변수",
         "관련도만 vs\n관련도 × 신규성",
         "추천 업종 분산(HHI),\n노출된 업종 수", "접촉 업종 수"],
    ], [30 * mm, 54 * mm, 46 * mm, 50 * mm]))
    S.append(Paragraph("※ 실험 A 주의 — <b>Chronos-Bolt는 단변량 모델이라 학사일정을 feature로 넣을 수 없다.</b> "
                       "그래서 '넣은 모델 vs 뺀 모델'이 아니라, <b>예측을 낸 뒤 학사일정 맥락으로 보정하는 단계를 "
                       "붙였다 / 안 붙였다</b>의 비교다.", NOTE))

    # ---------- 6-2 ----------
    S.append(Paragraph("6-2. 결과표 (전부 실측)", H2))
    rows = [
        ["지표", "베이스라인", "우리 모델", "개선", "사전 성공기준", "판정"],
        ["유동인구 예측 MAE", "1,812,830\n(MAPE 8.42%)", "862,142\n(MAPE 3.87%)",
         "-52.4%", "-15% 이상", "달성"],
        ["신규업종 노출률", "거리순 28.0%", "49.7%", "+21.7%p", "+60%p 이상", "미달"],
        ["추천 업종 HHI(분산)", "거리순 2,368", "1,504", "-36.5%", "baseline 대비 하락", "달성"],
        ["슬롯 추출 F1", "정규식 90.0", "91.1", "+1.1", "0.85 이상", "달성"],
    ]
    t = table(rows, [34 * mm, 30 * mm, 27 * mm, 22 * mm, 37 * mm, 20 * mm])
    t.setStyle(TableStyle([
        ("TEXTCOLOR", (5, 1), (5, 1), GREEN), ("TEXTCOLOR", (5, 2), (5, 2), BAD),
        ("TEXTCOLOR", (5, 3), (5, 3), GREEN), ("TEXTCOLOR", (5, 4), (5, 4), GREEN),
        ("ALIGN", (3, 0), (5, -1), "CENTER"),
    ]))
    S.append(t)
    S.append(Paragraph("<b>4개 지표 중 3개 달성, 1개 미달.</b> 미달한 신규업종 노출률은 사후 분석 결과 "
                       "<b>목표 설정 자체가 구조적 상한을 넘어섰다</b> — 추천 3곳 중 2곳은 학생 요청에 답해야 하므로 "
                       "탐색슬롯 1곳으로 낼 수 있는 최대 상승폭이 약 33%p다(목표는 +60%p).", BODY))

    # 베이스라인 4종
    S.append(Paragraph("베이스라인 4종 비교 (실험 B·C)", NOTE))
    S.append(table([
        ["추천 방식", "추천 업종 HHI", "신규업종 노출률", "노출 업종 수"],
        ["랜덤", "2,266", "33.7%", "10종"],
        ["거리순 (주 baseline)", "2,368", "28.0%", "6종"],
        ["인기순 (혼잡도 높은 순)", "2,362", "36.0%", "8종"],
        ["우리 (체이닝 + 신규성)", "1,504", "49.7%", "12종"],
    ], [50 * mm, 40 * mm, 45 * mm, 45 * mm]))

    S.append(PageBreak())

    # ---------- 6-3 ----------
    S.append(Paragraph("6-3. 재현 가능성", H2))
    S.append(table([
        ["항목", "기재 내용"],
        ["모델 / 버전", "EXAONE 3.5 7.8B-Instruct  /  Chronos-Bolt (base)  /  시드 42\n"
                    "파인튜닝 없음 (zero-shot), 그리디 디코딩(do_sample=False)"],
        ["데이터 기간 / 분할",
         "유동인구·점포·임대료 2021Q1~2026Q1 (21분기, 해커톤 제공)\n"
         "추정매출 2021Q1~2025Q4 (20분기, 서울 열린데이터 OA-15572)\n"
         "생활인구 2017.01~2025.08 (104개월, OA-14991)\n"
         "시간순 split — 학습 2021Q1~2024Q1 / 검증 2024Q2~2026Q1(8분기 확장 윈도우)"],
        ["베이스라인 정의",
         "랜덤 / 거리순(주 baseline) / 인기순(혼잡도 높은 순, 네이버지도 대용)\n"
         "예측 baseline — 학사일정 보정을 적용하지 않은 Chronos 원본 출력"],
        ["실험 조건",
         "추천 실험: 요청 100회 × 4방식 = 1,200건 노출, 후보 880곳(도보 12분 이내) 16업종\n"
         "쿼리셋 9종 용도(식사30·카페20·스터디10·술10·선물8·인쇄7·급한일7·생활5·레저3)\n"
         "슬롯 평가: 정답 라벨 40문항, 지연 p50 4.51s / p95 6.21s\n"
         "챗봇 평가: 20종 입력 × 3회 반복(편차 0)"],
        ["재현 명령",
         "curl '<서버>/api/backtest/augmentation?n_test=8'\n"
         "python eval/eval_chat.py --base <서버> --runs 3"],
    ], [28 * mm, 152 * mm], size=7.8))

    # ---------- 핵심 문장 ----------
    S.append(Spacer(1, 8))
    S.append(Paragraph("이 장에서 반드시 말할 것", H2))
    box = Table([[Paragraph(
        "<b>\"4개 지표 중 3개 사전 목표 달성, 1개 미달.\"</b><br/><br/>"
        "<b>\"학사일정 보정을 빼면 예측 오차(MAE)가 110% 나빠진다\"</b> "
        "— 862,142 → 1,812,830<br/>"
        "<font size=8>(반대로 말하면 보정을 붙여 오차를 52.4% 줄였다. 8분기 중 6분기에서 개선.)</font>",
        KEY)]], colWidths=[180 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    S.append(box)
    S.append(Spacer(1, 6))
    S.append(Paragraph("미달을 먼저 말하면 사전 기준의 진정성이 증명된다. "
                       "신규업종 노출률 미달은 '못 한 것'이 아니라 '목표를 구조적 상한보다 높게 잡은 것'이므로, "
                       "그 사실을 함께 밝히는 편이 방어된다.", NOTE))

    # ---------- 부록: 실험 A 상세 ----------
    S.append(Paragraph("[부록] 실험 A 상세 — 8분기 전 구간 결과", H2))
    S.append(table([
        ["분기", "구분", "보정계수", "Chronos 원본", "보정 후", "실측", "원본 오차", "보정 오차"],
        ["2024Q2", "학기", "0.913", "23,986,176", "26,281,174", "25,046,790", "4.23%", "4.93%"],
        ["2024Q3", "방학", "0.920", "24,772,608", "22,798,844", "21,436,406", "15.56%", "6.36%"],
        ["2024Q4", "학기", "0.907", "22,806,528", "25,148,175", "22,962,536", "0.68%", "9.52%"],
        ["2025Q1", "방학", "0.922", "22,806,528", "21,022,748", "20,944,815", "8.89%", "0.37%"],
        ["2025Q2", "학기", "0.909", "21,495,808", "23,646,265", "23,054,424", "6.76%", "2.57%"],
        ["2025Q3", "방학", "0.920", "22,413,312", "20,630,506", "19,625,573", "14.20%", "5.12%"],
        ["2025Q4", "학기", "0.905", "20,709,376", "22,883,327", "22,941,117", "9.73%", "0.25%"],
        ["2026Q1", "방학", "0.915", "22,151,168", "20,258,985", "20,641,163", "7.32%", "1.85%"],
        ["평균", "", "", "", "", "", "8.42%", "3.87%"],
    ], [17 * mm, 13 * mm, 18 * mm, 27 * mm, 27 * mm, 27 * mm, 23 * mm, 23 * mm], size=7.4))
    S.append(Paragraph("<b>보정 방법</b> — ① 예측 시점 <b>이전 데이터만</b> 사용해 계수 추정(누수 차단) "
                       "② 방학분기(Q1·Q3) 평균 ÷ 학기분기(Q2·Q4) 평균 = 보정계수 "
                       "③ 방학분기는 곱하고, 학기분기는 나눈다. 계수가 5년간 0.905~0.922로 안정적이라 "
                       "(방학 효과 일관되게 -8~9%) 보정이 작동했다.", NOTE))
    S.append(Paragraph("<b>왜 통했나</b> — Chronos 예측은 20.7M~24.8M 사이에서 밋밋한 데 비해 실측은 "
                       "19.6M~25.0M로 크게 오르내린다. Chronos가 <b>계절 낙차를 과소평가</b>하는데"
                       "(20분기로는 4분기 주기를 학습할 표본 부족), 학사일정이 그 낙차를 되돌려준 것이다.", NOTE))

    doc.build(S)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../슬라이드6_실행및결과.pdf")
    a = ap.parse_args()
    print("생성 완료 ->", Path(build(Path(a.out))).resolve())
