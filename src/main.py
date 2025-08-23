
import asyncio
from decimal import Decimal
from orderbook import OrderBookL2
from exchange import run
from analytics import compute_spreads_snapshot,compute_data, SpreadTracker
from trade_buffer import TradeBuffer
from strategy import MarketMaker
from risk import RiskManager
from ui import run_ui
from datetime import datetime, timezone
from logger import CSVLogger

#INSTANTIATE
ob = OrderBookL2()
sizes = [Decimal("0.1"), Decimal("1"), Decimal("5"), Decimal("10")]
tracker = SpreadTracker(sizes, window=300)
tbuf = TradeBuffer(maxlen=60)
mm = MarketMaker(base_bps=0.001, q_size="0.05", skew_k="0.25", tick="0.01")
risk = RiskManager(max_exposure_usd=1_000_000, max_loss_usd=100_000)
logger = CSVLogger(root="data")

#DEFINING
def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def on_snapshot(bids, asks):
    ob.apply_snapshot(bids, asks)
    snap = compute_spreads_snapshot(ob, sizes)
    sp,bid_curve,ask_curve = compute_data(ob, sizes)
    tracker.update(snap)
    logger.log_spreads(_now_iso(), snap)  # log first snapshot
    logger.log_power_curve(_now_iso(),'bid', bid_curve)
    logger.log_power_curve(_now_iso(),'ask', ask_curve)

def on_l2update(changes, t):
    ob.apply_l2update(changes)
    snap = compute_spreads_snapshot(ob, sizes)
    tracker.update(snap)
    logger.log_spreads(t or _now_iso(), snap)  
    sp, bid_curve, ask_curve = compute_data(ob, sizes)
    logger.log_power_curve(t or _now_iso(), 'bid', bid_curve)
    logger.log_power_curve(t or _now_iso(), 'ask', ask_curve)

def on_match(trade):
    tbuf.add(trade)
    fills = mm.maybe_fill_from_trade(trade)
    # Update risk on simulated fills
    for side, qty, px in fills:
        risk.on_fill(side, Decimal(str(qty)), Decimal(str(px)))
        #To get the log spreads
        snap = risk.snapshot(ob.mid())
        logger.log_trade_and_pnl(trade["time"], side, px, qty, snap)
        print(f"[fill {trade['time']}] {side} {qty} @ {px} | pos= {mm.position} BTC | skew_pwr(vs base)= {round(mm.skew_pwr,4)}")
        

async def quote_loop():
    """Refresh quotes ~4x/sec based on current mid & inventory; risk gates them."""
    while True:
        mid = ob.mid()
        if mid is not None:
            pos_limit_btc = Decimal("1000000") / mid
            raw_quotes = mm.make_quotes(mid, mm.position, pos_limit_btc)
            snap = risk.snapshot(mid)
            # Prepare for UI
            gated = risk.gate_quotes(raw_quotes, snap)
            mm.quotes = gated
            # periodic PnL snapshot
            logger.log_pnl(_now_iso(), snap)
        await asyncio.sleep(0.25)


async def main():
    ws_task = asyncio.create_task(run(on_snapshot, on_l2update, on_match))
    q_task  = asyncio.create_task(quote_loop())
    ui_task = asyncio.create_task(run_ui(ob, tracker, sizes, mm, risk, tbuf))
    await asyncio.gather(ws_task, q_task, ui_task)

if __name__ == "__main__":
    asyncio.run(main())
