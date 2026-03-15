import argparse
import logging
import socket
import threading
import time

import serial
from serial.tools import list_ports

DEFAULT_BAUD = 576000
DEFAULT_PORT = 5000
DEFAULT_VID = 0x0483
DEFAULT_PID = 0x5740


def find_device(vid, pid):
    for port in list_ports.comports():
        if port.vid == vid and port.pid == pid:
            return port.device
    return None


def open_serial(device, baud):
    return serial.Serial(device, baudrate=baud, timeout=0.1)


def bridge(conn, addr, ser):
    stop_event = threading.Event()

    def socket_to_serial():
        try:
            while not stop_event.is_set():
                data = conn.recv(4096)
                if not data:
                    break
                ser.write(data)
        except OSError:
            pass
        finally:
            stop_event.set()

    def serial_to_socket():
        try:
            while not stop_event.is_set():
                waiting = ser.in_waiting
                data = ser.read(waiting or 1)
                if data:
                    conn.sendall(data)
        except OSError:
            pass
        finally:
            stop_event.set()

    t1 = threading.Thread(target=socket_to_serial, daemon=True)
    t2 = threading.Thread(target=serial_to_socket, daemon=True)
    t1.start()
    t2.start()
    while not stop_event.is_set():
        time.sleep(0.1)
    try:
        conn.close()
    except OSError:
        pass
    logging.info("client %s disconnected", addr)


def run_server(host, port, device, baud, vid, pid):
    if not device:
        device = find_device(vid, pid)
        if not device:
            raise SystemExit(f"TinySA not found (VID=0x{vid:04x}, PID=0x{pid:04x}).")

    ser = open_serial(device, baud)
    logging.info("serial connected: %s @ %d", device, baud)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(1)
        logging.info("listening on %s:%d", host, port)

        while True:
            conn, addr = srv.accept()
            logging.info("client connected: %s", addr)
            bridge(conn, addr, ser)



def main():
    parser = argparse.ArgumentParser(description="TinySA TCP bridge server")
    parser.add_argument("--host", default="0.0.0.0", help="listen address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="listen port")
    parser.add_argument("--device", help="serial device path (optional)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="serial baud rate")
    parser.add_argument("--vid", type=lambda v: int(v, 0), default=DEFAULT_VID, help="USB VID (hex or int)")
    parser.add_argument("--pid", type=lambda v: int(v, 0), default=DEFAULT_PID, help="USB PID (hex or int)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_server(args.host, args.port, args.device, args.baud, args.vid, args.pid)


if __name__ == "__main__":
    main()