# GPU 서버 구동 가이드

RTX A6000(48GB) 기준. 세 모델 모두 **추가 학습 없이** 사전학습 가중치를 그대로 쓴다.

---

## 1. 설치

```bash
# CUDA 버전에 맞춰 torch 먼저 (예: CUDA 12.1)
pip install torch --index-url https://download.pytorch.org/whl/cu121

pip install -r requirements-gpu.txt
```

## 2. 실행

```bash
WOORISAI_REAL=1 uvicorn main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell:
```powershell
$env:WOORISAI_REAL=1; uvicorn main:app --host 0.0.0.0 --port 8000
```

첫 실행 때 모델을 내려받는다 (EXAONE 약 16GB). 이후에는 캐시에서 로드된다.

## 3. 확인

브라우저에서 **`/status.html`** 를 연다. 다음이 실시간으로 보인다.

- 실제 모델 구동 중 / 규칙 기반 모드
- GPU 이름 · 전체 메모리 · 모델 점유량 · 여유
- 모델별 로드 상태, 호출 횟수, 최근·평균 추론 시간(ms)
- 백테스트 버튼 → 베이스라인 대비 MAE 개선율 판정

---

## 메모리 예상

| 모델 | 크기 | dtype | VRAM |
|---|---|---|---|
| EXAONE 3.5 | 7.8B | bfloat16 | 약 16GB |
| Chronos-Bolt (base) | 205M | bfloat16 | 약 0.4GB |
| BGE-M3 | 568M | fp16 | 약 1.1GB |
| **합계** | | | **약 17.5GB** |

48GB 중 **약 30GB 여유**. KV-캐시와 동시 요청까지 충분하다.

메모리가 빠듯하면 `app/ai.py` 의 `MODEL_ID` 를 바꾼다.

```python
MODEL_ID = "LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct"   # 약 5GB
```

---

## 안전장치

모델 로드나 추론이 실패하면 **자동으로 규칙 기반으로 내려간다.** 서비스가 죽지 않고,
실패 사유는 `/status.html` 의 각 모델 카드에 빨간 박스로 표시된다.

즉 GPU가 없어도 데모는 항상 돌아간다.

---

## 모델별 사용 방식

### EXAONE 3.5 — 채널
instruction-tuned 모델이라 **chat template 을 거쳐야** 지시를 따른다.
`do_sample=False` 로 두어 같은 입력에 항상 같은 출력이 나오게 했다 (재현성).

| 기능 | 프롬프트 |
|---|---|
| 조건 파싱 | 자연어 → JSON (`minutes`, `purpose`, `people`) |
| 추천 문장 | 가게 목록 → 2~3문장 안내 |
| 일일 보고 파싱 | 사장님 문장 → JSON (`sales_change_pct`, `customers`, `level`) |
| 컨설팅 리포트 | 예측+후기 → 3~4문장 |
| 후기 분류 | 후기 목록 → 카테고리별 건수 + 요약 + 제안 |

프롬프트에 **"주어진 정보 밖의 내용은 지어내지 않는다"** 를 명시해 환각을 억제했다.

### Chronos-Bolt — 본체
회기동 분기별 매출 시계열(20포인트)을 컨텍스트로 넣어 다음 분기를 예측한다.
`predict_quantiles` 로 중앙값과 10/90분위를 함께 받아 예측 구간도 표시한다.

**입력은 학습이 아니다.** 가중치는 변하지 않고, forward pass 한 번만 돈다.

### BGE-M3 — 매칭
과제 텍스트와 학생 프로필을 각각 벡터로 만들어 코사인 유사도를 계산한다.
벡터는 텍스트별로 캐싱하므로, 같은 과제를 여러 학생과 비교해도 인코딩은 1회다.

---

## 백테스트 (검증 설계)

`/status.html` 의 버튼 또는 API로 실행한다.

```
GET /api/backtest?category=한식음식점&holdout=4
```

- 마지막 4분기를 가려놓고 예측
- 베이스라인 = 직전 4분기 평균 (AI 없이 세울 수 있는 기준선)
- **판정: 개선율 ≥ 15% 이면 통과**

결과를 보기 전에 기준을 먼저 정해둔 것이라, 결과가 나쁘게 나와도 그대로 보고하면 된다.

---

## 외부 서비스

| 용도 | 서비스 | 키 | 비용 |
|---|---|---|---|
| 도보 경로·소요시간 | Valhalla (FOSSGIS) | 불필요 | 무료 |
| 현재 위치 | 브라우저 Geolocation | 불필요 | 무료 |

Geolocation 은 **HTTPS 또는 localhost** 에서만 동작한다.
외부에 공개할 때는 반드시 HTTPS 를 붙여야 위치 기능이 작동한다.

---

## 트러블슈팅 — EXAONE 로드는 되는데 추론이 실패하는 경우

`transformers` 버전이 EXAONE 공개 시점(2024년 말)보다 훨씬 최신이면,
EXAONE의 원격 코드(`modeling_exaone.py`, HuggingFace 캐시에 자동 다운로드됨)가
최신 `transformers` 내부 API와 어긋나 추론 단계에서 실패할 수 있다.
**로드는 성공하고 실제 호출(`generate`)에서만 터지는 게 특징**이다.

실제로 `transformers==5.14.1` 에서 겪은 두 가지 문제와 해결:

### 증상 1 — `AttributeError` (메시지 없음)

```
File ".../transformers/generation/utils.py", line 2534, in generate
    batch_size = inputs_tensor.shape[0]
