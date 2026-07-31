"""HTTP request initiator for the emqx_sync_request beginner demo."""

import base64
import json
import logging
import os
import random
import time
import uuid

import requests


EMQX_HTTP_URL = os.getenv("EMQX_HTTP_URL", "http://127.0.0.1:18083")
REQUEST_API = f"{EMQX_HTTP_URL.rstrip('/')}/api/v5/plugin_api/emqx_sync_request/request"

# Keep these as obvious variables for beginners. Prefer environment variables
# so that API credentials do not need to be committed to source control.
API_KEY = os.getenv("EMQX_API_KEY", "replace-with-api-key")
SECRET_KEY = os.getenv("EMQX_SECRET_KEY", "replace-with-secret-key")

REQUEST_TOPIC = os.getenv("REQUEST_TOPIC", "demo/sync-request/request")
RESPONSE_TOPIC_PREFIX = os.getenv("RESPONSE_TOPIC_PREFIX", "demo/sync-request/response")
REQUEST_TIMEOUT_MIN = float(os.getenv("REQUEST_TIMEOUT_MIN", "1"))
REQUEST_TIMEOUT_MAX = float(os.getenv("REQUEST_TIMEOUT_MAX", "5"))
REQUEST_INTERVAL = float(os.getenv("REQUEST_INTERVAL", "2"))


def send_request(http: requests.Session, timeout_seconds: float):
    request_id = uuid.uuid4().hex
    response_topic = f"{RESPONSE_TOPIC_PREFIX}/{request_id}"
    body = {
        "timeout": f"{timeout_seconds:.1f}s",
        "request": {
            "topic": REQUEST_TOPIC,
            "response_topic": response_topic,
            "request_id": request_id,
            "qos": 1,
            "payload_encoding": "plain",
            "payload": json.dumps(
                {"command": "read-temperature", "request_id": request_id},
                ensure_ascii=False,
            ),
            "content_type": "application/json",
        },
    }
    logging.info("request id=%s timeout=%ss", request_id, timeout_seconds)
    try:
        # Add a small margin so the HTTP client can receive the plugin's 504.
        result = http.post(
            REQUEST_API,
            json=body,
            timeout=timeout_seconds + 2,
        )
    except requests.RequestException as error:
        logging.error("HTTP request failed: %s", error)
        return

    try:
        result_body = result.json()
    except ValueError:
        result_body = {"raw": result.text}

    if result.ok:
        response = result_body["response"]
        payload = base64.b64decode(response["payload"]).decode("utf-8", errors="replace")
        logging.info("success status=%s response=%s", result.status_code, payload)
    else:
        logging.warning(
            "failed status=%s code=%s message=%s",
            result.status_code,
            result_body.get("code"),
            result_body.get("message"),
        )


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if API_KEY.startswith("replace-") or SECRET_KEY.startswith("replace-"):
        raise SystemExit("请先设置 EMQX_API_KEY 和 EMQX_SECRET_KEY")

    with requests.Session() as http:
        http.auth = (API_KEY, SECRET_KEY)
        while True:
            timeout_seconds = random.uniform(REQUEST_TIMEOUT_MIN, REQUEST_TIMEOUT_MAX)
            send_request(http, round(timeout_seconds, 1))
            time.sleep(REQUEST_INTERVAL)


if __name__ == "__main__":
    main()
