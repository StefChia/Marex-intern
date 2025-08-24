
from __future__ import annotations
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING


# Basic MarketMaker (NO FIFO)
class MarketMaker:
    """
    Simple market-maker:
      - Quotes around mid with a base spread (bps) derived from tick size
      - Skews quotes vs inventory (to mean-revert position)
      - Simulates fills from trade prints (matches)
    """
    def __init__(
        self,            
        q_size: Decimal | float = "0.05",         # quote size in BTC
        skew_k: Decimal | float = "0.25",         # skew aggressiveness (multiplies base)
        tick: Decimal | float = "0.01",           # BTC-USD tick (USD)
        
        # how aggressively you want to fill (lower TICKS per side)
        target_ticks_per_side: Decimal = Decimal("1.0"),   
        join_touch: bool = True                              
    ) -> None:

        self.base_bps = Decimal()
        self.q_size   = Decimal(str(q_size))
        self.skew_k   = Decimal(str(skew_k))
        self.tick     = Decimal(str(tick))

        self.target_ticks_per_side = Decimal(str(target_ticks_per_side))
        self.join_touch            = bool(join_touch)

        self.quotes   = {"bid": (None, Decimal(0)), "ask": (None, Decimal(0))}
        self.position = Decimal("0")
        self.cash     = Decimal("0")
        self.last_mid: Decimal | None = None
        self.skew_pwr = Decimal("0")

    def _round_to_tick(self, px: Decimal) -> Decimal:
        # round to nearest tick without float errors
        return (px / self.tick).quantize(Decimal(1)) * self.tick

    def _tick_bps(self, mid: Decimal) -> Decimal:
        # 1 tick expressed in bps at this mid
        return (self.tick / mid) * Decimal(1e4)

    def _set_base_bps_from_ticks(self, mid: Decimal) -> None:
        # base_bps = max(target_ticks * tick_bps, tick_bps)  -> at least 1 tick
        tick_bps = self._tick_bps(mid)
        base = max(self.target_ticks_per_side * tick_bps, tick_bps)
        self.base_bps = base

    def make_quotes(self, mid: Decimal, pos: Decimal, pos_limit: Decimal) -> dict:
        """
        Return dict: {"bid": (price, size), "ask": (price, size)}
        Skew: if long, worsen bid / improve ask; if short, opposite.
        """
        self.last_mid = Decimal(mid)

        # set base_bps from tick so we quote at/near the touch
        self._set_base_bps_from_ticks(self.last_mid)
        base = self.base_bps

        # smooth inventory signal in [-1, 1]
        denom = (pos_limit if pos_limit != 0 else Decimal("1"))
        inv = (pos / denom)
        inv = max(Decimal("-1"), min(Decimal("1"), inv))

        # skew without cap (as requested)
        self.skew_pwr   = self.skew_k * inv              # dimensionless
        skew_bps        = self.skew_pwr * base           # in bps

        # price construction
        one = Decimal(1)
        bps = Decimal(1e4)
        bid_theo = self.last_mid * (one - (base + skew_bps) / bps)
        ask_theo = self.last_mid * (one + (base - skew_bps) / bps)

        bid_px = self._round_to_tick(bid_theo)
        ask_px = self._round_to_tick(ask_theo)

        # snap to touch intent: ensure at least 1 tick wide and no cross after rounding
        if self.join_touch and bid_px >= ask_px:
            ask_px = bid_px + self.tick

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







#DEFINING MarketMaker FOR FIFO

def _round_bid(px: Decimal, tick: Decimal) -> Decimal:
    return px.quantize(tick, rounding=ROUND_FLOOR)

def _round_ask(px: Decimal, tick: Decimal) -> Decimal:
    return px.quantize(tick, rounding=ROUND_CEILING)

def _best_bid(ob) -> Decimal | None:
    # expects ob.bids: dict[price->size]
    return max(ob.bids) if getattr(ob, "bids", None) else None

def _best_ask(ob) -> Decimal | None:
    # expects ob.asks: dict[price->size]
    return min(ob.asks) if getattr(ob, "asks", None) else None


