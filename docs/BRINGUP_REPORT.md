# Bring-up report — Modbus RTU Slave

**Bring-up testing:** Arshia Keshvari, for MTH LLC
**Last Updated:** 2026-11-01

Results of the hardware bring-up of `modbus_slave.py` on three carriers with an external isolated Waveshare UART-RS485. Single-node bench (multi-drop was not tested). Register map used here is a stand-in map (see below), not an IoTextra-derived one. Scripts referenced below live in [`tests/`](../tests) and [`examples/bringup/`](../examples/bringup).

---

## Executive summary

The Modbus RTU slave engine (`modbus_slave.py`) answers an external Modbus master over RS485 with **hardware direction auto-sensing** (no DE/RE GPIO). Bring-up used a stand-in register map.

| Item | Result |
| --- | --- |
| Baud rates | **9600** and **115200** — both PASS |
| CRC / I/O error rate | **0%** (500 consecutive FC03 reads per baud) |
| Frame timeout | `byte_timeout_ms = **10**` confirmed; same value both bauds |
| Masters | **pymodbus**, **QModMaster**, and **minimalmodbus** — all PASS |
| Carriers | **IoTsmart RP2040** (original bench), **IoTbase Pico 2W (RP2350)**, **IoTsmart ESP32-S3** — all PASS |
| Broadcast (address 0) | Write applied, no response — PASS |
| Multi-drop | Out of scope for this bench (single board) |

**Verdict:** RTU bring-up is successful on this single-node Waveshare path (pymodbus + QModMaster). The original bench was **IoTsmart RP2040**. The same bring-up then passed on **IoTbase Pico 2W (RP2350)** and **IoTsmart ESP32-S3**. On the ESP32-S3, 115200 needs the MicroPython REPL kept off the Modbus UART (`os.dupterm(None)`); with that applied, both baud rates passed.

---

## Hardware

Three carriers were tested on the same external isolated **Waveshare UART-RS485** (auto direction, no DE/RE). The original bench was an **IoTsmart RP2040**. **IoTbase Pico 2W (RP2350)** and **IoTsmart ESP32-S3** were tested afterwards as additions to that bench; both passed at **9600** and **115200**.

| Board | UART | TX | RX | Result |
| --- | --- | --- | --- | --- |
| **IoTsmart RP2040** | UART0 | GPIO0 | GPIO1 | PASS — original bench (RP2040 and RP2350 share the same Waveshare Tiny pinout) |
| **IoTbase Pico 2W (RP2350)** | UART0 | GPIO0 | GPIO1 | PASS — same UART and pins as the RP2040 bench |
| **IoTsmart ESP32-S3** | UART1 | GPIO43 | GPIO44 | PASS — UART1. 115200 baud rate needs the REPL detached from the UART (see below) |

| Item | Value |
| --- | --- |
| RS485 | External isolated **Waveshare UART-RS485** (auto direction, no DE/RE) |
| Master adapter | USB-RS485 dongle `FT232R` → `/dev/cu.usbserial-BH00LLRL` |
| Board USB REPL | `/dev/cu.usbmodem2101` (MicroPython / mpremote / Thonny) |
| Slave address | `1` |
| Framing | 8N1 |
| `byte_timeout_ms` | **10** (kept; confirmed below) |

Board firmware files used: `lib/modbus_slave.py`, `main.py` / `examples/bringup/test_rtu_main.py` (stand-in register map).

### ESP32-S3 at 115200

On the **IoTsmart ESP32-S3**, bring-up used **UART1** with **TX GPIO43** and **RX GPIO44**. **9600** worked on that wiring. **115200** passed only after an extra UART configuration so Modbus bytes were not mixed with other serial traffic. `byte_timeout_ms` stayed **10**. With that configuration applied, both baud rates passed the same bring-up as the RP2040.

