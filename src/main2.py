
import asyncio
from decimal import Decimal
from orderbook import OrderBookL2
from exchange import run
from analytics import compute_spreads_snapshot, compute_data, SpreadTracker
import pandas as pd

ob = OrderBookL2()
#sizes = [Decimal("0.001"),Decimal("0.01"),Decimal("0.1"), Decimal("1"), Decimal("5"), Decimal("10")]
sizes = [Decimal(str(2**i)) for i in range(-10,5)]
tracker = SpreadTracker(sizes, window=300)

def _fmt(x):
    return f"{x:.2f}" if x is not None else "-"

def on_snapshot(bids, asks):
    ob.apply_snapshot(bids, asks)
    snap = compute_spreads_snapshot(ob, sizes)
    tracker.update(snap)
    mid = snap["mid"]
    top = snap["top_of_book"]
    print(f"[snapshot] mid={_fmt(mid)}  top_spread=${_fmt(top['usd'])} ({_fmt(top['bps'])} bps)")

def on_l2update(changes, t):
    ob.apply_l2update(changes)
    snap = compute_spreads_snapshot(ob, sizes)
    spreads, out_bid, out_ask = compute_data(ob, sizes)

    tracker.update(snap)
    
    #To get rolling spreads data for a certain size in the book 
    #for s in sizes:
        #print(f'Size:{s} , mean_spread(bps): {tracker.report_for_historic_roll_spreads()[s].mean()}')
    
    #To get rolling spreads data for a certain size in the book
    
    for s in sizes:
        tracker.bid_lev[s].add(out_bid[s])
        tracker.ask_lev[s].add(out_ask[s])
        tracker.spreads[s].add(spreads[s])
        print(f'Size: {s}, IN $: Bid= {tracker.bid_lev[s].mean()}, Ask= {tracker.ask_lev[s].mean()}, Spread= {round(tracker.spreads[s].mean(),2)}, mean_spread(bps): {tracker.report_for_historic_roll_spreads()[s].mean()}')
    
    """
    #Display THE bid/ask levels for each size
    tracker.bid_lev.add(out_bid[Decimal('0.0009765625')])
    #Display THE bid/ask levels for each size
    tracker.ask_lev.add(out_ask[Decimal('0.0009765625')])
    #Display the spread for each size
    tracker.spreads.add(spreads[Decimal('0.0009765625')])
    
    print(f'IN $: Bid= {tracker.bid_lev.mean()}, Ask= {tracker.ask_lev.mean()}, Spread= {tracker.spreads.mean()}')
    """
"""
    # pretty one-liner with current + rolling avg for each size
    cur = snap["sizes"]
    roll = tracker.report()["rolling"]["sizes"]
    line = [f"[spreads {t}] top=${_fmt(snap['top_of_book']['usd'])} ({_fmt(snap['top_of_book']['bps'])} bps)"]
    for s in sizes:
        c = cur[s]
        avg_bps = roll[s]["bps"]["avg"]
        median_bps = roll[s]["bps"]["median"]
        min_bps = roll[s]["bps"]["min"]
        max_bps = roll[s]["bps"]["max"]
        line.append(f"{s} BTC: {_fmt(c['usd'])}$ / {_fmt(c['bps'])} bps (KPI in bps: avg={_fmt(avg_bps)} median={_fmt(median_bps)} min={_fmt(min_bps)} max={_fmt(max_bps)})")
        
    print(" | ".join(line))"""

def on_match(trade):
    # kept simple for now; used later for fill simulation
    pass

if __name__ == "__main__":
    asyncio.run(run(on_snapshot, on_l2update, on_match))
