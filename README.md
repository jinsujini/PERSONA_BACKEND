# PERSONA Backend

다양한 캐릭터의 가치관과 시선으로 고민을 나눌 수 있는 AI 채팅 서비스의 백엔드입니다.

## 기술 스택

- **Python 3.11**
- **FastAPI** — WebSocket 기반 실시간 채팅
- **Google Gemini 2.5 Flash** — AI 응답 생성
- **google-genai** — Gemini API 클라이언트

## 캐릭터

| ID | 이름 | 핵심 가치 |
|---|---|---|
| `harry` | Harry Potter | 용기, 우정, 희생 |
| `sherlock` | Sherlock Holmes | 논리, 분석, 객관성 |
| `little_prince` | Little Prince | 진심, 관계, 공감 |

## 시작하기

### 환경 변수 설정

```
GEMINI_API_KEY=your_api_key_here
```

[Google AI Studio](https://aistudio.google.com)에서 API 키를 발급받으세요.

### 설치 및 실행

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
uvicorn main:app --reload
```

## API

### `GET /characters`

사용 가능한 캐릭터 목록을 반환합니다.

```json
[
  { "id": "harry", "name": "Harry Potter" },
  { "id": "sherlock", "name": "Sherlock Holmes" },
  { "id": "little_prince", "name": "Little Prince" }
]
```

---

### `WS /ws/chat/{character_id}`

한 캐릭터와 1:1 채팅합니다.

**메시지 전송**
```json
{ "message": "요즘 너무 힘들어." }
```

**액션**
```json
{ "action": "reset" }      // 대화 초기화
{ "action": "summarize" }  // 대화 요약
```

**서버 응답**
```json
{ "type": "chunk", "content": "..." }       // 스트리밍 청크
{ "type": "done" }                          // 응답 완료
{ "type": "reset_done" }                    // 초기화 완료
{ "type": "summary", "content": "..." }     // 요약 결과
{ "type": "error", "content": "..." }       // 오류
```

---

### `WS /ws/group-chat`

여러 캐릭터가 함께 참여하는 그룹 채팅입니다.

**1. 연결 후 캐릭터 목록 전송**
```json
{ "character_ids": ["harry", "sherlock"] }
```

**2. 메시지 전송**
```json
{ "message": "친구와 싸웠어." }
```

각 캐릭터가 순서대로 응답하며, 뒤에 응답하는 캐릭터는 앞 캐릭터의 말을 보고 다른 관점으로 답합니다.

**서버 응답**
```json
{ "type": "chunk", "character_id": "harry", "content": "..." }
{ "type": "character_done", "character_id": "harry" }
{ "type": "chunk", "character_id": "sherlock", "content": "..." }
{ "type": "character_done", "character_id": "sherlock" }
{ "type": "done" }
```

**액션** (단체 채팅도 동일)
```json
{ "action": "reset" }
{ "action": "summarize" }
```
