"""
Modbus RTU back-to-back frame test (PC master).

Short summary: Sends many valid FC03 requests in succession and checks each
response matches the stand-in holding-register frame.

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.
"""

import time
import serial

PORT = "/dev/cu.usbserial-BH00LLRL"
BAUDRATE = 115200
COUNT = 20
# Expected FC03 response for holding registers [10, 20, 30, 40] at slave 1.
EXPECTED = bytes.fromhex(
    "01 03 08 00 0a 00 14 00 1e 00 28 6f cc"
)

def modbus_crc(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

request = bytearray([1, 3, 0, 0, 0, 4])
crc = modbus_crc(request)
request.extend([crc & 0xFF, crc >> 8])
REQUEST = bytes(request)

with serial.Serial(
    PORT, BAUDRATE, bytesize=8, parity="N",
    stopbits=1, timeout=0.02
) as ser:
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    passed = 0
    failed = 0

    for i in range(1, COUNT + 1):
        # Wait for the previous response to finish before the next request.
        ser.reset_input_buffer()
        ser.write(REQUEST)
        ser.flush()

        response = bytearray()
        deadline = time.monotonic() + 0.5

        while time.monotonic() < deadline and len(response) < len(EXPECTED):
            n = ser.in_waiting
            if n:
                response.extend(ser.read(n))
            else:
                time.sleep(0.001)

        if bytes(response) == EXPECTED:
            passed += 1
            print(f"{i:02d}: PASS")
        else:
            failed += 1
            print(f"{i:02d}: FAIL — received {response.hex(' ') or '(nothing)'}")

    print(f"\nResults: {passed}/{COUNT} passed, {failed} failed")