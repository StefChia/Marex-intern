
# src/main.py
import asyncio
from decimal import Decimal
from orderbook import OrderBookL2
from exchange import run
from analytics import compute_spreads_snapshot, SpreadTracker
from trade_buffer import TradeBuffer
from strategy import MarketMaker
from risk import RiskManager

ob = OrderBookL2()
sizes = [Decimal("0.1"), Decimal("1"), Decimal("5"), Decimal("10")]
tracker = SpreadTracker(sizes, window=300)

tbuf = TradeBuffer(maxlen=60)
mm = MarketMaker(base_bps=0.0005, q_size="0.05", skew_k="0.25", tick="0.01")
risk = RiskManager(max_exposure_usd=1_000_000, max_loss_usd=100_000)

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
    tbuf.add(trade)
    fills = mm.maybe_fill_from_trade(trade)
    for side, qty, px in fills:
        # Update both MM's own bookkeeping and RiskManager
        risk.on_fill(side, Decimal(str(qty)), Decimal(str(px)))
        print(f"[fill {trade['time']}] {side} {qty} @ {px} | pos= {mm.position} BTC | skew_pwr(vs base)= {round(mm.skew_pwr,4)}")

#LOOP FOR OUR QUOTES
async def quote_loop():
    while True:
        mid = ob.mid()
        if mid is not None:
            pos_limit_btc = Decimal("1000000") / mid  # dynamic BTC cap from $1m
            raw_quotes = mm.make_quotes(mid, mm.position, pos_limit_btc)

            snap = risk.snapshot(mid)
            quotes = risk.gate_quotes(raw_quotes, snap)

            bid_px, bid_sz = quotes["bid"]
            ask_px, ask_sz = quotes["ask"]

            # tiny status line
            print(
                f"[quote][{snap.mode}] "
                f"pos={snap.position}  exp=${snap.exposure_usd:.0f}  "
                f"PnL R/U/T={snap.realized:.0f}/{snap.unrealized:.0f}/{snap.total:.0f}  "
                f"bid={bid_px} x{bid_sz} | ask={ask_px} x{ask_sz}"
            )
        await asyncio.sleep(0.25)

async def main():
    ws_task = asyncio.create_task(run(on_snapshot, on_l2update, on_match))
    q_task  = asyncio.create_task(quote_loop())
    await asyncio.gather(ws_task, q_task)

if __name__ == "__main__":
    asyncio.run(main())
