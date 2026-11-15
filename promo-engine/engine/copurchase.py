from collections import Counter
from itertools import combinations

import pandas as pd

from .config import data_dir

LIFT_CAP = 5.0
MIN_PAIR_ORDERS = 3


class CoPurchase:
    def __init__(self, orders: pd.DataFrame):
        baskets = orders.groupby("order_id")["sku"].apply(set)
        self.n_orders = len(baskets)
        self.sku_count: Counter = Counter()
        self.pair_count: Counter = Counter()
        for basket in baskets:
            self.sku_count.update(basket)
            self.pair_count.update(frozenset(p) for p in combinations(sorted(basket), 2))

    def lift(self, a: str, b: str) -> float:
        together = self.pair_count[frozenset((a, b))]
        if together < MIN_PAIR_ORDERS:
            return 0.0
        return together * self.n_orders / (self.sku_count[a] * self.sku_count[b])

    def copurchase_score(self, a: str, b: str) -> float:
        """0-1: lift of 1 (bought together by chance) maps to 0, lift >= LIFT_CAP maps to 1."""
        return max(0.0, min((self.lift(a, b) - 1) / (LIFT_CAP - 1), 1.0))

    def partners(self, sku: str, k: int = 5) -> list[str]:
        scored = [(self.copurchase_score(sku, other), other) for other in self.sku_count if other != sku]
        return [other for score, other in sorted(scored, reverse=True)[:k] if score > 0]


def load_copurchase() -> CoPurchase:
    return CoPurchase(pd.read_csv(data_dir() / "orders.csv", dtype={"sku": str}))
