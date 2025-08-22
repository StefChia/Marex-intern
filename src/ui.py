
# src/ui.py
from __future__ import annotations
from decimal import Decimal
from typing import Dict, Tuple, Optional, Iterable

from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box

console = Console()

def _fmt(x: Optional[Decimal], nd: int = 2, none: str = "-") -> str:
    if x is None:
        return none
    try:
        return f"{x:.{nd}f}"
    except Exception:
        return str(x)

def _book_table(ob, depth: int = 5) -> Table:
    bids, asks = ob.top_n(depth)
    t = Table(title="Order Book (Top Levels)", box=box.SIMPLE, show_lines=False, expand=True)
    t.add_column("Ask Px", justify="right")
    t.add_column("Ask Sz", justify="right")
    t.add_column("")
    t.add_column("Bid Px", justify="right")
    t.add_column("Bid Sz", justify="right")

    # align rows: highest asks at bottom, highest bids at top visually
    max_rows = max(len(asks), len(bids))
    ask_rows = asks[:]
    bid_rows = bids[:]
    # asks are ascending; show highest near mid toward bottom
    # we'll print from bottom part of arrays to top with padding
    for i in range(max_rows):
        a = ask_rows[i] if i < len(ask_rows) else (None, None)
        b = bid_rows[i] if i < len(bid_rows) else (None, None)
        apx, asz = a
        bpx, bsz = b
        t.add_row(
            _fmt(apx, 2), _fmt(asz, 6), "⟷",
            _fmt(bpx, 2), _fmt(bsz, 6),
        )
    return t

def _spreads_table(tracker, sizes: Iterable[Decimal]) -> Table:
    rep = tracker.report()
    cur = rep.get("current", {})
    top = cur.get("top_of_book", {})
    t = Table(title="Spreads (Current & Rolling Avg)", box=box.SIMPLE, expand=True)
    t.add_column("Metric")
    t.add_column("Current", justify="right")
    t.add_column("Avg (bps)", justify="right")
    t.add_column("Min/Max (bps)", justify="right")

    # Top of book
    top_bps_cur = top.get("bps")
    roll_top = rep.get("rolling", {}).get("top", {}).get("bps", {})
    t.add_row(
        "Top-of-book",
        f"${_fmt(top.get('usd'), 2)} ({_fmt(top_bps_cur, 2)} bps)",
        _fmt(roll_top.get("avg"), 2),
        f"{_fmt(roll_top.get('min'), 2)} / {_fmt(roll_top.get('max'), 2)}",
    )

    # Size-aware
    cur_sizes = cur.get("sizes", {})
    roll_sizes = rep.get("rolling", {}).get("sizes", {})
    for s in sizes:
        cs = cur_sizes.get(s, {})
        rs = roll_sizes.get(s, {})
        t.add_row(
            f"{s} BTC",
            (f"${_fmt(cs.get('usd'), 2)} ({_fmt(cs.get('bps'), 2)} bps)"
             if cs.get('usd') is not None else "insufficient depth"),
            _fmt(rs.get("bps", {}).get("avg"), 2),
            f"{_fmt(rs.get('bps', {}).get('min'), 2)} / {_fmt(rs.get('bps', {}).get('max'), 2)}",
        )
    return t

def _quotes_table(quotes: Dict[str, Tuple[Optional[Decimal], Decimal]], mm) -> Table:
    t = Table(title="Quotes", box=box.SIMPLE, expand=True)
    t.add_column("Side")
    t.add_column("Price", justify="right")
    t.add_column("Size", justify="right")
    bid_px, bid_sz = quotes.get("bid", (None, Decimal(0)))
    ask_px, ask_sz = quotes.get("ask", (None, Decimal(0)))
    t.add_row("Bid", _fmt(bid_px, 2), _fmt(bid_sz, 6))
    t.add_row("Ask", _fmt(ask_px, 2), _fmt(ask_sz, 6))
    t.caption = f"Params: base={mm.base_bps} bps | q_size={_fmt(mm.q_size, 6)} BTC"
    return t

def _risk_panel(snap) -> Panel:
    body = Table.grid(expand=True)
    body.add_column(justify="left")
    body.add_column(justify="right")
    body.add_row("Mode", f"[bold]{snap.mode}[/bold]")
    body.add_row("Position (BTC)", _fmt(snap.position, 6))
    body.add_row("Exposure (USD)", f"${_fmt(snap.exposure_usd, 0)}")
    body.add_row("Avg Entry", _fmt(snap.avg_entry, 2))
    body.add_row("Realized PnL", f"${_fmt(snap.realized, 0)}")
    body.add_row("Unrealized PnL", f"${_fmt(snap.unrealized, 0)}")
    body.add_row("Total PnL", f"[bold]${_fmt(snap.total, 0)}[/bold]")
    return Panel(body, title="Risk & PnL", box=box.ROUNDED)

def _trades_table(tbuf, n: int = 12) -> Table:
    t = Table(title=f"Recent Trades (last {n})", box=box.SIMPLE, expand=True)
    t.add_column("Time", justify="right")
    t.add_column("Side", justify="center")
    t.add_column("Size", justify="right")
    t.add_column("Price", justify="right")
    for tr in tbuf.recent(n):
        t.add_row(
            tr["time"].replace("T", " ").replace("Z", ""),
            tr["side"],
            f"{tr['size']:.6f}",
            f"{tr['price']:.2f}",
        )
    return t

def render_dashboard(ob, tracker, sizes, mm, risk, tbuf):
    mid = ob.mid()
    snap = risk.snapshot(mid)
    # Gate whatever mm has most recently produced (don't re-make quotes here)
    quotes = risk.gate_quotes(mm.quotes, snap)

    header = Panel(
        f"mid={_fmt(mid, 2)} | bb/ba= {_fmt(ob.best_bid()[0],2)} / {_fmt(ob.best_ask()[0],2)}",
        title="[bold]BTC-USD — Live MM[/bold]",
        box=box.ROUNDED,
    )

    layout = Layout(name="root")
    layout.split_column(
        Layout(header, size=3),
        Layout(name="main", ratio=1)
    )
    layout["main"].split_row(
        Layout(Panel(Group(_book_table(ob), _spreads_table(tracker, sizes)), title="Market", box=box.ROUNDED), ratio=2),
        Layout(Panel(Group(_quotes_table(quotes, mm), _risk_panel(snap), _trades_table(tbuf)), title="Strategy", box=box.ROUNDED), ratio=3),
    )
    return layout

async def run_ui(ob, tracker, sizes, mm, risk, tbuf, refresh: float = 0.25):
    # Avoid spamming prints when Live is running; prefer console.log for one-off events elsewhere if needed
    with Live(render_dashboard(ob, tracker, sizes, mm, risk, tbuf),
              refresh_per_second=int(1/refresh) if refresh > 0 else 4,
              screen=True, console=console):
        # The Live context will keep updating when .update is called
        import asyncio
        while True:
            layout = render_dashboard(ob, tracker, sizes, mm, risk, tbuf)
            console.live.update(layout)  # type: ignore[attr-defined]
            await asyncio.sleep(refresh)
