"""
IoTflow Modbus RTU invalid-CRC edge test (PC master).

Short summary: Sends a corrupted-CRC FC03 request (expect silence), then a
valid request (expect recovery). Confirms slave drops bad frames per RTU rules.

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.
"""

import time
import serial

PORT = "/dev/cu.usbserial-BH00LLRL"
BAUDRATE = 115200
SLAVE_ADDR = 1
TIMEOUT = 0.25

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

def make_read_request(corrupt_crc=False):
    # FC03: read holding registers, address 0, quantity 4
    frame = bytearray([
        SLAVE_ADDR, 0x03,
        0x00, 0x00,
        0x00, 0x04
    ])
    crc = modbus_crc(frame)
    frame.extend([crc & 0xFF, (crc >> 8) & 0xFF])

    if corrupt_crc:
        frame[-1] ^= 0xFF

    return bytes(frame)

def read_response(ser, window=TIMEOUT):
    data = bytearray()
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting:
            data.extend(ser.read(waiting))
        else:
            time.sleep(0.002)
    return bytes(data)

with serial.Serial(
    PORT, BAUDRATE, bytesize=8, parity="N", stopbits=1,
    timeout=0.02
) as ser:
    # Clear stale bytes before beginning.
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print(f"Testing invalid CRC at {BAUDRATE} baud")

    bad_frame = make_read_request(corrupt_crc=True)
    print("Sending invalid-CRC request:", bad_frame.hex(" "))
    ser.write(bad_frame)
    ser.flush()

    bad_response = read_response(ser)
    if bad_response:
        print("FAIL: received bytes after invalid CRC:",
              bad_response.hex(" "))
    else:
        print("PASS: no response observed after invalid CRC")

    # Give the slave time to return to its normal polling loop.
    time.sleep(0.1)
    ser.reset_input_buffer()

    good_frame = make_read_request(corrupt_crc=False)
    print("Sending valid request:", good_frame.hex(" "))
    ser.write(good_frame)
    ser.flush()

    good_response = read_response(ser, window=0.5)
    if len(good_response) >= 13:
        print("Response bytes:", good_response.hex(" "))
        print("PASS: received a response after the valid request")
    else:
        print("CHECK: no complete expected response detected.")
        print("Received:", good_response.hex(" ") or "(no bytes)")