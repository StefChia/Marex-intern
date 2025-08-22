# Marex-intern
Exercise for Marex crypto intern


RECALL:
On Coinbase’s match / last_match messages, the field side tells you the maker’s side:
So the side is not the aggressor; it’s the resting order that got hit/lifted.

STRATEGY:
If you want to upgrade later: make base_bps adaptive to short-term volatility (wider when vol spikes, tighter when calm), and make q_size smaller as your inventory grows.



FIFO IN SIMULATION