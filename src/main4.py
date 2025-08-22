
import asyncio
from decimal import Decimal
from orderbook import OrderBookL2
from exchange import run
from analytics import compute_spreads_snapshot, SpreadTracker
from trade_buffer import TradeBuffer
from strategy import MarketMaker
from risk import RiskManager
from ui import run_ui

ob = OrderBookL2()
sizes = [Decimal("0.1"), Decimal("1"), Decimal("5"), Decimal("10")]
tracker = SpreadTracker(sizes, window=300)
tbuf = TradeBuffer(maxlen=60)
mm = MarketMaker(base_bps=5, q_size="0.05", skew_k="0.25", tick="0.01")
risk = RiskManager(max_exposure_usd=1_000_000, max_loss_usd=100_000)

def on_snapshot(bids, asks):
    ob.apply_snapshot(bids, asks)
    snap = compute_spreads_snapshot(ob, sizes)
    tracker.update(snap)
    # (silence prints; the UI will show it)

def on_l2update(changes, t):
    ob.apply_l2update(changes)
    snap = compute_spreads_snapshot(ob, sizes)
    tracker.update(snap)
    # (silence prints)

def on_match(trade):
    tbuf.add(trade)
    fills = mm.maybe_fill_from_trade(trade)
    # Update risk on simulated fills
    for side, qty, px in fills:
        risk.on_fill(side, Decimal(str(qty)), Decimal(str(px)))
        print(f"[fill {trade['time']}] {side} {qty} @ {px} | pos= {mm.position} BTC | skew_pwr(vs base)= {round(mm.skew_pwr,4)}")

async def quote_loop():
    """Refresh quotes ~4x/sec based on current mid & inventory; risk gates them."""
    while True:
        mid = ob.mid()
        if mid is not None:
            pos_limit_btc = Decimal("1000000") / mid
            raw_quotes = mm.make_quotes(mid, mm.position, pos_limit_btc)
            snap = risk.snapshot(mid)
            # Gate in-place so UI sees gated quotes via mm.quotes if you prefer:
            gated = risk.gate_quotes(raw_quotes, snap)
            # overwrite mm.quotes with gated view (so sim/UI are consistent)
            mm.quotes = gated
        await asyncio.sleep(0.25)

async def main():
    ws_task = asyncio.create_task(run(on_snapshot, on_l2update, on_match))
    q_task  = asyncio.create_task(quote_loop())
    ui_task = asyncio.create_task(run_ui(ob, tracker, sizes, mm, risk, tbuf))
    await asyncio.gather(ws_task, q_task, ui_task)

if __name__ == "__main__":
    asyncio.run(main())
