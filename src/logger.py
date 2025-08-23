
from __future__ import annotations
import atexit, csv, os
from typing import Dict, Iterable, Optional

def _to_str(x) -> str:
    if x is None: return ""
    return str(x)  

class CSVLogger:
    def __init__(self, root: str = "data") -> None:
        os.makedirs(root, exist_ok=True)

        self._f_tr = open(os.path.join(root, "trades.csv"), "a", newline="")
        self._w_tr = csv.writer(self._f_tr)
        self._maybe_write_header(self._f_tr, ["ts","side","price","size","position_after","realized","unrealized","total"])

        self._f_pnl = open(os.path.join(root, "pnl.csv"), "a", newline="")
        self._w_pnl = csv.writer(self._f_pnl)
        self._maybe_write_header(self._f_pnl, ["ts","mid","position","exposure","realized","unrealized","total","mode"])

        self._f_sp = open(os.path.join(root, "spreads.csv"), "a", newline="")
        self._w_sp = csv.writer(self._f_sp)
        self._sizes_cols: Optional[Iterable[str]] = None
        
        # NEW: power curves (bid/ask)
        self._f_bid = open(os.path.join(root, "power_bid.csv"), "a", newline="")
        self._w_bid = csv.writer(self._f_bid)
        self._sizes_cols_bid = None  

        self._f_ask = open(os.path.join(root, "power_ask.csv"), "a", newline="")
        self._w_ask = csv.writer(self._f_ask)
        self._sizes_cols_ask = None

        atexit.register(self.close)

    def _maybe_write_header(self, f, cols):
        if f.tell() == 0:
            csv.writer(f).writerow(cols); f.flush()

    def log_trade_and_pnl(self, ts_iso: str, side: str, price, size, snap) -> None:
        # snap: RiskSnapshot
        row = [
            ts_iso, side, _to_str(price), _to_str(size),
            _to_str(snap.position), _to_str(snap.realized),
            _to_str(snap.unrealized), _to_str(snap.total)
        ]
        self._w_tr.writerow(row); self._f_tr.flush()

    def log_pnl(self, ts_iso: str, snap) -> None:
        row = [
            ts_iso, _to_str(snap.mid), _to_str(snap.position),
            _to_str(snap.exposure_usd), _to_str(snap.realized),
            _to_str(snap.unrealized), _to_str(snap.total), snap.mode
        ]
        self._w_pnl.writerow(row); self._f_pnl.flush()

    def log_spreads(self, ts_iso: str, spreads_snapshot: Dict) -> None:
        # spreads_snapshot: output of compute_spreads_snapshot()
        mid = spreads_snapshot.get("mid")
        top = spreads_snapshot.get("top_of_book", {})
        sizes = spreads_snapshot.get("sizes", {})

        # initialize header if first time
        if self._sizes_cols is None:
            cols = ["ts","mid","top_usd","top_bps"]
            sz_cols = []
            for s in sizes.keys():
                s_str = str(s)
                sz_cols += [f"s{s_str}_usd", f"s{s_str}_bps"]
            self._sizes_cols = sz_cols
            self._w_sp.writerow(cols + sz_cols); self._f_sp.flush()

        row = [ts_iso, _to_str(mid), _to_str(top.get("usd")), _to_str(top.get("bps"))]
        for s in sizes.keys():
            d = sizes[s]
            row += [_to_str(d.get("usd")), _to_str(d.get("bps"))]
        self._w_sp.writerow(row); self._f_sp.flush()
        
        
    def log_power_curve(self, ts_iso: str, side: str, data: Dict) -> None:
        """
        data: {size -> value}. We assume 'size' as keys .
        """
        side = side.lower()
        sizes_now = [str(s) for s in data.keys()]  
        if side == "bid":
            if self._sizes_cols_bid is None:
                # write header once
                self._sizes_cols_bid = sizes_now
                self._w_bid.writerow(["ts"] + self._sizes_cols_bid); self._f_bid.flush()
            row = [ts_iso] + [_to_str(data[s]) for s in data.keys()]
            self._w_bid.writerow(row); self._f_bid.flush()

        elif side == "ask":
            if self._sizes_cols_ask is None:
                self._sizes_cols_ask = sizes_now
                self._w_ask.writerow(["ts"] + self._sizes_cols_ask); self._f_ask.flush()
            row = [ts_iso] + [_to_str(data[s]) for s in data.keys()]
            self._w_ask.writerow(row); self._f_ask.flush()

        else:
            return None 
        

    def close(self):
        for f in (self._f_tr, self._f_pnl, self._f_sp, self._f_bid, self._f_ask):
            try: f.flush(); f.close()
            except Exception: pass
