# 고정 주소표 (변경 금지)

이 표의 주소는 **확정**이다. 새 기능은 여기 있는 주소에 채워 넣고, 새 주소가 필요하면 이 문서에 먼저 추가한다.

---

## 화면

| 주소 | 목업 | 상태 | 내용 |
|---|---|---|---|
| `/` | 2p | ✅ | 역할 선택 (학생 / 사장님) |
| `/timetable.html` | 3p | ✅ | 시간표 등록 — 표 직접 입력 |
| `/home.html` | 6p | ✅ | 학생 홈 · 지금 갈 수 있는 곳 |
| `/chat.html` | 4p·5p | ✅ | 맥락 매칭 챗봇 + 단체예약 문의 |
| `/friends.html` | 7p | ✅ | 친구 시간표 겹쳐보기 |
| `/store.html?id=` | 9p·17p | ✅ | 가게 상세 + 익명 후기 |
| `/projects.html` | 19p | ✅ | 프로젝트 매칭 (학생) |
| `/stamp.html` | 13p | 🔲 | 스탬프 챌린지 |
| `/coupon.html` | 16p | 🔲 | 제휴 쿠폰 통합 |
| `/booking.html` | 12p | 🔲 | 단체예약 검색 |
| `/merchant.html` | 10p·14p·21p | ✅ | 사장님 대시보드 · 추이 · 일일보고 · 리포트 |
| `/merchant-register.html` | 15p | 🔲 | 상인 등록 (3분) |
| `/merchant-project.html` | 20p | 🔲 | 상인 과제 등록 |
| `/data.html` | — | ✅ | 회기동 상권 데이터 확인 (팀 내부용) |
| `/status.html` | — | ✅ | **모델 상태 · GPU · 추론시간 · 백테스트** |

---

## API

### 공통
| 메서드 | 주소 | 내용 |
|---|---|---|
| GET | `/api/system` | 모델 상태 · GPU 정보 · 추론 지연시간 |
| GET | `/api/backtest?category=&holdout=` | 베이스라인 대비 MAE 개선율 판정 |
| GET | `/api/hoegi/profile` | 회기동 실데이터 프로파일 |

### 점포 · 위치
| 메서드 | 주소 | 내용 |
|---|---|---|
| GET | `/api/stores` | 점포 목록 + 혼잡도 (기준점 도보시간) |
| GET | `/api/stores/{id}` | 점포 상세 |
| GET | `/api/nearby?lat=&lng=` | **현재 위치 기준 실제 도보시간** |
| GET | `/api/route?lat=&lng=&store_id=` | **앱 내 경로 안내** (턴바이턴) |
| GET | `/api/hoegi/stores` | 소상공인 상가정보 원본 |
| GET | `/download/hoegi-stores.csv` | **CSV 다운로드** (Excel 바로 열림) |

### 학생
| 메서드 | 주소 | 내용 |
|---|---|---|
| POST | `/api/chat` | 챗봇 (EXAONE→필터→Chronos→EXAONE) |
| GET | `/api/timetable/{user_id}` | 시간표 조회 |
| POST | `/api/timetable` | 시간표 저장 |
| GET | `/api/friends` | 친구 목록 |
| GET | `/api/friends/intersect?users=` | 교집합 계산 |
| GET | `/api/projects?user_id=` | 프로젝트 매칭 (BGE-M3) |

### 상인
| 메서드 | 주소 | 내용 |
|---|---|---|
| GET | `/api/merchant/dashboard/{id}` | 시간대별 유입 |
| GET | `/api/merchant/trend/{id}` | 분기 추이 예측 (Chronos) |
| GET | `/api/merchant/report/{id}` | 컨설팅 리포트 |
| POST | `/api/merchant/daily` | 일일보고 (자연어 → EXAONE) |
| POST | `/api/merchant/store` | 가게 등록 |
| POST | `/api/projects` | 과제 등록 |

### 후기 · 배치
| 메서드 | 주소 | 내용 |
|---|---|---|
| GET/POST | `/api/reviews` | 익명 후기 |
| POST | `/api/batch/predict` | Chronos 배치 (하루 4~6회) |

---

## 데이터 파일

| 파일 | 출처 | 상태 |
|---|---|---|
| `data/stores.json` | OpenStreetMap + 수기 | ✅ 453곳 (좌표 439곳) |
| `data/hoegi_timeseries.json` | 서울시 상권분석 + 제공 데이터 | ✅ 20분기·24업종 |
| `data/academic_calendar.json` | — | ⚠️ **임시값, 교체 필요** |
| `data/users.json` | 데모용 | ✅ |
| `data/reviews.json` | 데모용 | ✅ |
| `data/projects.json` | 데모용 | ✅ |
| `data/daily_reports.json` | 점주 입력 | 자동 생성 |
| `data/calibration.json` | 캘리브레이션 결과 | 자동 생성 |
