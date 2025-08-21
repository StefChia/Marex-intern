
import asyncio
from decimal import Decimal
from orderbook import OrderBookL2
from exchange import run
from analytics import compute_spreads_snapshot, SpreadTracker

ob = OrderBookL2()
sizes = [Decimal("0.1"), Decimal("1"), Decimal("5"), Decimal("10")]
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
    tracker.update(snap)

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
        
    print(" | ".join(line))

def on_match(trade):
    # kept simple for now; used later for fill simulation
    pass

if __name__ == "__main__":
    asyncio.run(run(on_snapshot, on_l2update, on_match))