The extra step is about the MicroPython REPL, and it may involve solutions like `os.dupterm(None)`. Normally MicroPython can send REPL input and output to a terminal connected through **USB CDC** or a **UART**. Prompts, tracebacks, and anything typed at that terminal are ordinary bytes on whichever stream is attached. If that stream is the UART carrying Modbus, those bytes interrupt the RTU frames. The point of the configuration is to let **115200** communication run without being interrupted by that other traffic. Whether it is required depends on how MicroPython was configured and which interface it uses for the REPL.

Disconnect the REPL from the default dupterm slot before using the UART for Modbus:

```python
import os
os.dupterm(None)
```

`os.dupterm(None)` clears dupterm slot 0, the usual REPL slot, so REPL traffic is no longer copied onto that stream. `test_rtu_main.py` for example calls this at startup. USB CDC can still be the console when the firmware left that path attached on its own; the RS485 UART is then only Modbus.

A UART stream can be connected again as the REPL:

```python
import os
import machine

uart = machine.UART(0, 115200)
os.dupterm(uart, 0)
```

`os.dupterm(uart, 0)` attaches that UART as dupterm slot 0 at 115200. Use it when a terminal on a UART is wanted again. Leave the Modbus UART (UART1 on this board) off the REPL so the bus stays clear of prompts and keystrokes.

### Wiring (single node)

**MCU ↔ Waveshare UART-RS485**

| Signal | Waveshare | RP2040 and Pico 2W | ESP32-S3 |
| --- | --- | --- | --- |
| 3V3 | 3V3 | 3V3 | 3V3 |
| GND | GND | GND | GND |
| TX | RX | GPIO0 (UART0) | GPIO43 (UART1) |
| RX | TX | GPIO1 (UART0) | GPIO44 (UART1) |

**RS485 bus:** USB-RS485 dongle **A/B/GND** ↔ Waveshare **A/B/GND**. Use 120 Ω termination at the bus ends when appropriate.

---

## Scripts used

| Script | Role |
| --- | --- |
| `test_rtu_main.py` / board `main.py` | Slave bring-up firmware (RP2040, Pico 2W, ESP32-S3) |
| `full_modbus_test.py` | Primary pymodbus checklist (user-confirmed PASS) |
| QModMaster (GUI) | Second master (GUI) (user-confirmed PASS) |
| `rtu_reliability_test.py` | 500-read CRC / stability |
| `invalid_crc_test.py` | Bad CRC silence + recovery |
| `test_incomplete_frame.py` | Truncated frame + recovery |
| `test_back_to_back.py` | Rapid valid frames |
| `test_interbyte_timing.py` | Inter-byte gap smoke |
| `second_master_minimalmodbus.py` | Extra second-library checklist both bauds |
| `basic_modbus_test.py` | Quick FC03 smoke before the full suite |

---

## How to reproduce

### 1. Board (MicroPython)

