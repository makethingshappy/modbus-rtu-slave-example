"""
modbus_slave.py — Minimal Modbus RTU Slave engine for MicroPython.

Short summary: MIT-licensed RTU slave (PDU + CRC + UART framing) with no
external Modbus dependencies.

Copyright (c) 2026 makethingshappy (MTH LLC)

Hardware: IoTsmart / IoTbase are pinout-compatible on Waveshare
Tiny-compatible boards; UART + external Waveshare UART-RS485 bring-up
applies to both.

Design notes
------------
This module implements only the SLAVE (server) side of Modbus, since the board
responds to an external Master (PLC / SCADA / ThingsBoard Gateway /
Node-RED node-red-contrib-modbus). Master/client behaviour is out of scope.

Supported function codes:
    0x01  Read Coils
    0x02  Read Discrete Inputs
    0x03  Read Holding Registers
    0x04  Read Input Registers
    0x05  Write Single Coil
    0x06  Write Single Holding Register
    0x0F  Write Multiple Coils
    0x10  Write Multiple Holding Registers

Register map (RegisterStore) is intentionally decoupled from IoTextra module
drivers: the application builds the map and hands it to this engine — this
module has no knowledge of IoTextra hardware at all.

Validated on IoTsmart RP2040, IoTbase Pico 2W (RP2350) and IoTsmart ESP32-S3
with an external isolated UART-RS485 at 9600 and 115200, byte_timeout_ms=10
(see docs/BRINGUP_REPORT.md).
"""

import struct

try:
    import utime as time
except ImportError:
    import time  # CPython fallback for offline unit testing


# ---------------------------------------------------------------------------
# Exception codes (Modbus spec §7)
# ---------------------------------------------------------------------------
ILLEGAL_FUNCTION = 0x01
ILLEGAL_DATA_ADDRESS = 0x02
ILLEGAL_DATA_VALUE = 0x03
SLAVE_DEVICE_FAILURE = 0x04

# Function codes
FC_READ_COILS = 0x01
FC_READ_DISCRETE_INPUTS = 0x02
FC_READ_HOLDING_REGISTERS = 0x03
FC_READ_INPUT_REGISTERS = 0x04
FC_WRITE_SINGLE_COIL = 0x05
FC_WRITE_SINGLE_REGISTER = 0x06
FC_WRITE_MULTIPLE_COILS = 0x0F
FC_WRITE_MULTIPLE_REGISTERS = 0x10

_SUPPORTED_FC = (
    FC_READ_COILS,
    FC_READ_DISCRETE_INPUTS,
    FC_READ_HOLDING_REGISTERS,
    FC_READ_INPUT_REGISTERS,
    FC_WRITE_SINGLE_COIL,
    FC_WRITE_SINGLE_REGISTER,
    FC_WRITE_MULTIPLE_COILS,
    FC_WRITE_MULTIPLE_REGISTERS,
)


class ModbusException(Exception):
    """Raised internally to signal a Modbus exception response."""

    def __init__(self, code):
        self.code = code
        super().__init__("Modbus exception 0x%02X" % code)


# ---------------------------------------------------------------------------
# Register storage
# ---------------------------------------------------------------------------
class RegisterStore:
    """
    Backing storage for the four Modbus data blocks.

    Each block is a flat, zero-indexed list — the application is responsible
    for populating these lists and for reading back updated
    values after a write to apply them to the real IoTextra channel
    (relay/coil/etc). This class does not know about hardware.

    coils / discrete_inputs : lists of 0/1 (int)
    input_registers / holding_registers : lists of 16-bit unsigned int (0-65535)
    """

    def __init__(self, num_coils=0, num_discrete_inputs=0,
                 num_input_registers=0, num_holding_registers=0):
        self.coils = [0] * num_coils
        self.discrete_inputs = [0] * num_discrete_inputs
        self.input_registers = [0] * num_input_registers
        self.holding_registers = [0] * num_holding_registers

        # Optional hook: called after any successful write, as
        #   on_write(block_name, start_address, values)
        # so the application can push the change out to the real IoTextra driver
        # (e.g. actually toggle a relay) instead of just updating memory.
        self.on_write = None

    # -- helpers -------------------------------------------------------
    def _check_range(self, block, start, qty):
        if qty <= 0:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        if start < 0 or start + qty > len(block):
            raise ModbusException(ILLEGAL_DATA_ADDRESS)

    def read_bits(self, block, start, qty):
        self._check_range(block, start, qty)
        return block[start:start + qty]

    def write_bits(self, block_name, block, start, values):
        self._check_range(block, start, len(values))
        for i, v in enumerate(values):
            block[start + i] = 1 if v else 0
        if self.on_write:
            self.on_write(block_name, start, values)

    def read_words(self, block, start, qty):
        self._check_range(block, start, qty)
        return block[start:start + qty]

    def write_words(self, block_name, block, start, values):
        self._check_range(block, start, len(values))
        for v in values:
            if not (0 <= v <= 0xFFFF):
                raise ModbusException(ILLEGAL_DATA_VALUE)
        for i, v in enumerate(values):
            block[start + i] = v
        if self.on_write:
            self.on_write(block_name, start, values)


