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
                types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
            )
            trimmed_history = conversation_history[-MAX_HISTORY:]

            full_response = ""

            async for chunk in client.aio.models.generate_content_stream(
                model="gemini-2.0-flash",
                contents=trimmed_history,
                config=types.GenerateContentConfig(
                    system_instruction=character.system_prompt,
                    max_output_tokens=1024,
                ),
            ):
                if chunk.text:
                    full_response += chunk.text
                    await websocket.send_json({"type": "chunk", "content": chunk.text})

            conversation_history.append(
                types.Content(role="model", parts=[types.Part.from_text(text=full_response)])
            )
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
