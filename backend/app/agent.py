import os
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from app.tools import (
    get_medication_by_name,
    check_inventory,
    check_prescription_requirement,
    check_allergy_concerns_and_ingredients,
    submit_customer_feedback,
)

SYSTEM_PROMPT = """You are an AI pharmacist assistant for a retail pharmacy chain. You help customers in Hebrew or English.

Hard rules:
1) Provide factual information only. Never diagnose. Never recommend what to take. Never encourage purchases.
2) If the user asks for advice (e.g., “what should I take”, “is this safe for me”, “can I combine”, pregnancy, symptoms), refuse medical advice and redirect to a licensed pharmacist/doctor or emergency services if severe.
3) You may explain label-style dosage/usage instructions and active ingredients as written in medication records.
4) Use tools to answer questions about medications, inventory, prescription requirements, ingredients, allergies and feedback.
5) Do not invent medication data or stock. If missing/ambiguous, ask a clarifying question or use the tool to search.
6) If a user mistypes a common medication name, ask them what they mean and provide a suggestion.
6) You are stateless: do not assume the user identity. Only use user-specific tools if user_id is provided.
7) When a tool returns an error or multiple matches, ask a short clarifying question.
8) The default store is s001. Do not ask for a specific store, use the default.

Style:
- Be concise.
- Mirror the user’s language (Hebrew/English).
"""

TOOL_FUNCS = {
    "get_medication_by_name": get_medication_by_name,
    "check_inventory": check_inventory,
    "check_prescription_requirement": check_prescription_requirement,
    "check_allergy_concerns_and_ingredients": check_allergy_concerns_and_ingredients,
    "submit_customer_feedback": submit_customer_feedback,
}

TOOLS_SPEC = [
    {
        "type": "function",
        "name": "get_medication_by_name",
        "description": "Find a medication by brand or generic name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Brand or generic name, e.g. 'Advil' or 'Ibuprofen'."}
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "check_inventory",
        "description": "Check store inventory for a medication.",
        "parameters": {
            "type": "object",
            "properties": {
                "medication_id": {"type": "string"},
                "store_id": {"type": "string", "description": "Store id. Default: s001"},
            },
            "required": ["medication_id"],
        },
    },
    {
        "type": "function",
        "name": "check_prescription_requirement",
        "description": "Return whether a medication requires a prescription.",
        "parameters": {
            "type": "object",
            "properties": {"medication_id": {"type": "string"}},
            "required": ["medication_id"],
        },
    },
    {
        "type": "function",
        "name": "check_allergy_concerns_and_ingredients",
        "description": "List active ingredients and optionally flag allergy matches for a given user_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "medication_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["medication_id"],
        },
    },
    {
        "type": "function",
        "name": "submit_customer_feedback",
        "description": "Record customer feedback.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                "message": {"type": "string"},
            },
            "required": ["rating", "message"],
        },
    },
]


async def run_agent_stream(payload: Dict[str, Any], history: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
    user_text = (payload.get("text") or "").strip()

    if not user_text:
        yield {"type": "error", "message": "Empty message."}
        return

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    input_list = [{"role": "developer", "content": SYSTEM_PROMPT}] + history + [
    {"role": "user", "content": user_text},
]
    
    while True:
        # 1) streamed call
        streamed_text = ""
        function_calls = []

        async with client.responses.stream(
            model="gpt-5",
            input=input_list,
            tools=TOOLS_SPEC,
        ) as stream:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    delta = event.delta or ""
                    if delta:
                        streamed_text += delta
                        yield {"type": "token", "text": delta}

            # IMPORTANT: get the final response object from the SAME stream
            response = await stream.get_final_response()

        # 2) parse tool calls from response.output (SAME response!)
        for item in response.output:
            if item.type == "function_call":
                function_calls.append({
                    "call_id": item.call_id,
                    "name": item.name,
                    "arguments": item.arguments,
                })

        # 3) if no tool calls -> finalize
        if not function_calls:
            final_text = (response.output_text or streamed_text or "").strip()
            yield {"type": "final", "text": final_text}
            return
        
        # We must record that the Assistant made these tool calls.
        # Construct the 'tool_calls' list in the format expected by the API.
        
        api_tool_calls = []
        for call in function_calls:
            api_tool_calls.append({
                "id": call["call_id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": call["arguments"]
                }
            })

        # 4) execute tools and append function_call_output using those call_ids
        for call in function_calls:
            name = call["name"]
            call_id = call["call_id"]
            args_str = call.get("arguments") or "{}"
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else (args_str or {})
            except Exception:
                args = {}

            yield {"type": "tool_call", "name": name, "args": args}

            func = TOOL_FUNCS.get(name)
            if not func:
                result = {"error_code": "UNKNOWN_TOOL", "message": f"Tool not implemented: {name}"}
            else:
                try:
                    result = func(**args)
                except TypeError as e:
                    result = {"error_code": "BAD_ARGS", "message": str(e)}
                except Exception as e:
                    result = {"error_code": "TOOL_ERROR", "message": str(e)}

            yield {"type": "tool_result", "name": name, "result": result}

            input_list.append({
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": args_str,
            })
            input_list.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result, ensure_ascii=False),
            })

        # 5) loop continues
        continue
