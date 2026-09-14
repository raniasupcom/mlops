"""
Webhook receiver for MLflow Model Registry stage-transition events.

Open-source MLflow does not fire webhooks natively (that's a Databricks-only
feature), so this service exposes an HTTP endpoint that *anything* promoting a
model can call: a CI job, `scripts/promote_model.py` in this repo, or a
Databricks-style registry webhook if you later migrate to managed MLflow.

Flow:
    1. Someone transitions a model version Staging -> Production in MLflow.
    2. They (or an automated job) POST the transition event to /webhook/mlflow.
    3. If the event is a transition into "Production", this service triggers
       `kubectl rollout restart deployment/<SERVE_DEPLOYMENT>` (via the
       Kubernetes API) in the target namespace.
    4. The pod restarts -> ml-app/serve.py runs its startup model load ->
       the new Production version is picked up.

Expected webhook payload (mirrors the shape of MLflow/Databricks registry
webhook events closely enough to be a drop-in target):
{
  "model_name": "iris-classifier",
  "version": "3",
  "from_stage": "Staging",
  "to_stage": "Production"
}
"""
import hashlib
import hmac
import os

from flask import Flask, jsonify, request
from kubernetes import client, config

MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-classifier")
TARGET_STAGE = os.getenv("TARGET_STAGE", "Production")
NAMESPACE = os.getenv("SERVE_NAMESPACE", "mlflow")
DEPLOYMENT_NAME = os.getenv("SERVE_DEPLOYMENT", "ml-app-serve")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # optional shared-secret verification

app = Flask(__name__)

try:
    # Running inside the cluster (normal case for this service)
    config.load_incluster_config()
except config.ConfigException:
    # Fallback for local testing against a kubeconfig
    config.load_kube_config()

apps_v1 = client.AppsV1Api()


def verify_signature(req) -> bool:
    if not WEBHOOK_SECRET:
        return True  # signature checking disabled
    signature = req.headers.get("X-Webhook-Signature", "")
    expected = hmac.new(WEBHOOK_SECRET.encode(), req.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def restart_deployment():
    """Equivalent of `kubectl rollout restart deployment/<name> -n <ns>`."""
    import datetime

    now = datetime.datetime.utcnow().isoformat() + "Z"
    body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {"kubectl.kubernetes.io/restartedAt": now}
                }
            }
        }
    }
    apps_v1.patch_namespaced_deployment(
        name=DEPLOYMENT_NAME, namespace=NAMESPACE, body=body
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook/mlflow", methods=["POST"])
def mlflow_webhook():
    if not verify_signature(request):
        return jsonify({"error": "invalid signature"}), 401

    event = request.get_json(silent=True) or {}
    model_name = event.get("model_name")
    to_stage = event.get("to_stage")
    version = event.get("version")

    if model_name != MODEL_NAME or to_stage != TARGET_STAGE:
        return jsonify(
            {
                "status": "ignored",
                "reason": f"event for model={model_name} stage={to_stage} "
                f"doesn't match watched model={MODEL_NAME} stage={TARGET_STAGE}",
            }
        ), 200

    try:
        restart_deployment()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"failed to restart deployment: {exc}"}), 500

    return jsonify(
        {
            "status": "restarted",
            "deployment": DEPLOYMENT_NAME,
            "namespace": NAMESPACE,
            "model_name": model_name,
            "version": version,
            "stage": to_stage,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