# ---------------------------------------------------------------------------
# PDU processing
# ---------------------------------------------------------------------------
class _PDUHandler:
    """
    Provides process_pdu() — the Modbus function-code logic used by
    ModbusRTUSlave.
    """

    def __init__(self, store):
        self.store = store

    def process_pdu(self, pdu):
        """
        pdu: bytes, starting with the function code.
        Returns: response pdu (bytes), including exception responses.
        """
        if len(pdu) < 1:
            raise ModbusException(ILLEGAL_FUNCTION)

        fc = pdu[0]
        try:
            if fc not in _SUPPORTED_FC:
                raise ModbusException(ILLEGAL_FUNCTION)

            if fc == FC_READ_COILS:
                return self._read_bits_response(fc, pdu, self.store.coils)
            elif fc == FC_READ_DISCRETE_INPUTS:
                return self._read_bits_response(fc, pdu, self.store.discrete_inputs)
            elif fc == FC_READ_HOLDING_REGISTERS:
                return self._read_words_response(fc, pdu, self.store.holding_registers)
            elif fc == FC_READ_INPUT_REGISTERS:
                return self._read_words_response(fc, pdu, self.store.input_registers)
            elif fc == FC_WRITE_SINGLE_COIL:
                return self._write_single_coil(pdu)
            elif fc == FC_WRITE_SINGLE_REGISTER:
                return self._write_single_register(pdu)
            elif fc == FC_WRITE_MULTIPLE_COILS:
                return self._write_multiple_coils(pdu)
            elif fc == FC_WRITE_MULTIPLE_REGISTERS:
                return self._write_multiple_registers(pdu)

        except ModbusException as e:
            return struct.pack(">BB", fc | 0x80, e.code)
        except Exception:
            # Anything unexpected -> SLAVE_DEVICE_FAILURE, never crash
            # the application's main loop because of a malformed request.
            return struct.pack(">BB", fc | 0x80, SLAVE_DEVICE_FAILURE)

    # -- read helpers ----------------------------------------------------
    def _read_bits_response(self, fc, pdu, block):
        if len(pdu) != 5:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        start, qty = struct.unpack(">HH", pdu[1:5])
        if qty < 1 or qty > 2000:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        bits = self.store.read_bits(block, start, qty)
        byte_count = (qty + 7) // 8
        packed = bytearray(byte_count)
        for i, bit in enumerate(bits):
            if bit:
                packed[i // 8] |= (1 << (i % 8))
        return struct.pack(">BB", fc, byte_count) + bytes(packed)

    def _read_words_response(self, fc, pdu, block):
        if len(pdu) != 5:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        start, qty = struct.unpack(">HH", pdu[1:5])
        if qty < 1 or qty > 125:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        words = self.store.read_words(block, start, qty)
        out = struct.pack(">BB", fc, qty * 2)
        for w in words:
            out += struct.pack(">H", w)
        return out

    # -- write helpers -----------------------------------------------------
    def _write_single_coil(self, pdu):
        if len(pdu) != 5:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        addr, value = struct.unpack(">HH", pdu[1:5])
        if value not in (0x0000, 0xFF00):
            raise ModbusException(ILLEGAL_DATA_VALUE)
        self.store.write_bits("coils", self.store.coils, addr, [1 if value else 0])
        return pdu  # echo request per spec

    def _write_single_register(self, pdu):
        if len(pdu) != 5:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        addr, value = struct.unpack(">HH", pdu[1:5])
        self.store.write_words("holding_registers", self.store.holding_registers,
                                addr, [value])
        return pdu  # echo request per spec

    def _write_multiple_coils(self, pdu):
        if len(pdu) < 6:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        start, qty, byte_count = struct.unpack(">HHB", pdu[1:6])
        if qty < 1 or qty > 1968 or byte_count != (qty + 7) // 8:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        if len(pdu) != 6 + byte_count:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        raw = pdu[6:6 + byte_count]
        values = []
        for i in range(qty):
            byte_val = raw[i // 8]
            values.append(1 if (byte_val >> (i % 8)) & 1 else 0)
        self.store.write_bits("coils", self.store.coils, start, values)
        return struct.pack(">BHH", FC_WRITE_MULTIPLE_COILS, start, qty)

    def _write_multiple_registers(self, pdu):
        if len(pdu) < 6:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        start, qty, byte_count = struct.unpack(">HHB", pdu[1:6])
        if qty < 1 or qty > 123 or byte_count != qty * 2:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        if len(pdu) != 6 + byte_count:
            raise ModbusException(ILLEGAL_DATA_VALUE)
        values = list(struct.unpack(">%dH" % qty, pdu[6:6 + byte_count]))
        self.store.write_words("holding_registers", self.store.holding_registers,
                                start, values)
        return struct.pack(">BHH", FC_WRITE_MULTIPLE_REGISTERS, start, qty)


# ---------------------------------------------------------------------------
# CRC16 (Modbus polynomial 0xA001), table-driven for speed on MCU
# ---------------------------------------------------------------------------
def _build_crc16_table():
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
        table.append(crc)
    return table


_CRC16_TABLE = _build_crc16_table()


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc = (crc >> 8) ^ _CRC16_TABLE[(crc ^ b) & 0xFF]
    return crc


# ---------------------------------------------------------------------------
# RTU slave (RS485 via SP3485 on IoTbase)
# ---------------------------------------------------------------------------
class ModbusRTUSlave(_PDUHandler):
    """
    Polling-style RTU slave. Call .poll() frequently from the application's main
    loop — this class never blocks longer
    than the configured byte_timeout_ms.

    ctrl_pin, if given, is driven HIGH before transmitting the response and
    LOW again afterwards, for RS485 transceivers (like SP3485) that need
    explicit driver-enable control rather than auto-direction hardware.
    """

    def __init__(self, uart, store, slave_addr, ctrl_pin=None,
                 byte_timeout_ms=10):
        super().__init__(store)
        self.uart = uart
        self.slave_addr = slave_addr
        self.ctrl_pin = ctrl_pin
        self.byte_timeout_ms = byte_timeout_ms
        self._buf = bytearray()
        self._last_byte_ms = None

    def poll(self):
        """
        Non-blocking-ish: drains whatever bytes are currently in the UART
        buffer, and if nothing new has arrived for byte_timeout_ms after
        having received something, treats the buffer as a complete frame
        (this approximates the T3.5 inter-character silence rule from the
        Modbus spec; exact timing must be re-verified against real UART
        behaviour before production use).
        """
        n = self.uart.any() if hasattr(self.uart, "any") else 0
        if n:
            data = self.uart.read(n)
            if data:
                self._buf.extend(data)
                self._last_byte_ms = time.ticks_ms()
            return

        if self._buf and self._last_byte_ms is not None:
            elapsed = time.ticks_diff(time.ticks_ms(), self._last_byte_ms)
            if elapsed >= self.byte_timeout_ms:
                self._handle_frame(bytes(self._buf))
                self._buf = bytearray()
                self._last_byte_ms = None

    def _handle_frame(self, frame):
        if len(frame) < 4:  # addr + fc + crc(2) minimum
            return
        addr = frame[0]
        payload, recv_crc = frame[1:-2], frame[-2:]
        if addr != self.slave_addr and addr != 0:
            return  # not for us and not broadcast — silently ignore, per spec
        calc_crc = crc16(frame[:-2])
        if struct.pack("<H", calc_crc) != recv_crc:
            return  # CRC mismatch — silently drop, master will retry

        if addr == 0:
            # Broadcast (Modbus spec): process the write, never respond.
            # Reads make no sense on broadcast (no one could receive the
            # answer) — process_pdu() handles them harmlessly either way,
            # the result is simply discarded.
            self.process_pdu(payload)
            return

        response_pdu = self.process_pdu(payload)
        response = bytes([addr]) + response_pdu
        response += struct.pack("<H", crc16(response))
        self._send(response)

    def _send(self, data):
        if self.ctrl_pin is not None:
            self.ctrl_pin.value(1)
        self.uart.write(data)
        if hasattr(self.uart, "flush"):
            self.uart.flush()
        if self.ctrl_pin is not None:
            self.ctrl_pin.value(0)