File ".../transformers/tokenization_utils_base.py", line 291, in __getattr__
    raise AttributeError
```

**원인**: `apply_chat_template(..., return_tensors="pt")` 가 순수 텐서가 아니라
`BatchEncoding`(딕셔너리형)을 반환하는데, `.shape` 로 텐서처럼 접근해서 발생.
`app/ai.py` 의 `Exaone._chat()` 에서 `return_dict=True` 로 명시하고
`**encoded` 로 언패킹하도록 이미 반영돼 있다 (재발 시 이 부분을 확인).

### 증상 2 — `TypeError: create_causal_mask() got an unexpected keyword argument 'input_embeds'`

**원인**: EXAONE 원격 코드가 옛날 인자명으로 호출하는데, 새 `transformers` 는
인자명이 바뀌었다(`input_embeds`→`inputs_embeds`) + 인자 하나가 아예 사라졌다(`cache_position`).

**진단 방법** (import 없이 파일을 직접 읽어서 비교 — 노트북 커널에 캐시된
옛 모듈과 뒤섞이는 걸 피할 수 있다):

```python
exa = ("/root/.cache/huggingface/modules/transformers_modules/"
       "LGAI_hyphen_EXAONE/EXAONE_hyphen_3_dot_5_hyphen_7_dot_8B_hyphen_Instruct/"
       "<revision_hash>/modeling_exaone.py")   # 로그의 revision 해시로 교체
lines = open(exa, encoding="utf-8").read().splitlines()
for i, ln in enumerate(lines):
    if "create_causal_mask" in ln:
        print("\n".join(lines[i:i+12])); break

mu = "<site-packages 경로>/transformers/masking_utils.py"
msrc = open(mu, encoding="utf-8").read().splitlines()
for i, ln in enumerate(msrc):
    if ln.strip().startswith("def create_causal_mask"):
        print("\n".join(msrc[i:i+15])); break
```

**해결** — 원격 캐시 파일을 직접 패치 (일반 텍스트라 수정 가능):

```python
exa = "<위와 동일한 경로>/modeling_exaone.py"
src = open(exa, encoding="utf-8").read()

src = src.replace("input_embeds=inputs_embeds,", "inputs_embeds=inputs_embeds,")

start = src.index("create_causal_mask(")
end = src.index(")", start)
block = src[start:end]
new_block = "\n".join(l for l in block.split("\n")
                      if l.strip() != "cache_position=cache_position,")
src = src[:start] + new_block + src[end:]
open(exa, "w", encoding="utf-8").write(src)
```

패치 후 uvicorn 재시작 필요 (모듈이 프로세스 시작 시 한 번만 로드되므로).

### ⚠️ 이 패치는 캐시에만 있다

`~/.cache/huggingface/modules/...` 는 **모델 캐시**이지 이 저장소의 일부가 아니다.
다음 경우 패치가 사라지고 같은 오류가 재발한다:
- 캐시를 지우거나(`rm -rf ~/.cache/huggingface`)
- 다른 서버로 새로 배포하거나
- EXAONE을 재다운로드하는 경우

재발하면 위 진단→패치 과정을 그대로 반복하면 된다 (원인이 같으면 패치도 같다).
근본 해결을 원하면 `transformers` 를 EXAONE 공개 시점에 가까운 버전으로 고정하는
방법도 있지만, 그러면 BGE-M3 가 요구하는 최신 `dtype` 인자 지원이 깨질 수 있어
(실제로 `transformers==4.51.3` 에서 `FlagEmbedding` 이 `dtype` 인자 오류로 실패한
전례가 있다) 버전 고정보다는 이 패치를 유지하는 쪽을 권장한다.
