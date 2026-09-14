"""
Flask API that loads the model registered in this project (iris-classifier)
from the MLflow Model Registry and serves predictions.

Model is loaded from a stage alias such as "Production" or "Staging":
    models:/<REGISTERED_MODEL_NAME>/<MODEL_STAGE>

Endpoints:
    GET  /health   -> liveness/readiness probe, also reports loaded model version
    POST /predict   -> {"data": [[5.1, 3.5, 1.4, 0.2], ...]} -> {"predictions": [...]}
    POST /reload    -> forces a reload of the model from the registry (used by
                        the webhook flow / pod restart, but also callable directly
                        so a rolling restart isn't strictly required)

The model is (re)loaded:
  - once at process startup
  - whenever POST /reload is called
  - implicitly whenever the pod is restarted (since loading happens at startup),
    which is what the registry webhook triggers via `kubectl rollout restart`
"""
import os
import threading
import time

import mlflow
import mlflow.pyfunc
from flask import Flask, jsonify, request
from mlflow.tracking import MlflowClient

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
REGISTERED_MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-classifier")
MODEL_STAGE = os.getenv("MODEL_STAGE", "Production")

mlflow.set_tracking_uri(MLFLOW_URI)

app = Flask(__name__)

_model = None
_model_version = None
_model_lock = threading.Lock()


def load_model():
    """(Re)loads the latest model version for REGISTERED_MODEL_NAME/MODEL_STAGE."""
    global _model, _model_version

    client = MlflowClient()
    versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=[MODEL_STAGE])
    if not versions:
        raise RuntimeError(
            f"No model version found for '{REGISTERED_MODEL_NAME}' in stage "
            f"'{MODEL_STAGE}'. Promote a version first."
        )

    version_info = versions[0]
    model_uri = f"models:/{REGISTERED_MODEL_NAME}/{MODEL_STAGE}"
    print(f"[INFO] Loading model from {model_uri} (version={version_info.version})")

    new_model = mlflow.pyfunc.load_model(model_uri)

    with _model_lock:
        _model = new_model
        _model_version = version_info.version

    print(f"[INFO] Model loaded: version={_model_version}")


@app.route("/health", methods=["GET"])
def health():
    with _model_lock:
        loaded = _model is not None
        version = _model_version
    return jsonify(
        {
            "status": "ok" if loaded else "model_not_loaded",
            "registered_model_name": REGISTERED_MODEL_NAME,
            "stage": MODEL_STAGE,
            "model_version": version,
        }
    ), (200 if loaded else 503)


@app.route("/predict", methods=["POST"])
def predict():
    with _model_lock:
        model = _model
        version = _model_version

    if model is None:
        return jsonify({"error": "model not loaded yet"}), 503

    payload = request.get_json(silent=True)
    if not payload or "data" not in payload:
        return jsonify({"error": "expected JSON body: {'data': [[...], ...]}"}), 400

    try:
        predictions = model.predict(payload["data"])
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "predictions": predictions.tolist()
            if hasattr(predictions, "tolist")
            else list(predictions),
            "model_version": version,
        }
    )


@app.route("/reload", methods=["POST"])
def reload_model():
    """Manually trigger a model reload without restarting the pod.

    The registry webhook restarts the pod (simplest, most robust option since
    it also picks up new dependencies/artifacts), but this endpoint is handy
    for local testing or as an alternative lighter-weight reload path.
    """
    try:
        load_model()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    with _model_lock:
        version = _model_version
    return jsonify({"status": "reloaded", "model_version": version})


def _load_with_retry(retries=10, delay=5):
    for attempt in range(1, retries + 1):
        try:
            load_model()
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Model load attempt {attempt}/{retries} failed: {exc}")
            time.sleep(delay)
    print("[WARN] Starting without a loaded model; use POST /reload once a version exists.")


# Load the model as soon as the module is imported. This runs both when
# launched directly (`python serve.py`) and under a WSGI server such as
# gunicorn (`gunicorn serve:app`), which is what actually picks up a newly
# promoted model whenever the pod restarts.
_load_with_retry()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
