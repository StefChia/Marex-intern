
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

def _prep(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only numeric-ish columns (sizes) and sort them ascending."""
    cols = []
    for c in df.columns:
        try:
            float(c); cols.append(c)
        except: pass
    df = df[cols].copy()
    order = np.argsort([float(c) for c in df.columns])
    return df.iloc[:, order]

def _load_power(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "ts" in df.columns:
        df = df.set_index("ts")
    return _prep(df)

def play_power_overlay(ask_csv="data/power_ask.csv",
                       bid_csv="data/power_bid.csv",
                       fps: int = 30,
                       tail: int = 0,
                       ylim='auto'):
    # Load & align on common timestamps and common size columns
    A = _load_power(ask_csv)
    B = _load_power(bid_csv)

    # inner-join on time
    df = A.join(B, how="inner", lsuffix="_ask", rsuffix="_bid")
    # intersect the size columns (as strings) present in both
    sizes_ask = [c[:-4] for c in df.columns if c.endswith("_ask")]
    sizes_bid = [c[:-4] for c in df.columns if c.endswith("_bid")]
    common = sorted(set(sizes_ask).intersection(sizes_bid), key=lambda x: float(x))

    # build aligned matrices (T, N)
    Ask = df[[f"{s}_ask" for s in common]].to_numpy(float)
    Bid = df[[f"{s}_bid" for s in common]].to_numpy(float)  
    sizes = np.array([float(s) for s in common], dtype=float)

    T, N = Ask.shape
    if T == 0 or N == 0:
        raise ValueError("No overlapping timestamps/sizes between power_ask and power_bid.")

    fig, ax = plt.subplots()
    (line_ask,) = ax.plot([], [], lw=2, label="Ask impact") 
    (line_bid,) = ax.plot([], [], lw=2, label="Bid impact")

    trails_ask, trails_bid = [], []
    if tail > 0:
        for k in range(tail):
            (ta,) = ax.plot([], [], lw=1, alpha=max(0.15, 0.6*(1-(k+1)/(tail+1))))
            (tb,) = ax.plot([], [], lw=1, alpha=max(0.15, 0.6*(1-(k+1)/(tail+1))))
            trails_ask.append(ta); trails_bid.append(tb)

    ax.set_xlim(np.nanmin(sizes), np.nanmax(sizes))
    if ylim == 'auto':
        ymin = np.nanmin(np.concatenate([Ask, Bid]))
        ymax = np.nanmax(np.concatenate([Ask, Bid]))
        pad = 0.05 * (ymax - ymin if ymax > ymin else 1.0)
        ax.set_ylim(ymin - pad, ymax + pad)
    else:
        ax.set_ylim(*ylim)
    ax.set_xlabel("Size")
    ax.set_ylabel("Impact (bps)")
    ax.legend()

    def init():
        line_ask.set_data([], [])
        line_bid.set_data([], [])
        for ta, tb in zip(trails_ask, trails_bid):
            ta.set_data([], []); tb.set_data([], [])
        ax.set_title("")
        return (line_ask, line_bid, *trails_ask, *trails_bid)

    def update(i):
        line_ask.set_data(sizes, Ask[i])
        line_bid.set_data(sizes, Bid[i])  #<=0
        for k in range(tail):
            j = i - (k+1)
            if j >= 0:
                trails_ask[k].set_data(sizes, Ask[j])
                trails_bid[k].set_data(sizes, Bid[j])
            else:
                trails_ask[k].set_data([], [])
                trails_bid[k].set_data([], [])
        ax.set_title(f"Frame {i+1}/{T}")
        return (line_ask, line_bid, *trails_ask, *trails_bid)

    anim = FuncAnimation(fig, update, frames=T, init_func=init, blit=True, interval=1000/fps)
    plt.show()
    return anim



if __name__ == "__main__": 
    play_power_overlay()