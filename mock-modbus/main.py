#!/usr/bin/env python3
"""Mock Modbus TCP slave для IoT-лаборатории (ComAp-like holding registers)."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import time

from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server import StartAsyncTcpServer

REG_VOLTAGE = 0
REG_FREQUENCY = 1
REG_COOLANT_TEMP = 2
REG_FUEL_LEVEL = 3
REG_ENGINE_STATE = 4
REG_ENGINE_RPM = 5
REG_OIL_PRESSURE = 6

MODBUS_UNIT_ID = int(os.environ.get("MODBUS_UNIT_ID", "1"))
LISTEN_PORT = int(os.environ.get("MOCK_MODBUS_PORT", "5020"))
UPDATE_INTERVAL_SEC = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mock-modbus")

_t0 = time.monotonic()


def _simulated_values(elapsed: float) -> list[int]:
    """Плавные синусоиды + шум — как живой ДГ на стенде."""
    base_rpm = 1500 if math.sin(elapsed / 30) > -0.2 else 0
    running = base_rpm > 0
    noise = random.uniform(-0.5, 0.5)

    voltage = 230 + (15 * math.sin(elapsed / 17)) + noise if running else 0
    frequency = 50 + (0.2 * math.sin(elapsed / 11)) if running else 0
    coolant = 78 + (8 * math.sin(elapsed / 23)) if running else 25
    fuel = max(0, min(100, 85 - elapsed / 120 + noise))
    engine_state = 1 if running else 0
    rpm = base_rpm + random.randint(-20, 20) if running else 0
    oil = 45 + (5 * math.sin(elapsed / 19)) if running else 0

    return [
        int(round(voltage * 10)),       # 0.1 V
        int(round(frequency * 100)),    # 0.01 Hz
        int(round(coolant * 10)),       # 0.1 °C
        int(round(fuel)),               # %
        engine_state,
        rpm,
        int(round(oil * 10)),           # 0.1 bar
    ]


async def _update_loop(context: ModbusServerContext) -> None:
    store = context[MODBUS_UNIT_ID]
    while True:
        elapsed = time.monotonic() - _t0
        values = _simulated_values(elapsed)
        store.setValues(3, 0, values)  # 3 = holding registers
        await asyncio.sleep(UPDATE_INTERVAL_SEC)


async def _run_server() -> None:
    block = ModbusSequentialDataBlock(0, [0] * 16)
    store = ModbusSlaveContext(hr=block)
    context = ModbusServerContext(slaves={MODBUS_UNIT_ID: store}, single=False)

    log.info(
        "Mock Modbus TCP 0.0.0.0:%s unit_id=%s (holding 0..6)",
        LISTEN_PORT,
        MODBUS_UNIT_ID,
    )

    asyncio.create_task(_update_loop(context))
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", LISTEN_PORT))


if __name__ == "__main__":
    asyncio.run(_run_server())