class MarketMakerFIFO:
    """
    FIFO (price-time) market-maker:
      - When you (re)post a quote at price px, you start BEHIND the current size at px.
      - Each trade at px first consumes queue_ahead, then your qty_rem (you get filled).
    """
    def __init__(
        self,
        q_size:  Decimal | float = "0.05",      # BTC per quote
        skew_k:  Decimal | float = "0.25",      # aggressiveness
        tick:    Decimal | float = "0.01",      # BTC-USD tick
        # how aggressively you want to fill (lower TICKS per side)
        target_ticks_per_side: Decimal = Decimal("1.0"),   
        join_touch: bool = True                              
    ) -> None:
        self.base_bps = Decimal()
        self.q_size   = Decimal(str(q_size))
        self.skew_k   = Decimal(str(skew_k))
        self.tick     = Decimal(str(tick))
        
        self.target_ticks_per_side = Decimal(str(target_ticks_per_side))
        self.join_touch            = bool(join_touch)

        self.quotes = {"bid": (None, Decimal(0)), "ask": (None, Decimal(0))}
        self.position = Decimal("0")
        self.cash = Decimal("0")
        self.last_mid: Decimal | None = None

        self.skew_pwr = Decimal("0")  

        # FIFO state per side: {"px": Decimal, "qty_rem": Decimal, "queue_ahead": Decimal}
        self.active = {"bid": None, "ask": None}
        self._tol = self.tick / 2  # price matching tolerance

    def _round_to_tick(self, px: Decimal) -> Decimal:
        # round to nearest tick without float errors
        return (px / self.tick).quantize(Decimal(1)) * self.tick

    def _tick_bps(self, mid: Decimal) -> Decimal:
        # 1 tick expressed in bps at this mid
        return (self.tick / mid) * Decimal(1e4)

    def _set_base_bps_from_ticks(self, mid: Decimal) -> None:
        tick_bps = self._tick_bps(mid)
        base = max(self.target_ticks_per_side * tick_bps, tick_bps)
        self.base_bps = base
        
    #Our Quotes
    def make_quotes(self, mid: Decimal, pos: Decimal, pos_limit: Decimal, ob=None) -> dict:
        """
        Return dict: {"bid": (price, size), "ask": (price, size)}
        Skew: if long, worsen bid / improve ask; if short, opposite.
        """
        self.last_mid = Decimal(mid)

        # set base_bps from tick so we quote at/near the touch
        self._set_base_bps_from_ticks(self.last_mid)
        base = self.base_bps

        # smooth inventory signal in [-1, 1]
        denom = (pos_limit if pos_limit != 0 else Decimal("1"))
        inv = (pos / denom)
        inv = max(Decimal("-1"), min(Decimal("1"), inv))

        # skew 
        self.skew_pwr   = self.skew_k * inv              
        skew_bps        = self.skew_pwr * base           # in bps

       
        one = Decimal(1)
        bps = Decimal(1e4)
        bid_theo = self.last_mid * (one - (base + skew_bps) / bps)
        ask_theo = self.last_mid * (one + (base - skew_bps) / bps)
        bid_px = _round_bid(bid_theo, self.tick)
        ask_px = _round_ask(ask_theo, self.tick)

     
        # In a 1-tick-wide market, mid-based rounding leaves you 1 tick behind.
        if self.join_touch and ob is not None:
            bb = _best_bid(ob)
            ba = _best_ask(ob)
            if bb is not None and ba is not None:
                # distance BEHIND top-of-book in ticks:
                #  - 1.0 -> 0 behind (join the touch)
                #  - 2.0 -> 1 behind, etc.
                behind = int(max(Decimal("0"), self.target_ticks_per_side - Decimal("1")))
                bid_px = bb - behind * self.tick
                ask_px = ba + behind * self.tick

        # snap to touch intent: ensure at least 1 tick wide and no cross after rounding
        if self.join_touch and bid_px >= ask_px:
            ask_px = bid_px + self.tick

        self.quotes = {"bid": (bid_px, self.q_size), "ask": (ask_px, self.q_size)}
        return self.quotes

    # FIFO state sync 
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

            act = self.active[side]
            level_sz = (ob.bids if side == "bid" else ob.asks).get(px, Decimal("0"))

            # post if first time, price changed, or displayed size changed
            if act is None or act["px"] != px or act.get("posted_qty", Decimal(0)) != qty:
                self.active[side] = {
                    "px": px,
                    "posted_qty": qty,
                    "qty_rem": qty,
                    "queue_ahead": level_sz,
                    "last_level_sz": level_sz
                }
            else:
                if level_sz > act["last_level_sz"]:
                    act["queue_ahead"] += (level_sz - act["last_level_sz"])
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
        FIFO fills from Coinbase trade prints (maker-side semantics):
          - trade['side'] == 'buy'  -> maker was bid (taker sold)  -> check our BID
          - trade['side'] == 'sell' -> maker was ask (taker bought) -> check our ASK
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
                eat = min(hit, act["queue_ahead"])     # through queue ahead
                act["queue_ahead"] -= eat
                act["queue_ahead"] = max(Decimal("0"), act["queue_ahead"])
                hit -= eat
                if hit > 0 and act["qty_rem"] > 0:     # our turn
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
                act["queue_ahead"] = max(Decimal("0"), act["queue_ahead"])
                hit -= eat
                if hit > 0 and act["qty_rem"] > 0:
                    fill = min(hit, act["qty_rem"])
                    self.on_fill("sell", fill, p)
                    act["qty_rem"] -= fill
                    fills.append(("sell", float(fill), float(p)))
                if act["qty_rem"] <= 0:
                    self.active["ask"] = None

        return fills





