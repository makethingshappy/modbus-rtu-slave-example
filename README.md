# Modbus RTU Slave for MicroPython — IoTsmart + IoTextra

A small, dependency-free **Modbus RTU slave** engine for MicroPython (MIT), with a working example on the **IoTextra Octal2** digital I/O module. Your board answers a PLC, SCADA, Node-RED or any Modbus master over RS485.

This is an open example, not a finished product: the register map is written by hand in the example script.

## What's here

| Path | What it is |
| --- | --- |
| [`modbus_slave.py`](modbus_slave.py) | The engine: PDU + CRC + UART framing. Function codes 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x0F, 0x10; broadcast (address 0) applies the write without a reply. |
| [`examples/octal2/`](examples/octal2) | **IoTextra Octal2** as a Modbus slave: 4 digital inputs → discrete inputs 0–3, 4 outputs → coils 0–3. Includes a PC master script that blinks the outputs and watches the inputs. |
| [`examples/bringup/`](examples/bringup) | Minimal slave with a stand-in register map, used for bring-up and the test suite. |
| [`tests/`](tests) | PC-side master tests (pymodbus, minimalmodbus, raw serial): function-code checklist, 500-read reliability run, bad CRC, truncated and back-to-back frames, inter-byte gaps. |
| [`docs/BRINGUP_REPORT.md`](docs/BRINGUP_REPORT.md) | Full test results and wiring. |

## Tested

External isolated **Waveshare UART-RS485** (automatic direction, no DE/RE pin), single node, slave address 1, 8N1.

| Board | UART | TX / RX | 9600 | 115200 |
| --- | --- | --- | --- | --- |
| IoTsmart RP2040 | UART0 | GPIO0 / GPIO1 | pass | pass |
| IoTbase Pico 2W (RP2350) | UART0 | GPIO0 / GPIO1 | pass | pass |
| IoTsmart ESP32-S3 | UART1 | GPIO43 / GPIO44 | pass | pass* |

\* On ESP32-S3 at 115200, detach the MicroPython REPL from the Modbus UART first:

```python
import os
os.dupterm(None)
```

Each board: 500 of 500 consecutive reads at both baud rates, 0 % errors. Masters used: pymodbus, QModMaster, minimalmodbus. `byte_timeout_ms=10` works at both baud rates. Multi-drop (several slaves on one bus) has not been tested. IoTsmart RP2350A has not been tested yet.

## Quick start

1. Flash MicroPython on the board.
2. Copy `modbus_slave.py` to the board (e.g. `lib/`).
3. For the Octal2 example, also copy everything from `examples/octal2/` except `octal2_master.py`; run `main_octal2.py` (or save it as `main.py`).
4. Wire the board to the RS485 adapter (3V3, GND, TX↔RX crossed) and connect the adapter to your master.
5. On the PC: `pip install -r requirements.txt`, then `python examples/octal2/octal2_master.py --port <your port> --baud 115200`.

Set `UART_ID`, `TX_PIN`, `RX_PIN` and `BAUDRATE` at the top of the script to match your carrier.

## Octal2 register map

| Modbus | Address | Octal2 |
| --- | --- | --- |
| Discrete inputs (FC02) | 0–3 | DI channels 0–3 |
| Coils (FC01/05/0F) | 0–3 | DO channels 4–7 (LED 1–4) |

Analog modules are not covered.

## Hardware

- [IoTsmart](https://github.com/makethingshappy/IoTsmart) — host boards (RP2040, RP2350, ESP32-S3)
- [IoTextra Digital](https://github.com/makethingshappy/IoTextra-Digital) — I/O modules including Octal2

## License

MIT. Copyright (c) 2026 makethingshappy (MTH LLC) and Arshia Keshvari. Bring-up and the Octal2 example by Arshia Keshvari for MTH LLC.
