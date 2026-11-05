"""
Modbus RTU inter-byte timing probe (PC master).

Short summary: Spaces request bytes by INTERBYTE_GAP_SECONDS to probe
frame-boundary behaviour relative to slave byte_timeout_ms (default 10 ms).

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.
"""

import time
import serial

PORT = "/dev/cu.usbserial-BH00LLRL"
BAUDRATE = 115200
# Gaps below byte_timeout_ms should still assemble one frame; above should not.
INTERBYTE_GAP_SECONDS = 0.002

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
request = bytes(request)

def read_for(ser, seconds):
    result = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        count = ser.in_waiting
        if count:
            result.extend(ser.read(count))
        else:
            time.sleep(0.001)
    return bytes(result)

with serial.Serial(
    PORT, BAUDRATE, bytesize=8, parity="N",
    stopbits=1, timeout=0.02
) as ser:
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print(f"Baud rate: {BAUDRATE}")
    print(f"Inter-byte delay: {INTERBYTE_GAP_SECONDS * 1000:.1f} ms")
    print("Sending request:", request.hex(" "))

    for byte in request:
        ser.write(bytes([byte]))
        ser.flush()
        time.sleep(INTERBYTE_GAP_SECONDS)

    response = read_for(ser, 0.15)
    print("Received:", response.hex(" ") or "(no bytes)")

    if response:
        print("CHECK: slave responded despite the excessive inter-byte gap.")
    else:
        print("CHECK: no response observed.")

    # Confirm the slave still handles a normal request.
    time.sleep(0.1)
    ser.reset_input_buffer()
    ser.write(request)
    ser.flush()

    normal_response = read_for(ser, 0.5)
    print("Normal request response:",
          normal_response.hex(" ") or "(no bytes)")