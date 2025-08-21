
from __future__ import annotations
from collections import deque
from typing import Deque, Dict, List

class TradeBuffer:
    """Keeps the last N trades for UI/fill-sim/reference."""
    def __init__(self, maxlen: int = 50) -> None:
        self.buf: Deque[Dict] = deque(maxlen=maxlen)

    def add(self, trade: Dict) -> None:
        # expected keys: price(float), size(float), side('buy'|'sell'), time(str)
        self.buf.append(trade)

    def recent(self, n: int = 10) -> List[Dict]:
        if n <= 0:
            return []
        b = list(self.buf)
        return b[-n:]
