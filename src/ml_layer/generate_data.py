"""Generates synthetic lock-contention data to train/test the model.
Replace with real rows from your LockTable/Transactions tables later."""
import numpy as np
import pandas as pd

np.random.seed(42)
N = 5000

df = pd.DataFrame({
    "locks_held_on_target": np.random.randint(0, 4, N),
    "wait_queue_length": np.random.randint(0, 10, N),
    "account_contention_count": np.random.poisson(1.5, N),
    "wait_time_ms": np.random.exponential(200, N),
    "priority": np.random.randint(1, 4, N),
})

risk = (
    0.35 * (df["locks_held_on_target"] >= 2)
    + 0.30 * (df["wait_queue_length"] >= 4)
    + 0.25 * (df["account_contention_count"] >= 3)
    + 0.10 * (df["wait_time_ms"] >= 400)
)
noise = np.random.normal(0, 0.12, N)
df["deadlock"] = ((risk + noise) > 0.5).astype(int)

df.to_csv("data/lock_logs.csv", index=False)
print(df["deadlock"].value_counts())
