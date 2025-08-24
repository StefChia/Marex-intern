
from __future__ import annotations
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING

class MarketMaker_ex_base:
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
    

    # Our Quotes
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

    # Fills (from trade prints)
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
    
    
    

#DEFINING Market Making FIFO

def _clamp(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, x))

class MarketMaker_ex_FIFO:
    """
    Simple market-maker (FIFO):
      - Quotes around mid with a FIXED base half-spread in bps (self.base_bps)
      - Skews quotes vs inventory (to mean-revert position)
      - Simulates FIFO fills using queue_ahead at the posted price
    """
    def __init__(
        self,
        base_bps: Decimal | float = 5,          # half-spread per side (bps)
        q_size:   Decimal | float = "0.05",     # BTC per quote
        skew_k:   Decimal | float = "0.25",     # skew aggressiveness (multiplies base)
        tick:     Decimal | float = "0.01",     # BTC-USD tick
    ) -> None:
        self.base_bps = Decimal(str(base_bps))
        self.q_size   = Decimal(str(q_size))
        self.skew_k   = Decimal(str(skew_k))
        self.tick     = Decimal(str(tick))

        self.quotes   = {"bid": (None, Decimal(0)), "ask": (None, Decimal(0))}
        self.position = Decimal("0")
        self.cash     = Decimal("0")
        self.last_mid: Decimal | None = None
        self.skew_pwr = Decimal("0")

        # FIFO state per side:
        # {"px": Decimal, "posted_qty": Decimal, "qty_rem": Decimal,
        #  "queue_ahead": Decimal, "last_level_sz": Decimal}
        self.active = {"bid": None, "ask": None}
        self._tol = self.tick / 2  # price matching tolerance

    #prevents spread collapse/cross
    def _round_bid(self, px: Decimal) -> Decimal:
        return px.quantize(self.tick, rounding=ROUND_FLOOR)

    def _round_ask(self, px: Decimal) -> Decimal:
        return px.quantize(self.tick, rounding=ROUND_CEILING)

    #Our Quotes
    def make_quotes(self, mid: Decimal, pos: Decimal, pos_limit: Decimal) -> dict:
        self.last_mid = Decimal(mid)

        # inventory signal in [-1, 1] (stay in Decimal)
        denom = (pos_limit if pos_limit != 0 else Decimal("1"))
        inv = _clamp(pos / denom, Decimal("-1"), Decimal("1"))

        base = self.base_bps                     # bps (per side)
        self.skew_pwr = self.skew_k * inv        
        skew = self.skew_pwr * base              

        one = Decimal(1); bps = Decimal(1e4)
        bid_theo = self.last_mid * (one - (base + skew) / bps)
        ask_theo = self.last_mid * (one + (base - skew) / bps)

        bid_px = self._round_bid(bid_theo)
        ask_px = self._round_ask(ask_theo)

        # ensure at least 1 tick wide after rounding
        if ask_px <= bid_px:
            ask_px = bid_px + self.tick

        self.quotes = {"bid": (bid_px, self.q_size), "ask": (ask_px, self.q_size)}
        return self.quotes

    #FIFO state sync
    def sync_active_orders_with_book(self, ob) -> None:
        """
        Seed/refresh FIFO queue state at the posted prices.
        Call this each time you (re)post quotes.
        """
        for side in ("bid", "ask"):
            px, qty = self.quotes.get(side, (None, Decimal(0)))
            if px is None or qty <= 0:
                self.active[side] = None
                continue

            book = ob.bids if side == "bid" else ob.asks
            level_sz = book.get(px, Decimal("0"))
            act = self.active[side]

            #don't reset on partial fills
            if act is None or act["px"] != px or act["posted_qty"] != qty:
                self.active[side] = {
                    "px": px,
                    "posted_qty": qty,
                    "qty_rem": qty,
                    "queue_ahead": max(level_sz, Decimal("0")),  # ahead at placement
                    "last_level_sz": level_sz
                }
            else:
                # If more size joined our price, assume it queued ahead of us (conservative)
                if level_sz > act["last_level_sz"]:
                    act["queue_ahead"] += (level_sz - act["last_level_sz"])
                # If size shrank (cancels)
                elif level_sz < act["last_level_sz"]:
                    delta = act["last_level_sz"] - level_sz
                    act["queue_ahead"] = max(Decimal("0"), act["queue_ahead"] - delta)
                act["last_level_sz"] = level_sz

    # Fills (from trade prints + FIFO state sync)
    def on_fill(self, side: str, size: Decimal, price: Decimal) -> None:
        if side == "buy":
            self.position += size
            self.cash -= size * price
        else:
            self.position -= size
            self.cash += size * price

    
    def maybe_fill_from_trade(self, trade: dict) -> list[tuple[str, float, float]]:
        """
        Coinbase maker-side semantics assumed:
          trade['side'] == 'buy'  -> maker was bid  -> check our BID
          trade['side'] == 'sell' -> maker was ask  -> check our ASK
        At the trade price, consume queue_ahead first, then our qty_rem.
        """
        fills: list[tuple[str, float, float]] = []
        p = Decimal(str(trade["price"]))
        s = Decimal(str(trade["size"]))
        tside = trade["side"]

        if tside == "buy":
            act = self.active.get("bid")
            if act and act["px"] is not None and abs(p - act["px"]) <= self._tol:
                hit = s
                eat = min(hit, act["queue_ahead"])
                act["queue_ahead"] -= eat
                hit -= eat
                if hit > 0 and act["qty_rem"] > 0:
                    fill = min(hit, act["qty_rem"])
                    self.on_fill("buy", fill, p)
                    act["qty_rem"] -= fill
                    fills.append(("buy", float(fill), float(p)))
                if act["qty_rem"] <= 0:
                    self.active["bid"] = None

        elif tside == "sell":
            act = self.active.get("ask")
            if act and act["px"] is not None and abs(p - act["px"]) <= self._tol:
                hit = s
                eat = min(hit, act["queue_ahead"])
                act["queue_ahead"] -= eat
                hit -= eat
                if hit > 0 and act["qty_rem"] > 0:
                    fill = min(hit, act["qty_rem"])
                    self.on_fill("sell", fill, p)
                    act["qty_rem"] -= fill
                    fills.append(("sell", float(fill), float(p)))
                if act["qty_rem"] <= 0:
                    self.active["ask"] = None

        return fills
