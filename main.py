import json
import os

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from characters import CHARACTERS

load_dotenv()

app = FastAPI(title="Persona Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중에는 전체 허용, 배포 시 프론트엔드 도메인으로 변경
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MAX_HISTORY = 20  # 최근 N개 메시지만 컨텍스트로 유지


@app.get("/characters")
def get_characters():
    return [
        {"id": char.id, "name": char.name}
        for char in CHARACTERS.values()
    ]


@app.websocket("/ws/chat/{character_id}")
async def chat(websocket: WebSocket, character_id: str):
    await websocket.accept()

    character = CHARACTERS.get(character_id)
    if not character:
        await websocket.send_json({
            "type": "error",
            "content": f"Unknown character: '{character_id}'. Available: {list(CHARACTERS.keys())}",
        })
        await websocket.close()
        return

    conversation_history: list[dict] = []

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            user_message = data.get("message", "").strip()
            if not user_message:
                await websocket.send_json({"type": "error", "content": "Empty message"})
                continue

            conversation_history.append({"role": "user", "content": user_message})

            # 컨텍스트 창 관리: 최근 MAX_HISTORY개 메시지만 유지
            trimmed_history = conversation_history[-MAX_HISTORY:]

            full_response = ""

            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=character.system_prompt,
                messages=trimmed_history,
            ) as stream:
                for text_chunk in stream.text_stream:
                    full_response += text_chunk
                    await websocket.send_json({"type": "chunk", "content": text_chunk})

            conversation_history.append({"role": "assistant", "content": full_response})

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
