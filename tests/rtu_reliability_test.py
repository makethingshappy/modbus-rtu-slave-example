"""
IoTflow Modbus RTU reliability / CRC-rate test (PC master).

Short summary: Issues many consecutive FC03 reads and reports success rate
and latency — used as CRC error-rate evidence for Stage 1 acceptance.

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.
"""

import time
import statistics
from pymodbus.client import ModbusSerialClient

PORT = "/dev/cu.usbserial-BH00LLRL"
BAUDRATE = 115200       # Run once at 9600, then change to 115200
SLAVE_ADDR = 1
NUM_READS = 500
TIMEOUT_SECONDS = 1
PAUSE_SECONDS = 0.01

EXPECTED = [10, 20, 30, 40]


def read_holding_registers(client):
    # Support PyModbus versions using either keyword.
    try:
        return client.read_holding_registers(
            address=0, count=4, device_id=SLAVE_ADDR
        )
    except TypeError:
        return client.read_holding_registers(
            address=0, count=4, slave=SLAVE_ADDR
        )


client = ModbusSerialClient(
    port=PORT,
    baudrate=BAUDRATE,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=TIMEOUT_SECONDS,
)

if not client.connect():
    print("ERROR: Could not open serial port:", PORT)
    raise SystemExit(1)

print(f"\nRTU reliability test: {BAUDRATE} baud")
print(f"Requests: {NUM_READS}; expected registers: {EXPECTED}")
print("Running...")

successes = 0
failures = []
times_ms = []

try:
    for i in range(1, NUM_READS + 1):
        started = time.perf_counter()

        try:
            response = read_holding_registers(client)
            elapsed_ms = (time.perf_counter() - started) * 1000

            if response is None:
                failures.append((i, "No response object"))
            elif response.isError():
                failures.append((i, f"Modbus exception: {response}"))
            elif response.registers != EXPECTED:
                failures.append(
                    (i, f"Unexpected values: {response.registers}")
                )
            else:
                successes += 1
                times_ms.append(elapsed_ms)

        except Exception as exc:
            failures.append((i, f"{type(exc).__name__}: {exc}"))

        if i % 50 == 0:
            print(
                f"Progress: {i}/{NUM_READS} | "
                f"successes: {successes} | failures: {len(failures)}"
            )

        time.sleep(PAUSE_SECONDS)

finally:
    client.close()

print("\n--- RESULTS ---")
print(f"Baud rate: {BAUDRATE}")
print(f"Successful reads: {successes}/{NUM_READS}")
print(f"Failed or incorrect reads: {len(failures)}")

if times_ms:
    ordered = sorted(times_ms)
    p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))

    print(f"Fastest response: {min(times_ms):.2f} ms")
    print(f"Average response: {statistics.mean(times_ms):.2f} ms")
    print(f"Median response: {statistics.median(times_ms):.2f} ms")
    print(f"95th percentile: {ordered[p95_index]:.2f} ms")
    print(f"Slowest response: {max(times_ms):.2f} ms")

if failures:
    print("\nFirst 20 failures:")
    for request_number, reason in failures[:20]:
        print(f"  Request {request_number}: {reason}")
else:
    print("\nPASS: all reads returned the expected values.")