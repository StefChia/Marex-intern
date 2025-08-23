
from __future__ import annotations
from collections import deque, defaultdict
from decimal import Decimal
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple
from pathlib import Path

#Compute Snapshot
def _bps(diff: Optional[Decimal], mid: Optional[Decimal]) -> Optional[Decimal]:
    if diff is None or mid in (None, Decimal(0)):
        return None
    return (diff / mid) * Decimal(1e4)

def compute_spreads_snapshot(orderbook, sizes: Iterable[Decimal]) -> Dict:
    """
    Returns a snapshot dict with:
      - mid
      - top_of_book: {usd, bps}
      - sizes: {size -> {usd, bps, buy_vwap, sell_vwap}}
    """
    mid = orderbook.mid()

    # Top-book spread
    bb, _ = orderbook.best_bid()
    ba, _ = orderbook.best_ask()
    top_usd = (ba - bb) if (bb is not None and ba is not None) else None
    top_bps = _bps(top_usd, mid) if top_usd is not None else None

    out = {
        "mid": mid,
        "top_of_book": {"usd": top_usd, "bps": top_bps},
        "sizes": {}
    }

    for s in sizes:
        buy_vwap  = orderbook.vwap_to_take("buy", s)   # take from asks
        sell_vwap = orderbook.vwap_to_take("sell", s)  # take from bids
        if buy_vwap is None or sell_vwap is None or mid is None:
            out["sizes"][s] = {"usd": None, "bps": None,
                               "buy_vwap": buy_vwap, "sell_vwap": sell_vwap}
            continue
        raw = buy_vwap - sell_vwap
        out["sizes"][s] = {
            "usd": raw,
            "bps": _bps(raw, mid),
            "buy_vwap": buy_vwap,
            "sell_vwap": sell_vwap
        }
    return out

def compute_data(orderbook, sizes: Iterable[Decimal]) -> Tuple[Dict, Dict, Dict]:
    """
    Returns three dicts (all values in bps unless None):
      - sp_bps: size-aware spread = (buy_vwap - sell_vwap)/mid * 1e4, plus 'best' = top-of-book bps
      - bid_curve_bps: impact for SELLING size = (mid - sell_vwap)/mid * 1e4
      - ask_curve_bps: impact for BUYING  size = (buy_vwap - mid)/mid * 1e4
    Keys are each size from `sizes`; also adds key 'best' in sp_bps.
    """
    mid = orderbook.mid()
    bb, _ = orderbook.best_bid()
    ba, _ = orderbook.best_ask()

    sp_bps: Dict = {}
    bid_curve_bps: Dict = {}
    ask_curve_bps: Dict = {}

    # Top-book spread (bps)
    if mid is None or bb is None or ba is None or mid == 0:
        sp_bps["best"] = None
    else:
        sp_bps["best"] = ( (ba - bb) / mid ) * Decimal(1e4)

    # Add for Each size (i.e. size aware)
    for s in sizes:
        if mid is None or mid == 0:
            sp_bps[s] = bid_curve_bps[s] = ask_curve_bps[s] = None
            continue

        buy_vwap  = orderbook.vwap_to_take("buy",  s)  # take asks
        sell_vwap = orderbook.vwap_to_take("sell", s)  # take bids

        if buy_vwap is None or sell_vwap is None:
            sp_bps[s] = bid_curve_bps[s] = ask_curve_bps[s] = None
            continue

        sp_bps[s]        = ( (buy_vwap - sell_vwap) / mid ) * Decimal(1e4)
        bid_curve_bps[s] = ( (sell_vwap- mid) / mid ) * Decimal(1e4)  # <=0
        ask_curve_bps[s] = ( (buy_vwap - mid) / mid ) * Decimal(1e4)  # >=0

    return sp_bps, bid_curve_bps, ask_curve_bps

# ---------- rolling windows & stats ----------

class RollingWindow:
    """
    Rolling window.
    Stores Decimals.
    """
    def __init__(self, maxlen: int = 300):
        self.maxlen = maxlen
        self.buf: deque[Decimal] = deque(maxlen=maxlen)

    def add(self, x: Optional[Decimal]) -> None:
        if x is not None:
            self.buf.append(x)

    def empty(self) -> bool:
        return len(self.buf) == 0

    def mean(self) -> Optional[Decimal]:
        if self.empty(): return None
        return sum(self.buf, start=Decimal(0)) / Decimal(len(self.buf))

    def med(self) -> Optional[Decimal]:
        if self.empty(): return None
        return median(self.buf)  

    def min(self) -> Optional[Decimal]:
        if self.empty(): return None
        return min(self.buf)

    def max(self) -> Optional[Decimal]:
        if self.empty(): return None
        return max(self.buf)

    def summary(self) -> Dict[str, Optional[Decimal]]:
        return {
            "avg": self.mean(),
            "median": self.med(),
            "min": self.min(),
            "max": self.max(),
        }

class SpreadTracker:
    """
    Maintains rolling stats for:
      - top-book spread (usd & bps)
      - size-aware spreads for a set of sizes (usd & bps)
    """
    def __init__(self, sizes: Iterable[Decimal], window: int = 300):
        self.sizes = list(sizes)
        self.win_top_usd = RollingWindow(window)
        self.win_top_bps = RollingWindow(window)
        self.win_usd: Dict[Decimal, RollingWindow] = {s: RollingWindow(window) for s in self.sizes}
        self.win_bps: Dict[Decimal, RollingWindow] = {s: RollingWindow(window) for s in self.sizes}
        self._last_snapshot: Optional[Dict] = None
        
        #MY ADDITION
        self.spreads : Dict[Decimal, RollingWindow] = {s: RollingWindow(window) for s in self.sizes}
        self.bid_lev : Dict[Decimal, RollingWindow] = {s: RollingWindow(window) for s in self.sizes}
        self.ask_lev : Dict[Decimal, RollingWindow] = {s: RollingWindow(window) for s in self.sizes}
        
        
    #THIS IS THE FEEDING FROM THE COMPUTE SPREADS SNAPSHOT TO THE CURRENT ROLLING TRACKER
    def update(self, snapshot: Dict) -> None:                   
        """Feed the latest compute_spreads_snapshot output."""
        self._last_snapshot = snapshot
        top = snapshot["top_of_book"]
        self.win_top_usd.add(top["usd"])
        self.win_top_bps.add(top["bps"])

        for s, d in snapshot["sizes"].items():
            self.win_usd[s].add(d["usd"])
            self.win_bps[s].add(d["bps"])

    def report(self) -> Dict:
        """
        Returns a nested dict:
          {
            "current": {...},
            "rolling": {
                "top": {"usd": {...}, "bps": {...}},
                "sizes": { size: {"usd": {...}, "bps": {...}} }
            }
          }
        """
        cur = self._last_snapshot or {}
        roll = {
            "top": {
                "usd": self.win_top_usd.summary(),
                "bps": self.win_top_bps.summary(),
            },
            "sizes": {}
        }
        for s in self.sizes:
            roll["sizes"][s] = {
                "usd": self.win_usd[s].summary(),
                "bps": self.win_bps[s].summary(),
            }
        return {"current": cur, "rolling": roll}
    
    def report_for_historic_roll_spreads(self) -> Dict:
        """
        Returns a dict
        """
        roll = {
            "top":  self.win_top_bps,
        }
        for s in self.sizes:
            roll[s] = self.win_bps[s]
            
        return roll
        
        
        