

import asyncio, orjson, websockets

WS_URL = "wss://ws-feed.exchange.coinbase.com"
SUB_MSG = {
    "type": "subscribe",
    "product_ids": ["BTC-USD"],
    "channels": ["level2_batch", "matches"],
}

async def run(on_snapshot, on_l2update, on_match):
    async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20,max_size=None) as ws:
        await ws.send(orjson.dumps(SUB_MSG).decode())
        async for raw in ws:
            msg = orjson.loads(raw)
            t = msg.get("type")
            if t == "subscriptions":
                print("[ack]", msg)
                continue
        
            # wss Route messages
            if t == "snapshot" and msg.get("product_id") == "BTC-USD":
                on_snapshot(msg["bids"], msg["asks"])          # arrays of [price, size]
            elif t == "l2update" and msg.get("product_id") == "BTC-USD":
                # changes: [["buy","price","size"], ...] ; size is absolute (0 -> remove)
                on_l2update(msg["changes"], msg.get("time"))
            elif t in ("match", "last_match") and msg.get("product_id") == "BTC-USD":
                # fields: price, size, side, time
                on_match({
                    "price": float(msg["price"]),
                    "size":  float(msg["size"]),
                    "side":  msg["side"],   # "buy" means taker bought
                    "time":  msg["time"],
                })
