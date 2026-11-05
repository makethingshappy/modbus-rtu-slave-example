"""
Modbus RTU hardware test suite (PC master).

Short summary: Runs the functional checklist over pymodbus at 9600 and
115200 against the board-side test_rtu_main.py slave.

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.

Run:
    python full_modbus_test.py

Requirements:
    python -m pip install pymodbus pyserial
"""

import time
import serial
from pymodbus.client import ModbusSerialClient

PORT = "/dev/cu.usbserial-BH00LLRL"
SLAVE = 1
TIMEOUT = 2

INITIAL_HOLDING = [10, 20, 30, 40]
INITIAL_INPUT = [1234, 5678, 100, 65535]
INITIAL_COILS = [0, 1, 0, 1, 1, 0, 1, 0]
INITIAL_DISCRETE = [0, 1, 1, 0, 1, 0, 0, 1]

results = []


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def check(name, operation):
    try:
        operation()
        record(name, True)
    except Exception as exc:
        record(name, False, repr(exc))


def expect_words(response, expected):
    assert not response.isError(), f"Modbus error: {response}"
    assert response.registers == expected, (
        f"Expected {expected}, got {response.registers}"
    )


def expect_bits(response, expected):
    assert not response.isError(), f"Modbus error: {response}"
    actual = [int(bit) for bit in response.bits[:len(expected)]]
    assert actual == expected, f"Expected {expected}, got {actual}"


def read_holding(client, expected):
    response = client.read_holding_registers(
        address=0, count=len(expected), device_id=SLAVE
    )
    expect_words(response, expected)


def read_input(client):
    response = client.read_input_registers(
        address=0, count=4, device_id=SLAVE
    )
    expect_words(response, INITIAL_INPUT)


def read_coils(client, expected):
    response = client.read_coils(
        address=0, count=len(expected), device_id=SLAVE
    )
    expect_bits(response, expected)


def read_discrete(client):
    response = client.read_discrete_inputs(
        address=0, count=8, device_id=SLAVE
    )
    expect_bits(response, INITIAL_DISCRETE)


def write_register(client, address, value):
    response = client.write_register(
        address=address, value=value, device_id=SLAVE
    )
    assert not response.isError(), f"Write failed: {response}"


def write_registers(client, address, values):
    response = client.write_registers(
        address=address, values=values, device_id=SLAVE
    )
    assert not response.isError(), f"Write failed: {response}"


def write_coil(client, address, value):
    response = client.write_coil(
        address=address, value=bool(value), device_id=SLAVE
    )
    assert not response.isError(), f"Write failed: {response}"


def write_coils(client, address, values):
    response = client.write_coils(
        address=address,
        values=[bool(v) for v in values],
        device_id=SLAVE,
    )
    assert not response.isError(), f"Write failed: {response}"


def test_invalid_address(client):
    response = client.read_holding_registers(
        address=10, count=1, device_id=SLAVE
    )
    assert response.isError(), f"Expected exception, got {response}"
    code = getattr(response, "exception_code", None)
    assert code == 2, f"Expected exception code 0x02, got {code!r}"


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def broadcast_write_single_coil(port, baudrate, address, value):
    # FC05 broadcast. Modbus RTU CRC is transmitted low byte first.
    raw = bytes([0, 5, (address >> 8) & 255, address & 255,
                 0xFF if value else 0, 0])
    crc = crc16(raw)
    frame = raw + bytes([crc & 255, (crc >> 8) & 255])

    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=0.2,
    ) as ser:
        ser.reset_input_buffer()
        ser.write(frame)
        ser.flush()
        time.sleep(0.15)
        # Some USB-RS485 adapters echo transmitted bytes, so do not
        # treat received bytes alone as proof of a slave response.


def run_suite(baudrate):
    print("\n" + "=" * 58)
    print(f"TESTING AT {baudrate} BAUD")
    print("=" * 58)
    input(
        f"Set the slave node to {baudrate} baud, restart its script, "
        "and press Enter here when it says Ready..."
    )

    client = ModbusSerialClient(
        port=PORT,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=TIMEOUT,
        retries=0,
    )

    try:
        if not client.connect():
            record(f"{baudrate}: open serial port", False)
            return

        record(f"{baudrate}: connect", True)

        check(f"{baudrate}: FC03 read holding registers",
              lambda: read_holding(client, INITIAL_HOLDING))
        check(f"{baudrate}: FC04 read input registers", lambda: read_input(client))
        check(f"{baudrate}: FC01 read coils",
              lambda: read_coils(client, INITIAL_COILS))
        check(f"{baudrate}: FC02 read discrete inputs",
              lambda: read_discrete(client))

        def single_register_test():
            write_register(client, 0, 77)
            read_holding(client, [77, 20, 30, 40])

        check(f"{baudrate}: FC06 write single register", single_register_test)

        def multiple_register_test():
            write_registers(client, 0, [111, 222])
            read_holding(client, [111, 222, 30, 40])

        check(f"{baudrate}: FC10 write multiple registers",
              multiple_register_test)

        def restore_registers():
            write_registers(client, 0, INITIAL_HOLDING)
            read_holding(client, INITIAL_HOLDING)

        check(f"{baudrate}: restore holding registers", restore_registers)

        def single_coil_test():
            write_coil(client, 0, True)
            read_coils(client, [1, 1, 0, 1, 1, 0, 1, 0])

        check(f"{baudrate}: FC05 write single coil", single_coil_test)

        def multiple_coil_test():
            write_coils(client, 0, INITIAL_COILS)
            read_coils(client, INITIAL_COILS)

        check(f"{baudrate}: FC0F write multiple coils", multiple_coil_test)

        check(f"{baudrate}: invalid address exception 0x02",
              lambda: test_invalid_address(client))

        # Broadcast is sent with PyModbus disconnected so the raw serial
        # port can open. Verify its effect with an ordinary unicast read.
        client.close()

        def broadcast_test():
            broadcast_write_single_coil(PORT, baudrate, 1, False)
            client.connect()
            read_coils(client, [0, 0, 0, 1, 1, 0, 1, 0])

        check(f"{baudrate}: broadcast FC05 applied without reply required",
              broadcast_test)

        def restore_coils():
            write_coils(client, 0, INITIAL_COILS)
            read_coils(client, INITIAL_COILS)

        check(f"{baudrate}: restore coils", restore_coils)

        def repeated_reads():
            for i in range(25):
                read_holding(client, INITIAL_HOLDING)

        check(f"{baudrate}: 25 consecutive holding-register reads",
              repeated_reads)

    except Exception as exc:
        record(f"{baudrate}: unexpected suite error", False, repr(exc))
    finally:
        client.close()


try:
    print("Modbus RTU test suite")
    print("Port:", PORT)
    print("Slave address:", SLAVE)
    print("Run the board-side test_rtu_main.py throughout.")

    run_suite(9600)
    run_suite(115200)

finally:
    print("\n" + "=" * 58)
    print("FINAL SUMMARY")
    print("=" * 58)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}"
              + (f" — {detail}" if detail else ""))

    print(f"\nPassed: {passed} | Failed: {failed} | Total: {len(results)}")