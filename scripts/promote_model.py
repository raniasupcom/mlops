"""
Promotes a model version to a new stage in the MLflow Model Registry, then
notifies the webhook-service so it can restart the serving pod.

Open-source MLflow's registry does not emit webhook events by itself, so this
script plays the role of "the thing that calls the webhook" right after doing
the stage transition. In CI this script is what you'd run as the deploy step.

Usage:
    python scripts/promote_model.py --version 3 --to-stage Production
    python scripts/promote_model.py --version 3 --to-stage Staging --archive-existing
"""
import argparse
import hashlib
import hmac
import os

import requests
from mlflow.tracking import MlflowClient

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://webhook-service.mlflow.svc.cluster.local:8001/webhook/mlflow")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-classifier")


def sign(payload_bytes: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Model version number to promote")
    parser.add_argument(
        "--from-stage", default="Staging", help="Expected current stage (for the webhook payload)"
    )
    parser.add_argument("--to-stage", default="Production", choices=["Staging", "Production", "Archived"])
    parser.add_argument(
        "--archive-existing",
        action="store_true",
        help="Archive any existing versions already in --to-stage",
    )
    args = parser.parse_args()

    client = MlflowClient(tracking_uri=MLFLOW_URI)

    print(f"[INFO] Transitioning {MODEL_NAME} v{args.version} -> {args.to_stage}")
    client.transition_model_version_stage(
        name=MODEL_NAME,
        version=args.version,
        stage=args.to_stage,
        archive_existing_versions=args.archive_existing,
    )
    print("[INFO] Stage transition complete.")

    payload = {
        "model_name": MODEL_NAME,
        "version": args.version,
        "from_stage": args.from_stage,
        "to_stage": args.to_stage,
    }

    import json

    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        headers["X-Webhook-Signature"] = sign(body)

    print(f"[INFO] Notifying webhook at {WEBHOOK_URL}")
    resp = requests.post(WEBHOOK_URL, data=body, headers=headers, timeout=10)
    print(f"[INFO] Webhook responded {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    main()
