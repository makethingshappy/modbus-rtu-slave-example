"""
PC Modbus RTU master for the IoTextra Octal2 slave (main_octal2.py).

Author: Arshia Keshvari
Role: Independent Developer, Engineer, and Project Author
Last Updated: 2026-10-25

Walks coils 0..3 so each physical output turns on, then off.
Then watches discrete inputs 0..3 so a real input change shows up.

Map (zero-based), matching main_octal2.py:
    coil 0..3 -> DO channels 4..7 (LED 1..LED 4)
    discrete input 0..3 -> DI channels 0..3 (Input A..Input D)

Run from the repo, with the board slave already up and the baud matching:
    python octal2/octal2_master.py
    python octal2/octal2_master.py --inputs-only
    python octal2/octal2_master.py --port /dev/cu.usbserial-BH00LLRL --baud 9600

Requires pymodbus and pyserial (see requirements.txt).
"""

import argparse
import time

from pymodbus.client import ModbusSerialClient

PORT = "/dev/cu.usbserial-BH00LLRL"
BAUDRATE = 115200
SLAVE = 1
TIMEOUT = 2

COILS = (
    (0, 4, "LED 1"),
    (1, 5, "LED 2"),
    (2, 6, "LED 3"),
    (3, 7, "LED 4"),
)
DISCRETE_INPUTS = (
    (0, 0, "Input A"),
    (1, 1, "Input B"),
    (2, 2, "Input C"),
    (3, 3, "Input D"),
)


def bits(response, count):
    if response.isError():
        raise RuntimeError("Modbus error: %r" % (response,))
    return [int(bit) for bit in response.bits[:count]]


def read_coils(client):
    response = client.read_coils(address=0, count=len(COILS), device_id=SLAVE)
    return bits(response, len(COILS))


def read_inputs(client):
    response = client.read_discrete_inputs(
        address=0, count=len(DISCRETE_INPUTS), device_id=SLAVE
    )
    return bits(response, len(DISCRETE_INPUTS))


def write_coil(client, address, value):
    response = client.write_coil(address=address, value=bool(value), device_id=SLAVE)
    if response.isError():
        raise RuntimeError("Coil write failed: %r" % (response,))


def format_inputs(states):
    parts = []
    for (address, channel, name), state in zip(DISCRETE_INPUTS, states):
        parts.append("%s (DI %s, addr %s)=%s" % (name, channel, address, state))
    return "  ".join(parts)


def all_outputs_off(client):
    for address, _channel, _name in COILS:
        write_coil(client, address, False)


def test_outputs(client, hold_s):
    print("Outputs: each coil ON, then OFF. Watch the Octal2 LEDs.")
    for address, channel, name in COILS:
        write_coil(client, address, True)
        time.sleep(hold_s)
        states = read_coils(client)
        print(
            "  coil %s ON  -> %s (DO channel %s)  coils=%s"
            % (address, name, channel, states)
        )
        if states[address] != 1:
            raise RuntimeError("Coil %s did not read back ON: %s" % (address, states))
        write_coil(client, address, False)
        time.sleep(0.2)
        states = read_coils(client)
        print(
            "  coil %s OFF -> %s (DO channel %s)  coils=%s"
            % (address, name, channel, states)
        )
        if states[address] != 0:
            raise RuntimeError("Coil %s did not read back OFF: %s" % (address, states))
    print("Outputs off.")


def watch_inputs(client, seconds, interval):
    print("Inputs: change a physical DI. Watching for %.0f s." % seconds)
    previous = read_inputs(client)
    print("  now ", format_inputs(previous))
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(interval)
        states = read_inputs(client)
        if states != previous:
            print("  change", format_inputs(states))
            previous = states
    print("  end ", format_inputs(previous))


def main():
    parser = argparse.ArgumentParser(description="Octal2 Modbus RTU master")
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--baud", type=int, default=BAUDRATE)
    parser.add_argument("--inputs-only", action="store_true")
    parser.add_argument("--hold", type=float, default=0.6, help="seconds each output stays ON")
    parser.add_argument("--watch", type=float, default=20, help="seconds to watch inputs")
    parser.add_argument("--interval", type=float, default=0.2, help="input poll period")
    args = parser.parse_args()

    client = ModbusSerialClient(
        port=args.port,
        baudrate=args.baud,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=TIMEOUT,
        retries=3,
    )
    if not client.connect():
        raise RuntimeError("Could not open %s" % args.port)

    print("Octal2 master  %s  %s 8N1  slave %s" % (args.port, args.baud, SLAVE))
    try:
        print("Discrete inputs:", format_inputs(read_inputs(client)))
        if not args.inputs_only:
            test_outputs(client, args.hold)
        if args.watch > 0:
            watch_inputs(client, args.watch, args.interval)
    finally:
        try:
            all_outputs_off(client)
        except Exception as exc:
            print("Could not force outputs off:", exc)
        client.close()


if __name__ == "__main__":
    main()
