# PERSONA Backend

FastAPI 기반 WebSocket 채팅 서버

## 스택

- Python 3.11 / FastAPI / Google Gemini 2.5 Flash

## 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

`.env` 파일에 `GEMINI_API_KEY` 설정 필요

---

## API

### GET `/characters`

사용 가능한 캐릭터 목록 반환

```json
[{ "id": "harry", "name": "Harry Potter" }, ...]
```

---

### WS `/ws/chat/{character_id}`

1:1 채팅

**클라이언트 → 서버**

| 용도 | 형식 |
|---|---|
| 메시지 전송 | `{ "message": "..." }` |
| 대화 초기화 | `{ "action": "reset" }` |
| 대화 요약 | `{ "action": "summarize" }` |

**서버 → 클라이언트**

| type | 설명 | 추가 필드 |
|---|---|---|
| `chunk` | 스트리밍 응답 | `content` |
| `done` | 응답 완료 | - |
| `reset_done` | 초기화 완료 | - |
| `summary` | 요약 결과 | `content` |
| `error` | 오류 | `content` |

---

### WS `/ws/group-chat`

다중 캐릭터 채팅 — 캐릭터들이 순서대로 응답하며 서로 다른 관점을 제시

**1. 연결 직후 캐릭터 목록 전송**

```json
{ "character_ids": ["harry", "sherlock", "little_prince"] }
```

**2. 이후 동일하게 메시지 / reset / summarize 사용**

**서버 → 클라이언트**

| type | 설명 | 추가 필드 |
|---|---|---|
| `chunk` | 스트리밍 응답 | `character_id`, `content` |
| `character_done` | 캐릭터 응답 완료 | `character_id` |
| `done` | 전체 라운드 완료 | - |
| `reset_done` | 초기화 완료 | - |
| `summary` | 요약 결과 | `content` |
| `error` | 오류 | `character_id`(선택), `content` |
