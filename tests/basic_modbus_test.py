"""
IoTflow Modbus RTU smoke test (PC master).

Short summary: Single FC03 holding-register read to confirm the RS485 link
and slave address before running the full suite.

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.
"""

from pymodbus.client import ModbusSerialClient

# Match board BAUDRATE in test_rtu_main.py before running.
client = ModbusSerialClient(
    port="/dev/cu.usbserial-BH00LLRL",
    baudrate=115200,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=1,
    retries=0,
)

if not client.connect():
    raise RuntimeError("Could not open serial port")

try:
    result = client.read_holding_registers(
        address=0, count=4, device_id=1
    )
    print(result)

    if result.isError():
        print("FAIL:", result)
    else:
        print("Holding registers:", result.registers)
        expected = [10, 20, 30, 40]
        print("PASS" if result.registers == expected else "FAIL: unexpected values")
finally:
    client.close()
