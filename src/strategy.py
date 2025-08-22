
from __future__ import annotations
from decimal import Decimal

class MarketMaker:
    """
    Simple market-maker:
      - Quotes around mid with a base spread (bps)
      - Skews quotes vs inventory (to mean-revert position)
      - Simulates fills from trade prints (matches)
    """
    def __init__(
        self,
        base_bps: Decimal | float = 5,          # each side
        q_size: Decimal | float = "0.05",       # BTC per quote
        skew_k: Decimal | float = "0.25",       # aggressiveness
        tick: Decimal | float = "0.01",         # BTC-USD tick
    ) -> None:
        self.base_bps = Decimal(str(base_bps))
        self.q_size   = Decimal(str(q_size))
        self.skew_k   = Decimal(str(skew_k))
        self.tick     = Decimal(str(tick))

        self.quotes = {"bid": (None, Decimal(0)), "ask": (None, Decimal(0))}
        self.position = Decimal("0")
        self.cash = Decimal("0")
        self.last_mid: Decimal | None = None
        
        self.skew_pwr = Decimal("0")
    

    # -------- quoting --------
    def _round_to_tick(self, px: Decimal) -> Decimal:
        # round to nearest tick without accumulating float errors
        return (px / self.tick).quantize(Decimal(1)) * self.tick

    def make_quotes(self, mid: Decimal, pos: Decimal, pos_limit: Decimal) -> dict:
        """
        Return dict: {"bid": (price, size), "ask": (price, size)}
        Skew: if long, worsen bid / improve ask; if short, opposite.
        """
        self.last_mid = Decimal(mid)
        # smooth inventory signal in [-1, 1]
        inv = float(pos / (pos_limit if pos_limit != 0 else Decimal("1")))
        inv = max(-1.0, min(1.0, inv))

        base = self.base_bps
        self.skew_pwr = self.skew_k * Decimal(inv)
        skew = self.skew_k * Decimal(inv) * base

        bid_px = self._round_to_tick(self.last_mid * (Decimal(1) - (base + skew) / Decimal(1e4)))
        ask_px = self._round_to_tick(self.last_mid * (Decimal(1) + (base - skew) / Decimal(1e4)))

        self.quotes = {"bid": (bid_px, self.q_size), "ask": (ask_px, self.q_size)}
        return self.quotes

    # -------- fills (from trade prints) --------
    def on_fill(self, side: str, size: Decimal, price: Decimal) -> None:
        if side == "buy":
            self.position += size
            self.cash -= size * price
        else:
            self.position -= size
            self.cash += size * price

    def maybe_fill_from_trade(self, trade: dict) -> list[tuple[str, float, float]]:
        """
        Coinbase 'match'/'last_match' uses maker side in 'side':
          - side == 'buy'  → maker was bid (taker sold)
          - side == 'sell' → maker was ask (taker bought)
        We assume a fill if the trade price ≈ our quote price (within half tick).
        """
        p = Decimal(str(trade["price"]))
        s = Decimal(str(trade["size"]))
        side = trade["side"]
        tol = self.tick / 2

        fills: list[tuple[str, float, float]] = []
        bid_px, bid_sz = self.quotes["bid"]
        ask_px, ask_sz = self.quotes["ask"]

        if side == "buy":  # bid was hit
            if bid_px is not None and abs(p - bid_px) <= tol:
                qty = min(bid_sz, s)
                if qty > 0:
                    self.on_fill("buy", qty, p)
                    fills.append(("buy", float(qty), float(p)))
        elif side == "sell":  # ask was lifted
            if ask_px is not None and abs(p - ask_px) <= tol:
                qty = min(ask_sz, s)
                if qty > 0:
                    self.on_fill("sell", qty, p)
                    fills.append(("sell", float(qty), float(p)))
        return fills
