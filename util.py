# utility functions which would be used by all other modules
# each module should import these functions and spawn the necessary threads
import io
import logging
import os
import socket
import sys
import time
from typing import Callable, TypedDict

from serial import Serial

STOP_SEQUENCE = b"\r\n"


class SetupReturn(TypedDict):
    serials: list[Serial]
    log_raw_file: io.TextIOWrapper | None
    log_cal_file: io.TextIOWrapper | None
    cleanup_function: Callable[[], None]
    udp_socket: socket.socket
    logger: logging.Logger


######################
#### LOGGER SETUP ####
######################
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def setup(
    serial_port_names: list[str],
    baudrate: int,
    timeout: float,
    log_raw_name: str | None,
    log_cal_name: str | None,
    reading_type: str,
) -> SetupReturn:
    """
    Main setup function for all utilities.
    """
    global READING_TYPE
    READING_TYPE = reading_type

    ###########################
    #### SETUP SERIAL PORT ######
    ###########################
    serial_ports = []
    while True:
        try:
            time.sleep(1)
            serial_ports = [
                Serial(serial_port_name, baudrate, timeout=timeout)
                for serial_port_name in serial_port_names
            ]
        except KeyboardInterrupt:
            logging.info("Caught KeyboardInterrupt! Exiting...")
            sys.exit(1)
        except:
            logging.info(f"Failure to bind serial port: {serial_port_names}")
            # if re-attempting connection, close all serial ports
            for port in serial_ports:
                if isinstance(port, Serial):
                    port.close()

        else:
            break

    ###########################
    #### CREATE LOGS DIR ######
    ###########################
    # Extract directory paths from log file paths
    log_raw = None
    log_cal = None
    if log_raw_name:
        log_dir_raw = os.path.dirname(log_raw_name)
        os.makedirs(log_dir_raw, exist_ok=True)
        log_raw = open(log_raw_name, "a")
    if log_cal_name:
        log_dir_cal = os.path.dirname(log_cal_name)
        os.makedirs(log_dir_cal, exist_ok=True)
        log_cal = open(log_cal_name, "a")

    ##########################
    #### RESOURCE CLEANUP ####
    ##########################
    def cleanup():
        for serial_port in serial_ports:
            if serial_port and serial_port.is_open:
                logging.info(
                    f"Closing serial port {serial_port.name} for {reading_type}..."
                )
                serial_port.close()
        if log_raw:
            logging.info(f"Closing raw log file for {reading_type} ...")
            log_raw.flush()
            log_raw.close()
        if log_cal:
            logging.info(f"Closing calibrated log file for {reading_type}...")
            log_cal.flush()
            log_cal.close()

    udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

    for serial_port in serial_ports:
        serial_port.reset_input_buffer()

    return {
        "serials": serial_ports,
        "log_raw_file": log_raw,
        "log_cal_file": log_cal,
        "cleanup_function": cleanup,
        "udp_socket": udp_socket,
        "logger": logging.getLogger(),
    }


def sync(serial_port: Serial) -> None:
    """Reads till the control character \r\n is found"""
    # may want to only make this call to reset the buffer when we start the program so we don't lose too much data
    serial_port.reset_input_buffer()
    serial_port.read_until(STOP_SEQUENCE)


def read_serial(serial_port: Serial, expected_packet_length: int) -> bytes | None:
    line = b""
    try:
        while (l := len(line)) < expected_packet_length:
            line += serial_port.read(expected_packet_length - l)

            if not line.endswith(STOP_SEQUENCE):
                print(f"""[Reader {READING_TYPE}] End sequence wrong {line[:-2]}""")
                sync(serial_port)
                continue

        line = line.removesuffix(STOP_SEQUENCE)
        return line
    except Exception as e:
        print(f"""[Reader {READING_TYPE}] {str(e)}""")
        sync(serial_port)


def getTime():
    return int(time.time_ns() / 1000000)  # time in ms
