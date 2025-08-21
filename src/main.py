

import asyncio
from orderbook import OrderBookL2
from exchange import run

ob = OrderBookL2()

def on_snapshot(bids, asks):
    ob.apply_snapshot(bids, asks)
    bb, bb_sz = ob.best_bid(); ba, ba_sz = ob.best_ask()
    print(f"[snapshot] bb={bb} x {bb_sz} | ba={ba} x {ba_sz} | mid={ob.mid()}")

def on_l2update(changes, t):
    ob.apply_l2update(changes)
    bb, bb_sz = ob.best_bid(); ba, ba_sz = ob.best_ask()
    print(f"[l2update {t}] bb={bb}({bb_sz}) | ba={ba}({ba_sz}) | mid={ob.mid()}")

def on_match(trade):
    """RECALL:
    On Coinbase’s match / last_match messages, the field side tells you the maker’s side:
    So the side is not the aggressor; it’s the resting order that got hit/lifted."""
    
    print(f"[match {trade['time']}] {trade['side']} {trade['size']} @ {trade['price']}")

if __name__ == "__main__":
    asyncio.run(run(on_snapshot, on_l2update, on_match))