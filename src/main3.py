
# src/main.py
import asyncio
from decimal import Decimal
from orderbook import OrderBookL2
from exchange import run
from analytics import compute_spreads_snapshot, SpreadTracker
from trade_buffer import TradeBuffer
from strategy import MarketMaker

ob = OrderBookL2()
sizes = [Decimal("0.1"), Decimal("1"), Decimal("5"), Decimal("10")]
tracker = SpreadTracker(sizes, window=300)

tbuf = TradeBuffer(maxlen=60)
mm = MarketMaker(base_bps=5, q_size="0.05", skew_k="0.25", tick="0.01")

def _fmt(x):
    return f"{x:.2f}" if x is not None else "-"

def on_snapshot(bids, asks):
    ob.apply_snapshot(bids, asks)
    snap = compute_spreads_snapshot(ob, sizes)
    tracker.update(snap)
    print(f"[snapshot] mid={_fmt(snap['mid'])} top=${_fmt(snap['top_of_book']['usd'])} ({_fmt(snap['top_of_book']['bps'])} bps)")

def on_l2update(changes, t):
    ob.apply_l2update(changes)
    snap = compute_spreads_snapshot(ob, sizes)
    tracker.update(snap)

def on_match(trade):
    # trade = {"price": float, "size": float, "side": "buy"|"sell", "time": str}
    tbuf.add(trade)
    fills = mm.maybe_fill_from_trade(trade)
    for side, qty, px in fills:
        print(f"[fill {trade['time']}] {side} {qty} @ {px} | pos={mm.position} BTC")

async def quote_loop():
    """Refresh quotes ~4x/sec based on current mid & inventory."""
    while True:
        mid = ob.mid()
        if mid is not None:
            # For now compute a dynamic BTC limit from $1m exposure; Step 7 plugs real risk manager.
            pos_limit_btc = Decimal("1000000") / mid
            quotes = mm.make_quotes(mid, mm.position, pos_limit_btc)
            bid_px, bid_sz = quotes["bid"]
            ask_px, ask_sz = quotes["ask"]
            print(f"[quote] bid {bid_px} x{bid_sz} | ask {ask_px} x{ask_sz} | pos {mm.position}")
        await asyncio.sleep(0.25)

async def main():
    ws_task = asyncio.create_task(run(on_snapshot, on_l2update, on_match))
    q_task  = asyncio.create_task(quote_loop())
    await asyncio.gather(ws_task, q_task)

if __name__ == "__main__":
    asyncio.run(main())
