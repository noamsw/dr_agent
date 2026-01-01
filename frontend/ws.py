import asyncio
import json
import sys

import websockets


WS_URL = "ws://127.0.0.1:8000/ws"


async def chat():
    print("Console WS chat connected to:", WS_URL)
    print("-" * 60)
    async with websockets.connect(
        WS_URL, 
        ping_interval=None, 
        ping_timeout=None
    ) as ws:
        while True:
            try:
                user_text = input("\nYou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting...")
                return

            if not user_text:
                continue

            if user_text.lower() == "/quit":
                print("Bye.")
                return


            # Send user message
            await ws.send(json.dumps({"text": user_text}))

            # Receive events until final/error for THIS turn
            assistant_started = False
            print("Assistant> ", end="", flush=True)

            while True:
                try:
                    msg = await ws.recv()
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"\n[WS CLOSED] code={e.code} reason={e.reason!r}")
                    return

                event = json.loads(msg)
                etype = event.get("type")

                if etype == "token":
                    assistant_started = True
                    sys.stdout.write(event.get("text", ""))
                    sys.stdout.flush()

                elif etype == "tool_call":
                    name = event.get("name")
                    args = event.get("args")
                    # show tool calls on their own line, but keep the assistant text readable
                    print(f"\n\n  [TOOL CALL] {name} args={args}")
                    print("Assistant> " + ("(continuing...) " if assistant_started else ""), end="", flush=True)

                elif etype == "tool_result":
                    name = event.get("name")
                    result = event.get("result")
                    print(f"\n  [TOOL RESULT] {name} result={result}")
                    print("Assistant> " + ("(continuing...) " if assistant_started else ""), end="", flush=True)

                elif etype == "final":
                    # Final message already streamed as tokens; but handle cases where final contains the whole text
                    final_text = event.get("text", "")
                    if final_text and not assistant_started:
                        print(final_text, end="")
                    print()  # newline
                    break

                elif etype == "error":
                    print(f"\n[ERROR] {event.get('message')}")
                    break

                else:
                    # unexpected event type, still print for debugging
                    print(f"\n[EVENT] {event}")
                    # keep waiting for final/error

if __name__ == "__main__":
    asyncio.run(chat())
