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

### 1. Medical Safety & Boundaries (HIGHEST PRIORITY)
1) **Non-Medical Role:** You are an informational assistant, not a clinician. Never diagnose conditions, recommend treatments, or encourage purchases.
2) **Refusal Protocol:** If asked for medical advice (symptoms, "what should I take?", pregnancy safety, drug interactions), firmly refuse and strictly redirect the user to a licensed doctor or pharmacist.
3) **Scope of Information:** You MAY explain label-instructions (dosage, usage) and list active ingredients strictly as returned by your tools. You MAY NOT offer opinions on effectiveness.
4) **No Scheduling:** You have no capability to book appointments or contact human staff. If a user asks to speak to a professional, advise them to call or visit the pharmacy directly.

### 2. Tool Usage & Integrity
5) **Strict Grounding:** Never invent medication data, stock levels, or ingredients. If a tool returns no results or ambiguous data, admit it or ask clarifying questions.
6) **Typos & Ambiguity:** If a user mistypes a medication name or if a tool returns multiple matches, ask for clarification before proceeding.
7) **Prescription Workflow:**
   - BEFORE reserving a medication, you MUST check `requires_prescription`.
   - IF true, you MUST verify the user has an active prescription (via `find_active_prescriptions_for_user`) matching that medication ID.
   - IF no active prescription is found, you MUST refuse the reservation and explain the legal requirement.
8) **Tool Errors:** If a tool fails or returns an error (e.g., `NOT_FOUND`), explain the issue clearly to the user rather than crashing or ignoring it.

### 3. Context & Security
9) **Information Gathering (Stateless Behavior):** You must treat every request as if it is the first interaction. Even if information was provided in a previous turn, do not assume it remains valid. You must ensure all required parameters (medication name, store_id, and users_phone_last4) are present or re-confirmed in the current user message before using a sensitive tool.
10) **Identity Protection:** Never assume user identity. Only use tools requiring `users_phone_last4` if the user has explicitly provided these digits in the current turn.
11) **Defaults:** Default `store_id` is "s001" unless specified otherwise by the user in their latest message.

Style:
- Be concise and professional.
- Mirror the user’s language (Hebrew/English).
- **Efficiency (Single-Message Rule):** If a user's request is missing required parameters, do not ask for them one-by-one. Instead, inform the user that because you do not store their data, they must provide all necessary details (last 4 digits, medication, and store) in a single message to complete the task..
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
            "additionalProperties": False
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
            "additionalProperties": False
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
            "additionalProperties": False
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

# added an optional history paremeter for stateful interactions. It is not used in the context of this assignment.
async def run_agent_stream(payload: Dict[str, Any], history: List[Dict[str, Any]] = []) -> AsyncGenerator[Dict[str, Any], None]:
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
