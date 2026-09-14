import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
import os

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment("iris-classification")

print(f"[INFO] Connecting to MLflow at: {MLFLOW_URI}")

with mlflow.start_run():
    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=42)

    n_estimators = int(os.getenv("N_ESTIMATORS", "100"))
    max_depth = int(os.getenv("MAX_DEPTH", "5"))

    model = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, random_state=42)
    model.fit(X_train, y_train)

    acc = model.score(X_test, y_test)

    mlflow.log_param("n_estimators", n_estimators)
    mlflow.log_param("max_depth", max_depth)
    mlflow.log_metric("accuracy", acc)

    # Register the model in the MLflow Model Registry so it can be promoted
    # through stages (None -> Staging -> Production) and served by serve.py
    REGISTERED_MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-classifier")
    mlflow.sklearn.log_model(
        model,
        "model",
        registered_model_name=REGISTERED_MODEL_NAME,
    )

    print(f"[DONE] accuracy={acc:.4f} | n_estimators={n_estimators} | max_depth={max_depth}")
