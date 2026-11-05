# IoTflow Modbus RTU Slave — hardware bring-up test (board-side)
#
# Short summary: Runs ModbusRTUSlave on UART with a stand-in register map so a
# PC master (pymodbus / QModMaster) can verify RTU timing and framing.
#
# Author: Arshia Keshvari
# Role: Independent Developer, Engineer, and Project Author
# Last Updated: 2026-10-25
#
# Target: IoTsmart / IoTbase + external Waveshare UART-RS485
# Copy modbus_slave.py to the board as well (e.g. lib/modbus_slave.py).
# IMPORTANT: Verify UART_ID and GPIO pins for your exact carrier.

import os
os.dupterm(None)

from machine import UART, Pin
import time

from modbus_slave import ModbusRTUSlave, RegisterStore

# ---- Hardware configuration: VERIFY THESE PINS ----
# Default UART0 GP0/GP1 matches IoTsmart RP2040 / RP2350 Tiny pinout.
UART_ID = 0
TX_PIN = 0
RX_PIN = 1

BAUDRATE = 115200       # Repeat bring-up at 9600 as well
SLAVE_ADDR = 1
BYTE_TIMEOUT_MS = 10    # Works on most microcontrollers

# ---- Test register map ----
# Holding registers: FC03 reads
# Input registers: FC04 reads
# Coils: FC01 reads / FC05 and FC0F writes
store = RegisterStore(
    num_coils=8,
    num_discrete_inputs=8,
    num_input_registers=4,
    num_holding_registers=4,
)

# Known values make it easy to verify master responses.
store.coils[:] = [0, 1, 0, 1, 1, 0, 1, 0]
store.discrete_inputs[:] = [0, 1, 1, 0, 1, 0, 0, 1]
store.input_registers[:] = [1234, 5678, 100, 65535]
store.holding_registers[:] = [10, 20, 30, 40]


def on_write(block_name, start_address, values):
    print("WRITE:", block_name,
          "address:", start_address,
          "values:", values)


store.on_write = on_write

uart = UART(
    UART_ID,
    baudrate=BAUDRATE,
    bits=8,
    parity=None,
    stop=1,
    tx=Pin(TX_PIN),
    rx=Pin(RX_PIN),
    timeout=0,
)

slave = ModbusRTUSlave(
    uart,
    store,
    slave_addr=SLAVE_ADDR,
    byte_timeout_ms=BYTE_TIMEOUT_MS,
)

print()
print("IoTflow Modbus RTU bring-up test")
print("Target: IoTsmart / IoTbase + Waveshare UART-RS485")
print("UART:", UART_ID)
print("TX GPIO:", TX_PIN, "RX GPIO:", RX_PIN)
print("Baud:", BAUDRATE, "8N1")
print("Slave address:", SLAVE_ADDR)
print("Byte timeout:", BYTE_TIMEOUT_MS, "ms")
print("Ready - connect a Modbus RTU master")
print("Input registers: 0=1234, 1=5678, 2=100, 3=65535")
print("Holding registers: 0=10, 1=20, 2=30, 3=40")

while True:
    slave.poll()
    time.sleep_ms(1)