# Marex-intern
Exercise for Marex crypto intern

A minimal market-making simulator on BTC-USD with live L2 book, size-aware spreads, inventory-skewed quotes, simulated maker fills, risk limits, logging, and a console UI.


```text
TO RUN (run these files in this order):

- pip install -r requirements.txt  
- main.py
- plots.py
- plot_curves_pwr.py
```


WHAT IT DOES:
Streams market data from Coinbase (WebSocket).
Maintains a live Level-2 order book.
Computes size-aware spreads (VWAP buy/sell for 0.1 / 1 / 5 / 10 BTC).
Quotes around mid with inventory skew. (both target spread and target tick-based spread)
Simulates maker fills from trade prints. (both Basic and FIFO)
Tracks PnL (R/U/T) and exposure, enforces: Max notional exposure = $1,000,000 & Max loss = $100,000
Logs spreads, PnL, fills, and power curves (impact vs size).
Provides a neat console UI (Rich).

```text
PROJECT COMPOSITION:
/src
  exchange.py          # WebSocket client (level2_batch + matches)
  orderbook.py         # L2 book (snapshot + l2update)
  analytics.py         # size-aware spreads, rolling stats, power curves

  strategy.py          # quoting + (simulated) maker fills + Tick based rule for base spread bps
  strategy_ex_base.py  # same as strategy but allows for arbitrary base spread bps (suboptimal, see Insights below)
  
  trade_buffer.py      # recent trades
  risk.py              # exposure, PnL, gating (normal/exposure/loss_cut)
  logger.py            # CSV logs (spreads, pnl, trades, power curves)
  ui.py                # live dashboard (Rich)
  main.py              # final app (WS + quotes + UI)

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
   
I have added the skew_power to show how we dynamically (based on exposition) we skew the bid-ask quotes to mean-revert back.


3) USE A FIFO MarketMaker

Intuition: Trades must go through the queue ahead before filling our quotes.
   


```text
MORE KEY INSIGHTS & RECALLS:

MATCHING SIDE (websockets definition of "side")
On Coinbase’s match / last_match messages, the field side tells you the maker’s side:
So the side is not the aggressor; it’s the resting order that got hit/lifted.

STRATEGY (To choose the base spread in bps):
 Fills happen at the exchange’s ticks, not at arbitrary bps. Instead of choosing a spread in bps,that would need a base bps of 0.001 for no FIFO case,the tick‑based rule chooses the spread in ticks first, so after rounding we are exactly at the best bid/ask and actually get in the queue.
 Another benefit of tick base rule is that also using Fifo I am filling more trades since I have less query ahead compared to the other case (i.e. arbitrary base spread bps)

 I also left the strategy_ex_base.py file to allow to make quotes at an arbitrary spread anyway but you have to manually find a proxy of 1-2 tick base bps to actually fill something and the tick base bps is also mid dependent.

ABOUT LOGS: (csv output) 
Five files in will be produced in /data:
trades.csv — each fill + PnL at that moment.
pnl.csv — Realized/Unrealized/Total PnL & exposure.
spreads.csv — time series of top-of-book and size-aware spreads.
power_ask.csv - evolution of the ask curve in orderbook (see Power Ask)
power_bid.csv - evolution of the bid curve in orderbook (see Power Bid)
(If you restart the app, logs will be append ed; delete old CSVs if you want a fresh run.)
```

STRATEGY:

Both Tick-based rule and target base spread in bps.
+
MAKE a basic mkt making Simulation. (In order to match tick-based and arbitrary base spread bps, I choose the latter to be 0.0008)
+
MAKE a FIFO mkt making Simulation. (Since it's way more difficult to fill I reduced the base spread bps to 0.0001 otherwise we would not have filled enough trades to run the next steps).

(Potential further developments):
make base_bps adaptive to short-term volatility (wider when vol spikes, tighter when calm),
and make q_size smaller as your inventory grows.









