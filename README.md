# Marex-intern
Exercise for Marex crypto intern

A minimal market-making simulator on BTC-USD with live L2 book, size-aware spreads, inventory-skewed quotes, simulated maker fills, risk limits, logging, and a console UI.

WHAT THIS DOES:
Streams market data from Coinbase (WebSocket).
Maintains a live Level-2 order book.
Computes size-aware spreads (VWAP buy/sell for 0.1 / 1 / 5 / 10 BTC).
Quotes around mid with inventory skew.
Simulates maker fills from trade prints.
Tracks PnL (R/U/T) and exposure, enforces: Max notional exposure = $1,000,000 & Max loss = $100,000
Logs spreads, PnL, fills, and power curves (impact vs size).
Provides a neat console UI (Rich).

```text
PROJECT COMPOSITION:
/src
  exchange.py       # WebSocket client (level2_batch + matches)
  orderbook.py      # L2 book (snapshot + l2update)
  analytics.py      # size-aware spreads, rolling stats, power curves
  strategy.py       # quoting + (simulated) maker fills
  trade_buffer.py   # recent trades
  risk.py           # exposure, PnL, gating (normal/exposure/loss_cut)
  logger.py         # CSV logs (spreads, pnl, trades, power curves)
  ui.py             # live dashboard (Rich)
  main.py           # final app (WS + quotes + UI)

  plots.py            # plot the logs saved in data (i.e. Time Series for spreads, PnL and Inventory)
  plot_curves_pwr.py  # (optional) animated power curves overlay

  #I also left previous main.py version if someone want to run without UI:
  main1.py          # Display just the websockets output
  main2.py          # Display analytics for spreads at each size
  main3.py          # Final app without UI

/data               # CSV output (created on first run)
README.md
requirements.txt
```

Keeping in mind also some of the topics discussed during the interview I also added:

1) POWER BID AND POWER ASK
   
Intuition:
power_ask: the buy-side price impact curve — how many bps above mid you’d pay to instantly buy size S from the asks.
power_bid: the sell-side price impact curve — how many bps relative to mid you’d get (or give up) to instantly sell size S into the bids.
Summerize depth and liquidity. The more convex/concave the two curves are the more impact (i.e. shock lift of ask or crash of bid) will be generated for the same quantity compared to a linear curve.
Logs of the two curves evolution are saved in /data: power_bid.csv & power_ask.csv
A simple animation of the dynamics of this curves (hence of the orderbook) is shown running plot_curves_pwr.py
Further analysis of these and other metrics could potentially provide signals.

2) SHOW THE 'SKEW_POWER' IN OUR QUOTES:
   
I have added the skew_power to show how we dynamically (based on exposition) we skew the bid-ask quotes to revert back.


```text
MORE KEY INSIGHTS & RECALLS:

MATCHING SIDE (websockets definition of "side")
On Coinbase’s match / last_match messages, the field side tells you the maker’s side:
So the side is not the aggressor; it’s the resting order that got hit/lifted.

ABOUT LOGS: (csv output) 
Five files in will be produced in /data:
trades.csv — each fill + PnL at that moment.
pnl.csv — Realized/Unrealized/Total PnL & exposure.
spreads.csv — time series of top-of-book and size-aware spreads.
power_ask.csv - evolution of the ask curve in orderbook (see Power Ask)
power_bid.csv - evolution of the bid curve in orderbook (see Power Bid)
(If you restart the app, logs will be append ed; delete old CSVs if you want a fresh run.)
```

STRATEGY:(Potential further developments)
make base_bps adaptive to short-term volatility (wider when vol spikes, tighter when calm),
and make q_size smaller as your inventory grows.
+
MAKE a mkt making FIFO Simulation.







