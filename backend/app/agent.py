import os
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from app.tools import (
    get_medication_by_name,
    check_inventory,
    check_prescription_requirement,
    reserve_medication,
    cancel_reservation_by_medication_id,
    cancel_reservation_by_reservation_id,
    find_active_prescriptions_for_user,
    find_reservations_for_user,
    get_medication_by_id
)

SYSTEM_PROMPT = """You are an AI pharmacist assistant for a retail pharmacy chain. You help customers in Hebrew or English.

Hard rules:
1) Provide factual information only. Never diagnose. Never recommend what to take. Never encourage purchases.
2) If the user asks for advice (e.g., “what should I take”, “is this safe for me”, “can I combine”, pregnancy, symptoms), refuse medical advice and redirect to a licensed pharmacist/doctor or emergency services if severe.
3) You have no capability to schedule appointments, book consultations, or transfer users to human staff. If a user requests to speak with a professional, strictly advise them to call or visit their local pharmacy or doctor directly.
4) You may explain label-style dosage/usage instructions and active ingredients as written in medication records.
5) Use tools to answer questions about medications, inventory, prescription requirements, active ingredients.
6) Do not invent medication data or stock. If missing/ambiguous, ask a clarifying question or use the tool to search.
7) If a user mistypes a common medication name, ask them what they mean and provide a suggestion.
8) Do not assume the user identity. Only use user-specific tools if the user provides phone last-4 (4 digits).
9) When a tool returns an error or multiple matches, ask a short clarifying question.
10) Default store is s001 unless the user specifies a different

Style:
- Be concise.
- Mirror the user’s language (Hebrew/English).
"""

TOOL_FUNCS = {
    "get_medication_by_name": get_medication_by_name,
    "check_inventory": check_inventory,
    "check_prescription_requirement": check_prescription_requirement,
    "reserve_medication": reserve_medication,
    "cancel_reservation_by_medication_id": cancel_reservation_by_medication_id,
    "cancel_reservation_by_reservation_id": cancel_reservation_by_reservation_id,
    "find_active_prescriptions_for_user": find_active_prescriptions_for_user,
    "find_reservations_for_user": find_reservations_for_user,
    "get_medication_by_id": get_medication_by_id
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
        "name": "reserve_medication",
        "description": (
            "Reserve (hold) a medication at a specific store for a user. "
            "Validates stock, user identity (phone last-4), duplicate active reservations, "
            "and prescription requirement if applicable. Returns a reservation receipt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "medication_id": {
                    "type": "string",
                    "description": "Medication ID (e.g., 'm001')."
                },
                "requested_quantity": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "How many units to reserve (must be >= 1)."
                },
                "users_phone_last4": {
                    "type": "string",
                    "pattern": "^[0-9]{4}$",
                    "description": "User's phone number last 4 digits as a 4-digit string (e.g., '0427')."
                },
                "store_id": {
                    "type": "string",
                    "default": "s001",
                    "description": "Store ID to reserve from (e.g., 's001'). Defaults to 's001'."
                }
            },
            "required": ["medication_id", "requested_quantity", "users_phone_last4"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "cancel_reservation_by_reservation_id",
        "description": (
            "Cancel (release) a reservation using its reservation_id. "
            "Removes the reservation from the user's reservations list and releases the reserved quantity "
            "back to store inventory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reservation_id": {
                    "type": "string",
                    "description": "Reservation ID to cancel (e.g., 'r_a1b2c3d4e5')."
                },
                "users_phone_last4": {
                    "type": "string",
                    "pattern": "^[0-9]{4}$",
                    "description": "User phone last 4 digits as a 4-digit string (e.g., '0427')."
                }
            },
            "required": ["reservation_id", "users_phone_last4"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "cancel_reservation_by_medication_id",
        "description": (
            "Cancel (release) a user's reservation for a medication at a store. "
            "Removes the reservation from the user's reservations list and releases the reserved quantity "
            "back to store inventory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "medication_id": {
                    "type": "string",
                    "description": "Medication ID to cancel (e.g., 'm001')."
                },
                "users_phone_last4": {
                    "type": "string",
                    "pattern": "^[0-9]{4}$",
                    "description": "User phone last 4 digits as a 4-digit string (e.g., '0427')."
                },
                "store_id": {
                    "type": "string",
                    "default": "s001",
                    "description": "Store ID where the reservation was made (e.g., 's001'). Defaults to 's001'."
                }
            },
            "required": ["medication_id", "users_phone_last4"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "find_active_prescriptions_for_user",
        "description": (
            "Retrieve all active prescriptions for a user. "
            "Returns a list of active prescriptions enriched with medication details."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "users_phone_last4": {
                    "type": "string",
                    "pattern": "^[0-9]{4}$",
                    "description": "User phone number last 4 digits as a 4-digit string (e.g., '0427')."
                }
            },
            "required": ["users_phone_last4"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "find_reservations_for_user",
        "description": (
            "Retrieve all current reservations for a user (reservations are considered active if present). "
            "Returns a list of reservations enriched with medication details."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "users_phone_last4": {
                    "type": "string",
                    "pattern": "^[0-9]{4}$",
                    "description": "User phone last 4 digits as a 4-digit string (e.g., '0427')."
                }
            },
            "required": ["users_phone_last4"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "get_medication_by_id",
        "description": "Retrieve a medication by its medication_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "medication_id": {
                    "type": "string",
                    "description": "Medication ID (e.g., 'm001')."
                }
            },
            "required": ["medication_id"],
            "additionalProperties": False
        }
    }
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
