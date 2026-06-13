#!/usr/bin/env python3
"""Опрос Modbus TCP (pymodbus) и публикация метрик в MQTT для Node-RED."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from paho.mqtt import client as mqtt
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = os.environ.get("MQTT_TOPIC_PREFIX", "lab/modbus").rstrip("/")
POLL_INTERVAL_SEC = float(os.environ.get("POLL_INTERVAL_SEC", "5"))
REGISTERS_CONFIG = Path(os.environ.get("REGISTERS_CONFIG", "registers.yaml"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("modbus-poller")

_running = True


@dataclass
class RegisterDef:
    name: str
    address: int
    count: int
    scale: float
    unit: str


@dataclass
class DeviceDef:
    id: str
    host: str
    port: int
    unit_id: int
    registers: list[RegisterDef]


def _load_config(path: Path) -> list[DeviceDef]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    devices: list[DeviceDef] = []
    for item in raw.get("devices", []):
        regs = [
            RegisterDef(
                name=r["name"],
                address=int(r["address"]),
                count=int(r.get("count", 1)),
                scale=float(r.get("scale", 1)),
                unit=str(r.get("unit", "")),
            )
            for r in item.get("registers", [])
        ]
        devices.append(
            DeviceDef(
                id=str(item["id"]),
                host=str(item["host"]),
                port=int(item.get("port", 502)),
                unit_id=int(item.get("unit_id", 1)),
                registers=regs,
            )
        )
    if not devices:
        raise ValueError(f"No devices in {path}")
    return devices


def _read_device(device: DeviceDef) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "device_id": device.id,
        "host": device.host,
        "ts": int(time.time()),
        "metrics": {},
        "ok": False,
    }

    client = ModbusTcpClient(host=device.host, port=device.port, timeout=3)
    if not client.connect():
        payload["error"] = "connect_failed"
        return payload

    try:
        for reg in device.registers:
            response = client.read_holding_registers(
                address=reg.address,
                count=reg.count,
                slave=device.unit_id,
            )
            if response.isError():
                raise ModbusException(str(response))

            raw = response.registers[0]
            value = round(raw * reg.scale, 4)
            payload["metrics"][reg.name] = {
                "value": value,
                "raw": raw,
                "unit": reg.unit,
                "address": reg.address,
            }

        payload["ok"] = True
        return payload
    except ModbusException as exc:
        payload["error"] = str(exc)
        return payload
    finally:
        client.close()


def _publish(client: mqtt.Client, topic: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False)
    info = client.publish(topic, body, qos=0, retain=False)
    info.wait_for_publish(timeout=5)
    log.info("MQTT %s ok=%s", topic, payload.get("ok"))


def _handle_stop(signum: int, _frame: Any) -> None:
    global _running
    log.info("Signal %s — stopping", signum)
    _running = False


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    devices = _load_config(REGISTERS_CONFIG)
    log.info("Loaded %s device(s) from %s", len(devices), REGISTERS_CONFIG)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="modbus-poller")
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    mqtt_client.loop_start()

    try:
        while _running:
            started = time.monotonic()
            for device in devices:
                result = _read_device(device)
                topic = f"{MQTT_TOPIC_PREFIX}/{device.id}"
                _publish(mqtt_client, topic, result)

            elapsed = time.monotonic() - started
            sleep_for = max(0.5, POLL_INTERVAL_SEC - elapsed)
            time.sleep(sleep_for)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
