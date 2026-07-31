"""HTTP request initiator for the emqx_sync_request beginner demo."""

import argparse
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

REQUEST_TIMEOUT_MIN = float(os.getenv("REQUEST_TIMEOUT_MIN", "1"))
REQUEST_TIMEOUT_MAX = float(os.getenv("REQUEST_TIMEOUT_MAX", "5"))
REQUEST_INTERVAL = 1


def parse_args():
    parser = argparse.ArgumentParser(description="emqx_sync_request HTTP 请求发起端")
    parser.add_argument(
        "--vin_list",
        default="vin01,vin02,vin03",
        help="VIN 列表，使用逗号分隔，默认：vin01,vin02,vin03",
    )
    parser.add_argument("--count", type=int, default=10, help="请求次数，默认：10")
    args = parser.parse_args()
    args.vin_list = [vin.strip() for vin in args.vin_list.split(",") if vin.strip()]
    if not args.vin_list:
        parser.error("--vin_list 不能为空")
    if args.count < 1:
        parser.error("--count 必须大于 0")
    return args


def send_request(http: requests.Session, vin: str, timeout_seconds: float):
    request_id = uuid.uuid4().hex
    request_topic = f"/rpc/{vin}/sync_request"
    response_topic = f"/rpc/{vin}/sync_response"
    body = {
        "timeout": f"{timeout_seconds:.1f}s",
        "request": {
            "topic": request_topic,
            "response_topic": response_topic,
            "request_id": request_id,
            "qos": 1,
            "payload_encoding": "plain",
            "payload": json.dumps(
                {"command": "read-temperature", "vin": vin, "request_id": request_id},
                ensure_ascii=False,
            ),
            "content_type": "application/json",
        },
    }
    logging.info(
        "request vin=%s topic=%s id=%s timeout=%ss",
        vin,
        request_topic,
        request_id,
        timeout_seconds,
    )
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
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if API_KEY.startswith("replace-") or SECRET_KEY.startswith("replace-"):
        raise SystemExit("请先设置 EMQX_API_KEY 和 EMQX_SECRET_KEY")

    with requests.Session() as http:
        http.auth = (API_KEY, SECRET_KEY)
        for index in range(args.count):
            vin = random.choice(args.vin_list)
            timeout_seconds = random.uniform(REQUEST_TIMEOUT_MIN, REQUEST_TIMEOUT_MAX)
            # send_request blocks until HTTP returns; only then choose the next VIN.
            send_request(http, vin, round(timeout_seconds, 1))
            if index + 1 < args.count:
                time.sleep(REQUEST_INTERVAL)


if __name__ == "__main__":
    main()
