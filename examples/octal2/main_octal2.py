# IoTextra Octal2 — Modbus RTU slave on the real DI/DO module.
#
# Standalone board script.
# Files used (copied unchanged from other MTH projects):
#   iot_driver.py   — IoTextra driver, taken from the IoTflow project
#   modbus_slave.py — Modbus RTU slave engine (repository root)
#   Digital.json    — IoTextra Octal2 channel template, taken from the IoTflow project
#
# Author: Arshia Keshvari
# Role: Independent Developer, Engineer, and Project Author
# Last Updated: 2026-10-25
#
# Octal2 (zero-based channel_number, pin_config 0b00001111):
#   DI channels 0..3  -> TCA9534 P0..P3  -> discrete inputs 0..3
#   DO channels 4..7  -> TCA9534 P4..P7  -> coils 0..3
#
# IotDriver.set_output() is 1-based (TCA bit = channel - 1), the same
# numbering as the Octal Node-RED topics output/5 .. output/8.
# Coil 0 therefore calls set_output(5, ...) and drives LED 1.
#
# UART matches the Waveshare bench (UART0, GPIO0 TX, GPIO1 RX).
#
# PC master check (pymodbus, baud must match the board):
#   write_coil(address=0, value=True, device_id=1)          # DO channel 4 ON
#   read_discrete_inputs(address=0, count=4, device_id=1)   # DI channels 0..3

import os

os.dupterm(None)

try:
    import ujson as json
except ImportError:
    import json

import machine
from machine import UART, Pin
import time

import iot_driver
from iot_driver import IotDriver
from modbus_slave import ModbusRTUSlave, RegisterStore

# ---- RS485 UART (Waveshare bench) ----
UART_ID = 0
TX_PIN = 0
RX_PIN = 1
BAUDRATE = 115200
SLAVE_ADDR = 1
BYTE_TIMEOUT_MS = 10

# ---- Manual register map (not generated from the channel list) ----
# Zero-based channel numbers from Digital.json.
DI_CHANNELS = (0, 1, 2, 3)
DO_CHANNELS = (4, 5, 6, 7)

driver = None


def _parse_int(value):
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text[:2] in ("0b", "0B"):
        return int(text[2:], 2)
    if text[:2] in ("0x", "0X"):
        return int(text[2:], 16)
    return int(text)


def _template_path():
    name = "Digital.json"
    try:
        path = __file__
    except NameError:
        return name
    if "/" in path:
        return path.rsplit("/", 1)[0] + "/" + name
    return name


def _expected_pin_config():
    """pin_config bit = 1 for each manual DI channel, 0 for each manual DO channel."""
    mask = 0
    for channel in DI_CHANNELS:
        mask |= 1 << channel
    for channel in DO_CHANNELS:
        mask &= ~(1 << channel)
    return mask


def load_template(path):
    with open(path, "r") as handle:
        template = json.load(handle)
    hardware = template["hardware"]
    pin_config = _parse_int(template["pin_config"])
    expected = _expected_pin_config()
    if pin_config != expected:
        raise ValueError(
            "Digital.json pin_config "
            + bin(pin_config)
            + " does not match the manual Octal2 map "
            + bin(expected)
        )
    gpio_host_pins = {}
    for key, pin in hardware["gpio_host_pins"].items():
        gpio_host_pins[int(key)] = int(pin)
    names = {}
    for entry in template["channels"]:
        names[int(entry["channel_number"])] = entry["name"]
    return {
        "mezzanine_type": template.get("mezzanine_type", ""),
        "bus_id": int(hardware["i2c_bus_id"]),
        "sda_pin": int(hardware["i2c_sda_pin"]),
        "scl_pin": int(hardware["i2c_scl_pin"]),
        "device_address": _parse_int(hardware["i2c_device_addr"]),
        "gpio_host_pins": gpio_host_pins,
        "pin_config": pin_config,
        "hardware_mode": hardware["mode"],
        "names": names,
    }


class _SoftI2C(machine.SoftI2C):
    """Same call shape as machine.I2C(bus_id, sda=..., scl=..., freq=...).

    On this Pico 2 W, MicroPython 1.29 hardware I2C scans the bus and then
    returns EIO for every read and write. SoftI2C on the same pins talks to
    the expander. 100 kHz is the rate that was checked against the TCA9534.
    """

    def __init__(self, bus_id, sda, scl, freq=400000, timeout=50000):
        super().__init__(scl=scl, sda=sda, freq=100000, timeout=timeout)


