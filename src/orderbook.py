
from __future__ import annotations
from bisect import bisect_left, insort
from decimal import Decimal, getcontext
from typing import Dict, List, Optional, Tuple, Iterable

# Choose precision for decimal(for crypto default is 28)
getcontext().prec = 28

DecimalLike = Decimal

class OrderBookL2:
    """
    Minimal L2 order book:
    - Maintains aggregated bids/asks
    - Supports snapshot + l2update (absolute sizes; "0" removes level)
    - Fast best bid/ask, mid, top-N, and size-aware VWAP walks
    """

    def __init__(self) -> None:
        # Price -> size
        self.bids: Dict[DecimalLike, DecimalLike] = {}
        self.asks: Dict[DecimalLike, DecimalLike] = {}
        # Sorted price lists (ASC). For best bid use last element.
        self.bid_px: List[DecimalLike] = []
        self.ask_px: List[DecimalLike] = []
        self._ready = False

    #UPDATES
    def apply_snapshot(self, bids: Iterable[Iterable[str]], asks: Iterable[Iterable[str]]) -> None:
        """Coinbase L2 snapshot: bids/asks are arrays of [price, size] (strings)."""
        self.__init__()  # clear
        for p_str, s_str in bids:
            self._set_level("buy", Decimal(p_str), Decimal(s_str))
        for p_str, s_str in asks:
            self._set_level("sell", Decimal(p_str), Decimal(s_str))
        self._ready = True

    def apply_l2update(self, changes: Iterable[Iterable[str]]) -> None:
        """
        Coinbase L2 update: changes is array of [side, price, size].
        Size is the UPDATED aggregated size at price (NOT a delta). "0" => remove level.
        """
        if not self._ready:
            # Ignore diffs until we have a snapshot
            return
        for side, p_str, s_str in changes:
            px = Decimal(p_str); sz = Decimal(s_str)
            self._set_level("buy" if side == "buy" else "sell", px, sz)

    #Queries
    def best_bid(self) -> Tuple[Optional[DecimalLike], DecimalLike]:
        if not self.bid_px:
            return (None, Decimal(0))
        p = self.bid_px[-1]
        return (p, self.bids[p])

    def best_ask(self) -> Tuple[Optional[DecimalLike], DecimalLike]:
        if not self.ask_px:
            return (None, Decimal(0))
        p = self.ask_px[0]
        return (p, self.asks[p])

    def mid(self) -> Optional[DecimalLike]:
        bb, _ = self.best_bid()
        ba, _ = self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / Decimal(2)

    def top_n(self, n: int = 5) -> Tuple[List[Tuple[DecimalLike, DecimalLike]], List[Tuple[DecimalLike, DecimalLike]]]:
        """Return top N (price, size) for bids (desc) and asks (asc)."""
        bids = [(p, self.bids[p]) for p in reversed(self.bid_px[-n:])]
        asks = [(p, self.asks[p]) for p in self.ask_px[:n]
               ]
        return (bids, asks)

    def vwap_to_take(self, side: str, size: DecimalLike) -> Optional[DecimalLike]:
        """
        Walk the book to compute VWAP to take 'size' on side:
        - side == "buy": you take from asks (ascending)
        - side == "sell": you take from bids (descending)
        Returns VWAP price or None if insufficient depth.
        """
        if size <= 0:
            return Decimal(0)

        if side == "buy":
            pxs = self.ask_px  # asc
            book = self.asks
        else:
            pxs = list(reversed(self.bid_px))  # desc
            book = self.bids

        need = size
        notional = Decimal(0)
        for p in pxs:
            avail = book[p]
            if avail <= 0:
                continue
            take = min(avail, need)
            notional += take * p
            need -= take
            if need <= 0:
                break
        if need > 0:
            return None
        return notional / size

    #SUPPORTING FUNCTIONS
    def _set_level(self, side: str, px: DecimalLike, sz: DecimalLike) -> None:
        if side == "buy":
            book = self.bids; plist = self.bid_px
        else:
            book = self.asks; plist = self.ask_px

        if sz == 0:
            # remove level if present
            if px in book:
                del book[px]
                i = bisect_left(plist, px)
                if i < len(plist) and plist[i] == px:
                    plist.pop(i)
            return

        # insert/update
        is_new = px not in book
        book[px] = sz
        if is_new:
            insort(plist, px)

    # Consistency check
    def assert_invariants(self) -> None:
        assert self.bid_px == sorted(self.bids.keys()), "bid_px out of sync"
        assert self.ask_px == sorted(self.asks.keys()), "ask_px out of sync"




"""
#SANITY CHECK ORDERBOOK OFFLINE
if __name__ == "__main__":
    ob = OrderBookL2()
    ob.apply_snapshot([["100", "1.0"], ["99", "2.0"]], [["101", "1.5"], ["102", "3.0"]])
    print("bb/ba/mid:", ob.best_bid(), ob.best_ask(), ob.mid())
    # Apply updates: set bid@100 to 0.5, remove ask@101, add ask@103
    ob.apply_l2update([
        ["buy", "100", "0.5"],
        ["sell", "101", "0"],
        ["sell", "103", "1.2"],
    ])
    print("bb/ba/mid:", ob.best_bid(), ob.best_ask(), ob.mid())
    print("VWAP buy 1.0:", ob.vwap_to_take("buy", Decimal("1.0")))
    print("VWAP sell 1.0:", ob.vwap_to_take("sell", Decimal("1.0")))
"""