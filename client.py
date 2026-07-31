"""MQTT 5 request client for the emqx_sync_request beginner demo."""

import argparse
import json
import logging
import os
import random
import signal
import time

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties


MQTT_HOST = os.getenv("EMQX_MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("EMQX_MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("EMQX_MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("EMQX_MQTT_PASSWORD")
RESPONSE_DELAY_MIN = float(os.getenv("RESPONSE_DELAY_MIN", "0.5"))
RESPONSE_DELAY_MAX = float(os.getenv("RESPONSE_DELAY_MAX", "4.0"))


def parse_args():
    parser = argparse.ArgumentParser(description="emqx_sync_request MQTT 5 请求接收客户端")
    parser.add_argument("--vin", required=True, help="设备 VIN，同时作为 MQTT Client ID")
    return parser.parse_args()


def on_connect(client: mqtt.Client, userdata, _flags, reason_code, _properties=None):
    if reason_code != 0:
        logging.error("MQTT connect failed: %s", reason_code)
        return
    request_topic = userdata["request_topic"]
    result, _ = client.subscribe(request_topic, qos=1)
    if result != mqtt.MQTT_ERR_SUCCESS:
        logging.error("subscribe failed: %s", mqtt.error_string(result))
        return
    logging.info("connected; subscribed to %s", request_topic)


def on_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    properties = message.properties
    response_topic = getattr(properties, "ResponseTopic", None)
    correlation_data = getattr(properties, "CorrelationData", None)

    if not response_topic or correlation_data is None:
        logging.warning("request has no MQTT 5 Response Topic or Correlation Data")
        return

    try:
        request = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        request = {"raw_payload": message.payload.decode("utf-8", errors="replace")}

    delay = random.uniform(RESPONSE_DELAY_MIN, RESPONSE_DELAY_MAX)
    logging.info(
        "received topic=%s correlation_data=%r payload=%s; processing %.2fs",
        message.topic,
        correlation_data.decode("utf-8", errors="replace"),
        request,
        delay,
    )
    time.sleep(delay)

    result = {
        "ok": True,
        "message": "response from Python MQTT 5 client",
        "vin": userdata["vin"],
        "request": request,
        "processing_seconds": round(delay, 3),
    }
    response_properties = Properties(PacketTypes.PUBLISH)
    response_properties.CorrelationData = correlation_data
    response_properties.ContentType = "application/json"
    info = client.publish(
        response_topic,
        json.dumps(result, ensure_ascii=False).encode("utf-8"),
        qos=message.qos,
        properties=response_properties,
    )
    info.wait_for_publish()
    logging.info("published response topic=%s mid=%s", response_topic, info.mid)


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    request_topic = f"/rpc/{args.vin}/sync_request"
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=args.vin,
        protocol=mqtt.MQTTv5,
        userdata={"vin": args.vin, "request_topic": request_topic},
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD or "")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    def stop(_signum, _frame):
        logging.info("stopping")
        client.disconnect()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    logging.info(
        "starting client_id=%s request_topic=%s response_topic=/rpc/%s/sync_response",
        args.vin,
        request_topic,
        args.vin,
    )
    client.loop_forever()


if __name__ == "__main__":
    main()
