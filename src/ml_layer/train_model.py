"""Trains the Random Forest deadlock-risk classifier."""
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score

FEATURES = ["locks_held_on_target", "wait_queue_length",
            "account_contention_count", "wait_time_ms", "priority"]

df = pd.read_csv("data/lock_logs.csv")
X, y = df[FEATURES], df["deadlock"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
model.fit(X_train, y_train)

preds = model.predict(X_test)
print(f"Accuracy:  {accuracy_score(y_test, preds):.3f}")
print(f"Precision: {precision_score(y_test, preds):.3f}")
print(f"Recall:    {recall_score(y_test, preds):.3f}")
for name, score in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
    print(f"  {name:28s} {score:.3f}")

joblib.dump(model, "model/deadlock_rf.joblib")
print("Model saved to model/deadlock_rf.joblib")
