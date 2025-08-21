
from __future__ import annotations
from collections import deque, defaultdict
from decimal import Decimal
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

# ---------- core snapshot computations ----------

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

    # Top-of-book spread
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

# ---------- rolling windows & stats ----------

class RollingWindow:
    """
    Rolling window that ignores None values.
    Stores Decimals; stats returned as Decimals where applicable.
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
        return median(self.buf)  # works with Decimals

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
      - top-of-book spread (usd & bps)
      - size-aware spreads for a set of sizes (usd & bps)
    """
    def __init__(self, sizes: Iterable[Decimal], window: int = 300):
        self.sizes = list(sizes)
        self.win_top_usd = RollingWindow(window)
        self.win_top_bps = RollingWindow(window)
        self.win_usd: Dict[Decimal, RollingWindow] = {s: RollingWindow(window) for s in self.sizes}
        self.win_bps: Dict[Decimal, RollingWindow] = {s: RollingWindow(window) for s in self.sizes}
        self._last_snapshot: Optional[Dict] = None

    def update(self, snapshot: Dict) -> None:                   #THIS IS THE FEEDING FROM THE COMPUTE SNAPSHOT AND THE CURRENT ROLLING TRACKER
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
