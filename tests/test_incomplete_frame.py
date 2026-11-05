"""
Modbus RTU incomplete-frame edge test (PC master).

Short summary: Sends a truncated request (expect no response), then a full
valid FC03 to confirm the slave recovers after byte_timeout_ms.

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.
"""

import time
import serial

PORT = "/dev/cu.usbserial-BH00LLRL"
BAUDRATE = 115200

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

def read_for(ser, duration):
    result = bytearray()
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        n = ser.in_waiting
        if n:
            result.extend(ser.read(n))
        else:
            time.sleep(0.002)
    return bytes(result)

def valid_request():
    frame = bytearray([1, 3, 0, 0, 0, 4])
    crc = modbus_crc(frame)
    frame.extend([crc & 0xFF, crc >> 8])
    return bytes(frame)

with serial.Serial(
    PORT, BAUDRATE, bytesize=8, parity="N",
    stopbits=1, timeout=0.02
) as ser:
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    # Send only the first four bytes of an 8-byte FC03 request.
    fragment = valid_request()[:4]
    print("Sending incomplete frame:", fragment.hex(" "))
    ser.write(fragment)
    ser.flush()

    response = read_for(ser, 0.15)
    if response:
        print("CHECK: bytes observed after incomplete frame:",
              response.hex(" "))
        print("Inspect for adapter echo before judging.")
    else:
        print("PASS: no response observed to incomplete frame")

    # Allow the slave to finish its receive timeout and recover.
    time.sleep(0.1)
    ser.reset_input_buffer()

    print("Sending complete valid request:", valid_request().hex(" "))
    ser.write(valid_request())
    ser.flush()

    response = read_for(ser, 0.5)
    print("Received:", response.hex(" ") or "(no bytes)")

    if response == bytes.fromhex(
        "01 03 08 00 0a 00 14 00 1e 00 28 6f cc"
    ):
        print("PASS: slave recovered and returned expected data")
    else:
        print("CHECK: response differed from the expected frame")