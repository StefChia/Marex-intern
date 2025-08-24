
import csv
from datetime import datetime
import matplotlib.pyplot as plt


def _read_csv(path):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
    return rows

def _parse_ts(ts):
    try: return datetime.fromisoformat(ts.replace("Z","+00:00"))
    except: return None

def plot_pnl():
    rows = _read_csv("data/pnl.csv")
    t = [_parse_ts(r["ts"]) for r in rows]
    total = [float(r["total"]) if r["total"] else 0.0 for r in rows]
    unreal = [float(r["unrealized"]) if r["unrealized"] else 0.0 for r in rows]

    plt.figure()
    plt.plot(t, total, label="Total PnL")
    plt.plot(t, unreal, label="Unrealized PnL")
    plt.legend()
    plt.title("PnL Over Time")
    plt.xlabel("Time"); plt.ylabel("USD")
    plt.tight_layout()
    plt.show()

def plot_spreads():
    rows = _read_csv("data/spreads.csv")
    t = [_parse_ts(r["ts"]) for r in rows]
    top = [float(r["top_bps"]) if r["top_bps"] else None for r in rows]
    size_cols = [c for c in rows[0].keys() if c.endswith("_bps") and c != "top_bps"]
    plt.figure()
    plt.plot(t, top, label="Top-of-book")
    for j in range(len(size_cols)):
        plt.plot(t, [float(rows[i][size_cols[j]]) if rows[i][size_cols[j]] else None for i in range(len(rows))],
                 label=size_cols[j].replace("_bps",""))
    plt.legend()
    plt.title("Spreads (bps)")
    plt.xlabel("Time"); plt.ylabel("bps")
    plt.tight_layout()
    plt.show()

def plot_inventory():
    rows = _read_csv("data/pnl.csv")
    t = [_parse_ts(r["ts"]) for r in rows]
    pos = [float(r["position"]) if r["position"] else 0.0 for r in rows]

    plt.figure()
    plt.plot(t, pos, label="Position (BTC)")
    plt.legend()
    plt.title("Inventory Over Time")
    plt.xlabel("Time"); plt.ylabel("BTC")
    plt.tight_layout()
    plt.show()
    
    

if __name__ == "__main__":
    plot_pnl()
    plot_spreads()
    plot_inventory()
    
