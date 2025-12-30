import asyncio, json, websockets

async def main():
    uri = "ws://127.0.0.1:8000/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "text": "Do you have Advil in stock and do I need a prescription?",
        }))

        while True:
            try:
                msg = await ws.recv()
            except websockets.exceptions.ConnectionClosed as e:
                print(f"\n[WS CLOSED] code={e.code} reason={e.reason!r}")
                break

            event = json.loads(msg)
            t = event.get("type")

            if t == "token":
                print(event.get("text", ""), end="", flush=True)
            else:
                print(event)

if __name__ == "__main__":
    asyncio.run(main())