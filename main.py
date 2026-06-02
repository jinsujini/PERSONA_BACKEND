import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

from characters import CHARACTERS

load_dotenv()

app = FastAPI(title="Persona Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MAX_HISTORY = 20
MODEL = "gemini-2.5-flash"
GENERATE_CONFIG = dict(max_output_tokens=1024, thinking_config=types.ThinkingConfig(thinking_budget=0))


@app.get("/characters")
def get_characters():
    return [{"id": char.id, "name": char.name} for char in CHARACTERS.values()]


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

    conversation_history: list[types.Content] = []

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

            conversation_history.append(
                types.Content(role="user", parts=[types.Part(text=user_message)])
            )
            trimmed_history = conversation_history[-MAX_HISTORY:]
            full_response = ""

            try:
                async for chunk in await client.aio.models.generate_content_stream(
                    model=MODEL,
                    contents=trimmed_history,
                    config=types.GenerateContentConfig(
                        system_instruction=character.system_prompt,
                        **GENERATE_CONFIG,
                    ),
                ):
                    try:
                        content = chunk.text
                    except Exception:
                        continue
                    if content:
                        content = content.replace("\n", " ")
                        full_response += content
                        await websocket.send_json({"type": "chunk", "content": content})
            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)})
                continue

            conversation_history.append(
                types.Content(role="model", parts=[types.Part(text=full_response)])
            )
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
