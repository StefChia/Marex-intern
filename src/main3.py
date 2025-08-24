
import asyncio
from decimal import Decimal
from orderbook import OrderBookL2
from exchange import run
from analytics import compute_spreads_snapshot, SpreadTracker
from trade_buffer import TradeBuffer
from strategy import MarketMaker, MarketMakerFIFO
from strategy_ex_base import MarketMaker_ex_base, MarketMaker_ex_FIFO
from risk import RiskManager

#INSTANTIATE
ob = OrderBookL2()
sizes = [Decimal("0.1"), Decimal("1"), Decimal("5"), Decimal("10")]
tracker = SpreadTracker(sizes, window=300)
tbuf = TradeBuffer(maxlen=60)

#DECIDE MKT MAKING
#Tick-based spread (2 ticks)(suggested)
#mm = MarketMaker(q_size="0.05", skew_k="0.25", tick="0.01")
mm = MarketMakerFIFO(q_size="0.05", skew_k="0.25", tick="0.01") 
#Arbitrary chosen base spread bps
#mm = MarketMaker_ex_base(base_bps=0.0008,q_size="0.05", skew_k="0.25", tick="0.01")
#mm = MarketMaker_ex_FIFO(base_bps=0.0001, q_size="0.05", skew_k="0.25", tick="0.01")

#SET RISK MANAGEMENT
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
        print(f"[fill {trade['time']}] {side} {qty} @ {px} | pos= {mm.position} BTC")

#LOOP FOR OUR QUOTES
async def quote_loop():
    while True:
        mid = ob.mid()
        if mid is not None:
            pos_limit_btc = Decimal("1000000") / mid
            
            #NO FIFO  & FIFO+NO-TICKS
            #raw_quotes = mm.make_quotes(mid, mm.position, pos_limit_btc)
            #ONLY FOR FIFO + TICK
            raw_quotes = mm.make_quotes(mid, mm.position, pos_limit_btc, ob)

            snap = risk.snapshot(mid)
            quotes = risk.gate_quotes(raw_quotes, snap)
            mm.quotes = quotes
            
            #Compute the FIFO metrics for current quote
            mm.sync_active_orders_with_book(ob)

            bid_px, bid_sz = quotes["bid"]
            ask_px, ask_sz = quotes["ask"]

            #I have added the skew_power to show how we dynamically (based on exposition) we skew the bid-ask quotes
            print(
                f"[quote][{snap.mode}] "
                f"pos={snap.position}  exp=${snap.exposure_usd:.0f}  "
                f"PnL R/U/T={snap.realized:.0f}/{snap.unrealized:.0f}/{snap.total:.0f}  "
                f"bid={bid_px} x{bid_sz} | ask={ask_px} x{ask_sz} | "
                f'skew_pwr(vs base)= {round(mm.skew_pwr,4)}'
            )
        await asyncio.sleep(0.25)

async def main():
    ws_task = asyncio.create_task(run(on_snapshot, on_l2update, on_match))
    q_task  = asyncio.create_task(quote_loop())
    await asyncio.gather(ws_task, q_task)

if __name__ == "__main__":
    asyncio.run(main())