1. Flash MicroPython on the carrier under test: **IoTsmart RP2040**, **IoTbase Pico 2W (RP2350)**, or **IoTsmart ESP32-S3**.
2. Copy `modbus_slave.py` to the board (e.g. `lib/modbus_slave.py`).
3. Copy `test_rtu_main.py` as `main.py` (or run it from Thonny).
4. Set `UART_ID` / `TX_PIN` / `RX_PIN` / `BAUDRATE` for that board:
   - **RP2040** and **Pico 2W:** `UART_ID = 0`, `TX_PIN = 0`, `RX_PIN = 1`
   - **ESP32-S3:** `UART_ID = 1`, `TX_PIN = 43`, `RX_PIN = 44`. For **115200**, disconnect REPL I/O from the UART with `os.dupterm(None)` when MicroPython still has the REPL on USB CDC or a UART (see [ESP32-S3 at 115200](#esp32-s3-at-115200)).
5. Soft-reset; wait until the serial console prints **Ready**.

### 2. PC environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set `PORT` in the PC scripts to your USB-RS485 device if it differs from `/dev/cu.usbserial-BH00LLRL`.

### 3. Suggested test order

| Order | Script / tool | Baud | Purpose |
| --- | --- | --- | --- |
| 1 | `basic_modbus_test.py` | match board | Smoke link |
| 2 | `full_modbus_test.py` | 9600 then 115200 | Full FC checklist + broadcast |
| 3 | `rtu_reliability_test.py` | each baud | 500-read CRC / latency |
| 4 | Edge scripts | each baud | CRC / incomplete / back-to-back / inter-byte |
| 5 | **QModMaster** | each baud | Second master (GUI) — same checklist |

Match PC baud to the board’s `BAUDRATE` before each run. Close other apps that hold the USB-RS485 port.

---

## Stand-in register map

Used only for bring-up :

| Block | Values |
| --- | --- |
| Holding registers (FC03/06/16) | `[10, 20, 30, 40]` |
| Input registers (FC04) | `[1234, 5678, 100, 65535]` |
| Coils (FC01/05/15) | `[0, 1, 0, 1, 1, 0, 1, 0]` |
| Discrete inputs (FC02) | `[0, 1, 1, 0, 1, 0, 0, 1]` |

---

## Test results

The functional checklist and `byte_timeout_ms` tables below are from the original **IoTsmart RP2040** bench. **IoTbase Pico 2W (RP2350)** and **IoTsmart ESP32-S3** were tested later as additions to that bench and passed the same bring-up at both baud rates. CRC / link reliability (500 FC03 reads per baud) is recorded separately for each board.

| Board | UART / pins | 9600 | 115200 |
| --- | --- | --- | --- |
| IoTsmart RP2040 | UART0, GPIO0 TX / GPIO1 RX | PASS | PASS |
| IoTbase Pico 2W (RP2350) | UART0, GPIO0 TX / GPIO1 RX | PASS | PASS |
| IoTsmart ESP32-S3 | UART1, GPIO43 TX / GPIO44 RX | PASS | PASS, after detaching the REPL (`os.dupterm(None)`) |

### Masters used

1. **pymodbus** — primary checklist (`full_modbus_test.py`, reliability, edge scripts); user-confirmed PASS
2. **QModMaster** — same functional checklist; **user-confirmed PASS** (2026-10-11)
3. **minimalmodbus** — extra second-library checklist (`second_master_minimalmodbus.py`); **24/24 PASS**

**Master latency note:** QModMaster felt slower (longer timeouts / poll delays / UI latency) than pymodbus. That is expected master-side / GUI pacing, not a slave CRC or framing problem. pymodbus reliability stayed about 20 ms average at 115200 and about 52 ms at 9600 with 0% errors on each carrier (see the per-board tables below).

### Functional checklist (both bauds)

Covered by user-confirmed `full_modbus_test.py` (pymodbus), user-confirmed **QModMaster**, and `second_master_minimalmodbus.py` (24/24 PASS).

| Check | 9600 | 115200 |
| --- | --- | --- |
| FC03 read holding | PASS | PASS |
| FC04 read input | PASS | PASS |
| FC01 read coils | PASS | PASS |
| FC02 read discrete | PASS | PASS |
| FC06 write single register | PASS | PASS |
| FC10 write multiple registers | PASS | PASS |
| FC05 write single coil | PASS | PASS |
| FC0F write multiple coils | PASS | PASS |
| Illegal address → exception 0x02 | PASS | PASS |
| Broadcast addr 0 write applied, no reply required | PASS | PASS |
| 25 consecutive holding reads | PASS | PASS |

Stand-in map values: holding `[10,20,30,40]`, input `[1234,5678,100,65535]`, coils `[0,1,0,1,1,0,1,0]`, discrete `[0,1,1,0,1,0,0,1]`.

### CRC / link reliability (500 FC03 reads)

Proxy for CRC error rate + direction auto-sense (no scope available; judged by link stability). Script: `rtu_reliability_test.py`. Each run is 500 consecutive FC03 reads, expected holding registers `[10, 20, 30, 40]`.

**IoTsmart RP2040** (original bench, UART0, GPIO0 TX / GPIO1 RX)

| Baud | Success | Failures | CRC / I/O error rate | Fastest | Avg | Median | p95 | Slowest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9600 | **500/500** | 0 | **0%** | 41.60 ms | 51.58 ms | 52.13 ms | 53.08 ms | 58.21 ms |
| 115200 | **500/500** | 0 | **0%** | 17.91 ms | 19.72 ms | 19.52 ms | 21.87 ms | 34.92 ms |

**IoTsmart ESP32-S3** (UART1, GPIO43 TX / GPIO44 RX; REPL detached with `os.dupterm(None)`)

| Baud | Success | Failures | CRC / I/O error rate | Fastest | Avg | Median | p95 | Slowest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9600 | **500/500** | 0 | **0%** | 46.23 ms | 51.57 ms | 52.12 ms | 54.79 ms | 58.18 ms |
| 115200 | **500/500** | 0 | **0%** | 18.00 ms | 19.88 ms | 19.58 ms | 21.82 ms | 35.19 ms |

**IoTbase Pico 2W (RP2350)** (UART0, GPIO0 TX / GPIO1 RX)

| Baud | Success | Failures | CRC / I/O error rate | Fastest | Avg | Median | p95 | Slowest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9600 | **500/500** | 0 | **0%** | 45.32 ms | 51.56 ms | 52.19 ms | 55.77 ms | 58.18 ms |
| 115200 | **500/500** | 0 | **0%** | 17.97 ms | 19.78 ms | 19.53 ms | 21.86 ms | 36.15 ms |

**Direction auto-sensing:** confirmed indirectly — zero lost or corrupt frames across these reliability runs (500/500 at both bauds on each carrier; 3000 reads total) plus the full suites at both speeds. First and last bytes were not clipped in practice.

### `byte_timeout_ms` confirmation

Default **10 ms** left unchanged. Same value works at **both** 9600 and 115200.

Inter-byte gap probe (valid FC03, bytes spaced by gap):

| Gap | Expected vs `byte_timeout_ms=10` | 9600 | 115200 |
| --- | --- | --- | --- |
| 2 ms | still one frame → response | PASS | PASS |
| 5 ms | still one frame → response | PASS | PASS |
| 12 ms | silence splits frame → no response | no response + recovery PASS | no response + recovery PASS |
| 20 ms | silence splits frame → no response | no response + recovery PASS | no response + recovery PASS |

Also PASS at both bauds:

- invalid CRC → silent drop, then valid frame recovers (`invalid_crc_test.py`)
- incomplete frame → no response, then recovery (`test_incomplete_frame.py`)
- 20 back-to-back valid frames (`test_back_to_back.py`) → 20/20

**Conclusion:** `byte_timeout_ms=10` is reliable on this bench; no per-baud change needed.

---

---

## Not covered by this bench

- Multi-drop (two or more slaves on one bus) — only one board was available
- Modbus Master (polling other Modbus devices)
- Analog (AO / DAC) modules

## Notes

1. Functional checklist and `byte_timeout_ms` tables are from the **IoTsmart RP2040** bench (UART0, GPIO0 TX / GPIO1 RX). CRC reliability (500 FC03 reads per baud) is recorded for RP2040, Pico 2W and ESP32-S3.
2. **IoTbase Pico 2W (RP2350)** uses the same UART0 and GPIO0/GPIO1 wiring and passed at 9600 and 115200.
3. **IoTsmart ESP32-S3** uses **UART1** on **GPIO43 (TX)** and **GPIO44 (RX)**. 115200 needs the REPL kept off that UART (`os.dupterm(None)`); with that applied, both baud rates passed.
4. Direction auto-sensing was judged by link stability (no oscilloscope).
