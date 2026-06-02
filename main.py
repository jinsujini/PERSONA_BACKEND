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

            action = data.get("action")
            user_message = data.get("message", "").strip()

            if action == "reset":
                conversation_history.clear()
                await websocket.send_json({"type": "reset_done"})
                continue

            if action == "summarize":
                if not conversation_history:
                    await websocket.send_json({"type": "error", "content": "대화 내역이 없어요."})
                    continue
                summary = await _summarize(conversation_history, character.name)
                await websocket.send_json({"type": "summary", "content": summary})
                continue

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


@app.websocket("/ws/group-chat")
async def group_chat(websocket: WebSocket):
    await websocket.accept()

    try:
        raw = await websocket.receive_text()
        data = json.loads(raw)
    except Exception:
        await websocket.send_json({"type": "error", "content": "Invalid init message"})
        await websocket.close()
        return

    character_ids: list[str] = data.get("character_ids", [])
    characters = [CHARACTERS[cid] for cid in character_ids if cid in CHARACTERS]

    if not characters:
        await websocket.send_json({"type": "error", "content": "No valid characters selected"})
        await websocket.close()
        return

    history: list[dict] = []

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            action = data.get("action")
            user_message = data.get("message", "").strip()

            if action == "reset":
                history.clear()
                await websocket.send_json({"type": "reset_done"})
                continue

            if action == "summarize":
                if not history:
                    await websocket.send_json({"type": "error", "content": "대화 내역이 없어요."})
                    continue
                group_history = _group_history_to_contents(history)
                names = ", ".join(c.name for c in characters)
                summary = await _summarize(group_history, names)
                await websocket.send_json({"type": "summary", "content": summary})
                continue

            if not user_message:
                await websocket.send_json({"type": "error", "content": "Empty message"})
                continue

            current_round: dict = {"user": user_message, "responses": []}

            for character in characters:
                contents = _build_group_history(history, current_round, character.id)
                full_response = ""

                try:
                    async for chunk in await client.aio.models.generate_content_stream(
                        model=MODEL,
                        contents=contents,
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
                            await websocket.send_json({
                                "type": "chunk",
                                "character_id": character.id,
                                "content": content,
                            })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "character_id": character.id,
                        "content": str(e),
                    })
                    continue

                current_round["responses"].append({
                    "character_id": character.id,
                    "content": full_response,
                })
                await websocket.send_json({
                    "type": "character_done",
                    "character_id": character.id,
                })

            history.append(current_round)
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass


def _build_group_history(
    history: list[dict],
    current_round: dict,
    character_id: str,
) -> list[types.Content]:
    contents: list[types.Content] = []

    for round_ in history:
        user_text = round_["user"]
        own_response = next(
            (r["content"] for r in round_["responses"] if r["character_id"] == character_id),
            None,
        )
        others = [r for r in round_["responses"] if r["character_id"] != character_id]

        if others:
            other_text = "\n".join(
                f"[{CHARACTERS[r['character_id']].name}]: {r['content']}" for r in others
            )
            user_text = f"{user_text}\n\n[다른 캐릭터들의 말]\n{other_text}"

        contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        if own_response:
            contents.append(types.Content(role="model", parts=[types.Part(text=own_response)]))

    user_text = current_round["user"]
    prior_responses = current_round["responses"]
    if prior_responses:
        prior_text = "\n".join(
            f"[{CHARACTERS[r['character_id']].name}]: {r['content']}" for r in prior_responses
        )
        user_text = (
            f"{user_text}\n\n"
            f"[다른 캐릭터들의 말]\n{prior_text}\n\n"
            f"위 캐릭터들과 같은 말을 반복하지 말고, 너만의 가치관과 관점에서 다른 시각을 제시해줘."
        )

    contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
    return contents


def _group_history_to_contents(history: list[dict]) -> list[types.Content]:
    """그룹 채팅 히스토리를 요약용 단순 Content 목록으로 변환."""
    contents: list[types.Content] = []
    for round_ in history:
        contents.append(types.Content(role="user", parts=[types.Part(text=round_["user"])]))
        responses_text = "\n".join(
            f"[{CHARACTERS[r['character_id']].name}]: {r['content']}"
            for r in round_["responses"]
        )
        if responses_text:
            contents.append(types.Content(role="model", parts=[types.Part(text=responses_text)]))
    return contents


async def _summarize(history: list[types.Content], character_names: str) -> str:
    SUMMARIZE_PROMPT = (
        f"다음은 사용자와 {character_names} 사이의 대화입니다. "
        "대화 내용을 한 문장으로 간결하게 한국어로 요약해줘. "
        "어떤 고민을 나눴는지 핵심만 담아줘. 줄바꿈 없이 한 줄로만 출력해."
    )
    try:
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SUMMARIZE_PROMPT,
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return response.text
    except Exception as e:
        return f"요약 중 오류가 발생했어요: {e}"
