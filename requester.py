"""通过 HTTP API 持续发起 emqx_sync_request 请求。"""

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

# 推荐使用环境变量，避免把真实 API 凭据提交到代码仓库。
API_KEY = os.getenv("EMQX_API_KEY", "replace-with-api-key")
SECRET_KEY = os.getenv("EMQX_SECRET_KEY", "replace-with-secret-key")

# 这些是演示行为，不作为命令行参数暴露给初学者。
REQUEST_TIMEOUT_MIN = 1.0
REQUEST_TIMEOUT_MAX = 5.0
REQUEST_INTERVAL = 1
REQUEST_COUNT = 10


def validate_vin(vin: str) -> str:
    """校验 VIN，避免生成无效或非预期的 MQTT 主题。"""
    vin = vin.strip()
    if (
        not vin
        or any(char in vin for char in "/+#")
        or any(char.isspace() for char in vin)
    ):
        raise argparse.ArgumentTypeError(
            f"无效 VIN {vin!r}：不能包含空白字符、/、+ 或 #"
        )
    return vin


def parse_vin_list(value: str) -> list[str]:
    vins = [validate_vin(vin) for vin in value.split(",") if vin.strip()]
    if not vins:
        raise argparse.ArgumentTypeError("VIN 列表不能为空")
    return vins


def parse_args():
    parser = argparse.ArgumentParser(description="emqx_sync_request HTTP 请求发起端")
    parser.add_argument(
        "--vin_list",
        type=parse_vin_list,
        default=["vin01"],
        help="逗号分隔的 VIN 列表，默认：vin01",
    )
    return parser.parse_args()


def send_request(http: requests.Session, vin: str, timeout_seconds: float):
    request_id = uuid.uuid4().hex
    request_topic = f"/rpc/{vin}/sync_request"
    response_topic = f"/rpc/{vin}/sync_response"
    # request_id 会被插件转换为 MQTT 5 Correlation Data。
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
        # HTTP 客户端多等待 2 秒，确保能收到插件返回的 504 TIMEOUT。
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
        try:
            response = result_body["response"]
            payload = base64.b64decode(response["payload"]).decode(
                "utf-8", errors="replace"
            )
        except (KeyError, TypeError, ValueError) as error:
            logging.error("unexpected success response: %s (%s)", result_body, error)
            return
        logging.info("success status=%s response=%s", result.status_code, payload)
    else:
        # 不同插件版本使用 code/message 或 status/reason 表示错误。
        error_code = result_body.get("code", result_body.get("status"))
        error_message = result_body.get("message", result_body.get("reason"))
        logging.warning(
            "failed status=%s code=%s message=%s",
            result.status_code,
            error_code,
            error_message,
        )


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if API_KEY.startswith("replace-") or SECRET_KEY.startswith("replace-"):
        raise SystemExit("请先设置 EMQX_API_KEY 和 EMQX_SECRET_KEY")

    with requests.Session() as http:
        http.auth = (API_KEY, SECRET_KEY)
        for index in range(REQUEST_COUNT):
            vin = random.choice(args.vin_list)
            timeout_seconds = random.uniform(REQUEST_TIMEOUT_MIN, REQUEST_TIMEOUT_MAX)
            # send_request 会阻塞到 HTTP 返回，之后才会选择下一个 VIN。
            send_request(http, vin, round(timeout_seconds, 1))
            if index + 1 < REQUEST_COUNT:
                time.sleep(REQUEST_INTERVAL)


if __name__ == "__main__":
    main()
