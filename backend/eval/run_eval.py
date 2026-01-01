import asyncio
import json
import os
import inspect
from typing import Any, Dict, List

from app.agent import run_agent_stream
from app.db import load_json, save_json

async def _collect_one_async(payload: Dict[str, Any], history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    final_text = ""

    agen = run_agent_stream(payload, history) if history else run_agent_stream(payload)

    async for ev in agen:
        events.append(ev)
        if ev.get("type") == "final":
            final_text = ev.get("text", "") or ""

    return {"events": events, "final_text": final_text}


def _assert_contains_any(text: str, needles: List[str]) -> bool:
    t = (text or "").lower()
    return any(n.lower() in t for n in needles)


def _tools_called(events: List[Dict[str, Any]]) -> List[str]:
    return [e.get("name") for e in events if e.get("type") == "tool_call"]

# used for stateful interactions
def _append_history(history: List[Dict[str, Any]], user_text: str, assistant_text: str) -> None:
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})


async def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set in env.")
    
    here = os.path.dirname(__file__)
    scenarios_path = os.path.join(here, "scenarios.json")
    with open(scenarios_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    total = 0
    passed = 0

    users = load_json("users.json") 
    idx = next(
        (i for i, u in enumerate(users) if u.get("phone_last4") == "6789"),
        None
    )
    if idx is None:
        print("Error: User with phone_last4 '6789' not found in users.json")
        return 
    # Clear the reservations
    users[idx]["reservations"] = []

    # Save using the same filename format
    save_json("users.json", users)

    for sc in scenarios:
        total += 1
        # history: List[Dict[str, Any]] = [] used for stateful interactions
        all_events: List[Dict[str, Any]] = []
        last_final = ""
        # used for stateful interactions
        for turn in sc["turns"]:
            res = await _collect_one_async(turn)
            # used for stateful interactions
            # res = await _collect_one_async(turn, history)
            all_events.extend(res["events"])

            if res["final_text"]:
                last_final = res["final_text"]
                # used for stateful interactions
                # _append_history(history, (turn.get("text") or "").strip(), res["final_text"])

        tools_called = _tools_called(all_events)

        ok = True
        assertions = sc.get("assertions", {})

        for tname in assertions.get("must_call_tools", []):
            if tname not in tools_called:
                ok = False

        for tname in assertions.get("forbidden_tools", []):
            if tname in tools_called:
                ok = False

        final_any = assertions.get("final_must_contain_any", [])
        if final_any and not _assert_contains_any(last_final, final_any):
            ok = False

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1

        print(f"[{status}] {sc['id']}")
        if not ok:
            print("  tools_called:", tools_called)
            print("  final:", last_final)
        print()

    print(f"Summary: {passed}/{total} passed")


if __name__ == "__main__":
    asyncio.run(main())
