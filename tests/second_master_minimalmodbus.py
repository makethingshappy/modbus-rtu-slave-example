"""
Modbus RTU second-master checklist via minimalmodbus.

Short summary: Re-runs the functional checklist with an independent
master library (complement to pymodbus / QModMaster). Can flip board baud via
mpremote when needed.

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-11

Target slave: IoTsmart / IoTbase + Waveshare UART-RS485.
"""

import subprocess
import time
from pathlib import Path

import minimalmodbus
import serial

PORT = "/dev/cu.usbserial-BH00LLRL"
SLAVE = 1
INITIAL_HOLDING = [10, 20, 30, 40]
INITIAL_INPUT = [1234, 5678, 100, 65535]
INITIAL_COILS = [0, 1, 0, 1, 1, 0, 1, 0]
INITIAL_DISCRETE = [0, 1, 1, 0, 1, 0, 0, 1]
results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail)


def make_inst(baud):
    inst = minimalmodbus.Instrument(PORT, SLAVE)
    inst.serial.baudrate = baud
    inst.serial.bytesize = 8
    inst.serial.parity = serial.PARITY_NONE
    inst.serial.stopbits = 1
    inst.serial.timeout = 1.5
    inst.mode = minimalmodbus.MODE_RTU
    inst.clear_buffers_before_each_transaction = True
    return inst


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


def broadcast_coil(baud, address, value):
    raw = bytes(
        [0, 5, (address >> 8) & 255, address & 255, 0xFF if value else 0, 0]
    )
    crc = crc16(raw)
    frame = raw + bytes([crc & 255, (crc >> 8) & 255])
    with serial.Serial(
        PORT, baud, bytesize=8, parity="N", stopbits=1, timeout=0.2
    ) as ser:
        ser.reset_input_buffer()
        ser.write(frame)
        ser.flush()
        time.sleep(0.2)


def set_board_baud(baud):
    src = Path("test_rtu_main.py").read_text()
    if baud != 115200:
        src = src.replace("BAUDRATE = 115200", f"BAUDRATE = {baud}")
    tmp = Path(f"/tmp/test_rtu_main_{baud}.py")
    tmp.write_text(src)
    subprocess.check_call(
        ["mpremote", "connect", "/dev/cu.usbmodem21101", "cp", str(tmp), ":main.py"]
    )
    subprocess.check_call(
        ["mpremote", "connect", "/dev/cu.usbmodem21101", "reset"]
    )
    time.sleep(2)


def run(baud):
    print("\n=== minimalmodbus", baud, "===")
    inst = make_inst(baud)
    try:
        h = inst.read_registers(0, 4, 3)
        record(f"{baud} FC03", h == INITIAL_HOLDING, str(h))
        i = inst.read_registers(0, 4, 4)
        record(f"{baud} FC04", i == INITIAL_INPUT, str(i))
        c = inst.read_bits(0, 8, 1)
        record(f"{baud} FC01", c == INITIAL_COILS, str(c))
        d = inst.read_bits(0, 8, 2)
        record(f"{baud} FC02", d == INITIAL_DISCRETE, str(d))

        inst.write_register(0, 77, functioncode=6)
        h = inst.read_registers(0, 4, 3)
        record(f"{baud} FC06", h == [77, 20, 30, 40], str(h))

        inst.write_registers(0, [111, 222])
        h = inst.read_registers(0, 4, 3)
        record(f"{baud} FC10", h == [111, 222, 30, 40], str(h))

        inst.write_registers(0, INITIAL_HOLDING)
        h = inst.read_registers(0, 4, 3)
        record(f"{baud} restore HR", h == INITIAL_HOLDING, str(h))

        inst.write_bit(0, True, functioncode=5)
        c = inst.read_bits(0, 8, 1)
        record(f"{baud} FC05", c == [1, 1, 0, 1, 1, 0, 1, 0], str(c))

        inst.write_bits(0, INITIAL_COILS)
        c = inst.read_bits(0, 8, 1)
        record(f"{baud} FC0F", c == INITIAL_COILS, str(c))

        try:
            inst.read_registers(10, 1, 3)
            record(f"{baud} illegal addr", False, "no exception")
        except Exception as exc:
            record(f"{baud} illegal addr", True, type(exc).__name__)

        inst.serial.close()
        broadcast_coil(baud, 1, False)
        inst = make_inst(baud)
        c = inst.read_bits(0, 8, 1)
        record(
            f"{baud} broadcast FC05 applied",
            c == [0, 0, 0, 1, 1, 0, 1, 0],
            str(c),
        )
        inst.write_bits(0, INITIAL_COILS)

        ok = True
        for _ in range(25):
            if inst.read_registers(0, 4, 3) != INITIAL_HOLDING:
                ok = False
                break
        record(f"{baud} 25 reads", ok)
    except Exception as exc:
        record(f"{baud} suite error", False, repr(exc))
    finally:
        try:
            inst.serial.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        set_board_baud(115200)
        run(115200)
        set_board_baud(9600)
        run(9600)
    finally:
        set_board_baud(115200)
        passed = sum(1 for _, ok, _ in results if ok)
        print("\nSUMMARY")
        print(f"Passed {passed}/{len(results)}")
        for name, ok, detail in results:
            print(("PASS" if ok else "FAIL"), name, detail)