class _MachineI2CProxy:
    def __getattr__(self, name):
        if name == "I2C":
            return _SoftI2C
        return getattr(machine, name)


def _hardware_i2c_ok(bus_id, sda_pin, scl_pin, addr):
    try:
        bus = machine.I2C(
            bus_id,
            sda=machine.Pin(sda_pin),
            scl=machine.Pin(scl_pin),
            freq=100000,
        )
        bus.readfrom_mem(addr, 0x00, 1)
        return True
    except OSError:
        return False


def _prepare_driver_i2c(config):
    if _hardware_i2c_ok(
        config["bus_id"],
        config["sda_pin"],
        config["scl_pin"],
        config["device_address"],
    ):
        print("I2C: hardware")
        return
    # iot_driver looks up machine.I2C when the driver is constructed.
    # The built-in machine module cannot be patched; the driver's global can.
    iot_driver.machine = _MachineI2CProxy()
    print("I2C: SoftI2C (hardware I2C transfers returned EIO)")


def on_write(block_name, start_address, values):
    """Drive the physical DO when a Modbus master writes a coil."""
    if block_name != "coils":
        return
    for offset, value in enumerate(values):
        address = start_address + offset
        if address < 0 or address >= len(DO_CHANNELS):
            continue
        # Zero-based DO channel 4..7 -> 1-based driver channel 5..8.
        channel = DO_CHANNELS[address] + 1
        driver.set_output(channel, bool(value))
        latch_text = ""
        if driver.i2c is not None:
            try:
                latch = driver.i2c.readfrom_mem(
                    driver.device_address, driver.OUTPUT_PORT_REGISTER, 1
                )[0]
                bit = (latch >> (channel - 1)) & 1
                latch_text = " latch %s bit %s=%s" % (hex(latch), channel - 1, bit)
            except OSError as exc:
                latch_text = " latch read failed " + str(exc)
        print(
            "COIL",
            address,
            "DO channel",
            DO_CHANNELS[address],
            "->",
            bool(value),
            latch_text,
        )


template_path = _template_path()
config = load_template(template_path)
_prepare_driver_i2c(config)

driver = IotDriver(
    bus_id=config["bus_id"],
    sda_pin=config["sda_pin"],
    scl_pin=config["scl_pin"],
    device_address=config["device_address"],
    gpio_host_pins=config["gpio_host_pins"],
    pin_config=config["pin_config"],
    hardware_mode=config["hardware_mode"],
)

store = RegisterStore(
    num_coils=len(DO_CHANNELS),
    num_discrete_inputs=len(DI_CHANNELS),
)
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
print("IoTextra Octal2 Modbus RTU slave")
print("Template:", template_path)
print("Mezzanine:", config["mezzanine_type"])
print(
    "I2C bus",
    config["bus_id"],
    "SDA",
    config["sda_pin"],
    "SCL",
    config["scl_pin"],
    "addr",
    hex(config["device_address"]),
)
print("pin_config: 0b{:08b}".format(config["pin_config"]), "mode:", config["hardware_mode"])
print("UART:", UART_ID, "TX GPIO:", TX_PIN, "RX GPIO:", RX_PIN)
print("Baud:", BAUDRATE, "8N1  slave:", SLAVE_ADDR)
print("Byte timeout:", BYTE_TIMEOUT_MS, "ms")
if driver.i2c is None:
    print("Warning: I/O expander did not initialize; outputs will not switch")
print("Coils (FC01/05/15), zero-based address -> DO channel:")
for address, channel in enumerate(DO_CHANNELS):
    label = config["names"].get(channel, "")
    print(" ", address, "->", channel, label)
print("Discrete inputs (FC02), zero-based address -> DI channel:")
for address, channel in enumerate(DI_CHANNELS):
    label = config["names"].get(channel, "")
    print(" ", address, "->", channel, label)
print("Ready - connect a Modbus RTU master")

while True:
    states = driver.read_all_inputs()
    if states is not None:
        for address, position in enumerate(DI_CHANNELS):
            if position >= len(states):
                continue
            value = states[position]
            if value is None:
                continue
            store.discrete_inputs[address] = 1 if value else 0
    slave.poll()
    time.sleep_ms(1)
