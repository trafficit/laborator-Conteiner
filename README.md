# Laboratoria — Modbus + Node-RED (Docker)

IoT-лаборатория: **mock Modbus TCP** → **Python poller (pymodbus)** → **MQTT** → **Node-RED**.

Prod — это автономный стенд для отладки register-map до поля.

## Архитектура

```
mock-modbus:5020  ──TCP──►  modbus-poller (Python)  ──MQTT──►  Node-RED :1880
                                    │                              │
                              registers.yaml                  алерты, логика
                                    │
                              mosquitto:1883
```

## Быстрый старт

```bash
cd /home/wizard/Laborotoria
cp .env.example .env
docker compose up -d --build
docker compose logs -f modbus-poller
```

| Сервис | URL / порт |
|--------|------------|
| Node-RED | http://localhost:1880 |
| MQTT | localhost:1883 |
| Mock Modbus TCP | localhost:5020 (unit_id=1) |

В Node-RED открой вкладку **Modbus Lab** → Debug sidebar — каждые ~5 с приходят метрики. При `fuel < 20%` срабатывает ветка **alerts**.

## Конфигурация опроса

Файл `modbus-poller/registers.yaml` — карта регистров (как на ComAp/ПЛК):

```yaml
devices:
  - id: dg-demo
    host: mock-modbus   # или IP Teltonika / RS485-gateway
    port: 5020
    unit_id: 1
    registers:
      - name: fuel_percent
        address: 3
        scale: 1
        unit: "%"
```

После правок:

```bash
docker compose restart modbus-poller
```

## Подключение реального устройства

1. Подключение Edge (Teltonika / USB-RS485 + Modbus TCP gateway) в ту же L2, что ноут.
2. В `registers.yaml` укажи `host` / `port` / `unit_id` и адреса из vendor register map.
3. p.s. Останови mock, если не нужен: `docker compose stop mock-modbus`.
4. Poller и Node-RED менять не трогать — меняем только YAML.

## Полезные команды

```bash
# MQTT с хоста (проверка без Node-RED)
docker run --rm -it --network laborotoria_default eclipse-mosquitto:2 \
  mosquitto_sub -h mosquitto -t 'lab/modbus/#' -v

# Логи
docker compose logs -f mock-modbus modbus-poller node-red

# Остановка
docker compose down
```

## Расширение в Node-RED

- **Dashboard 2.0** (`node-red-dashboard`) — gauges для fuel/rpm.
- **HTTP Request** → будущий GES API / Postgres.
- **Telegram / email** на выходе узла `Low fuel event`.
- а) **Modbus Read** (node-red-contrib-modbus) — только если нужен опрос прямо из NR;
- б) рекомендуемый путь: **Python poller + MQTT** (стабильнее для production-like стенда).

## Файлы

```
docker-compose.yml
mock-modbus/          # pymodbus TCP slave (demo)
modbus-poller/        # pymodbus client + MQTT publish
  registers.yaml
mosquitto/
node-red/data/flows.json
```
