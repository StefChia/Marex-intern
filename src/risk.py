
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Tuple

@dataclass
class RiskSnapshot:
    mid: Optional[Decimal]
    position: Decimal
    exposure_usd: Decimal
    avg_entry: Optional[Decimal]
    realized: Decimal
    unrealized: Decimal
    total: Decimal
    mode: str           # "normal" | "exposure" | "loss_cut"

class RiskManager:
    """
    Tracks realized/unrealized PnL and enforces:
      - max notional exposure (USD)
      - max loss (USD)
    Gating policy:
      - Exposure breach  -> quote only the FLATTENING side
      - Max loss breach  -> quote only the FLATTENING side (loss-cut mode)
    """
    def __init__(self,
                 max_exposure_usd: Decimal | float = 1_000_000,
                 max_loss_usd: Decimal | float = 100_000):
        self.max_exp = Decimal(str(max_exposure_usd))
        self.max_loss = Decimal(str(max_loss_usd))

        self.pos = Decimal("0")
        self.avg_entry: Optional[Decimal] = None
        self.realized = Decimal("0")

    # ---------- PnL & inventory accounting ----------
    def on_fill(self, side: str, size: Decimal, price: Decimal) -> None:
        """
        Update position, realized PnL and avg entry.
        side: "buy" or "sell"; size>0; price>0
        """
        sz = Decimal(size); px = Decimal(price)
        prev_pos = self.pos
        new_pos = prev_pos + (sz if side == "buy" else -sz)

        # Same-direction add -> weighted average entry
        if prev_pos == 0 or (prev_pos > 0 and new_pos > 0 and abs(new_pos) > abs(prev_pos)) \
           or (prev_pos < 0 and new_pos < 0 and abs(new_pos) > abs(prev_pos)):
            # adding to open position
            if prev_pos == 0:
                self.avg_entry = px
            else:
                tot = abs(prev_pos) + sz
                self.avg_entry = (abs(prev_pos) * self.avg_entry + sz * px) / tot  # type: ignore

        # Reducing or flipping -> realize PnL on closed portion
        else:
            closed = min(abs(sz), abs(prev_pos))
            # sign(prev_pos): +1 long, -1 short
            sgn = Decimal(1) if prev_pos > 0 else Decimal(-1)
            per_unit = (px - self.avg_entry) * sgn  # type: ignore
            self.realized += closed * per_unit
            # If flipped through zero, reset avg_entry for the remaining open part
            if prev_pos * new_pos < 0:
                remaining = abs(sz) - closed
                if remaining > 0:
                    self.avg_entry = px  # new side opens at this trade price
                else:
                    self.avg_entry = None

        # If flat, clear avg entry
        self.pos = new_pos
        if self.pos == 0:
            self.avg_entry = None

    def _unrealized(self, mid: Optional[Decimal]) -> Decimal:
        if mid is None or self.avg_entry is None or self.pos == 0:
            return Decimal("0")
        return self.pos * (mid - self.avg_entry)

    def snapshot(self, mid: Optional[Decimal]) -> RiskSnapshot:
        exposure = abs(self.pos) * (mid if mid is not None else Decimal("0"))
        unreal = self._unrealized(mid)
        total = self.realized + unreal

        mode = "normal"
        if total <= -self.max_loss:
            mode = "loss_cut"
        elif exposure >= self.max_exp:
            mode = "exposure"

        return RiskSnapshot(
            mid=mid, position=self.pos, exposure_usd=exposure,
            avg_entry=self.avg_entry, realized=self.realized,
            unrealized=unreal, total=total, mode=mode
        )

    # ---------- Quote gating ----------
    def gate_quotes(self, quotes: Dict[str, Tuple[Optional[Decimal], Decimal]],
                    snap: RiskSnapshot) -> Dict[str, Tuple[Optional[Decimal], Decimal]]:
        """
        Return quotes with the risk-adding side suppressed when needed.
        quotes = {"bid": (price_or_None, size), "ask": (price_or_None, size)}
        """
        out = dict(quotes)
        if snap.mode in ("exposure", "loss_cut"):
            # Keep only the FLATTENING side
            if self.pos > 0:
                # Long -> only sell (ask) to reduce
                out["bid"] = (None, Decimal("0"))
            elif self.pos < 0:
                # Short -> only buy (bid) to reduce
                out["ask"] = (None, Decimal("0"))
            else:
                # Flat but loss_cut: safest is don't add risk; here we keep both off
                if snap.mode == "loss_cut":
                    out["bid"] = (None, Decimal("0"))
                    out["ask"] = (None, Decimal("0"))
        return out
