import atexit
import io
import queue
import socket
import struct
import sys
import threading
import traceback

from serial import Serial

from util import getTime, read_serial, setup

##########################
#### CONFIGURATIONS ######
##########################
PORT = "/dev/cu.usbmodem2101"
BAUDRATE = 115200
NUM_SENSORS = 13  # Number of thermocouples (1 to 15)

DATA_CHANNELS = [
    f"tc{i+1}" for i in range(NUM_SENSORS)
]  # Naming thermocouples as tc0, tc1, etc.
EXPECTED_PACKET_LENGTH = 42

LOG_FILE = "./tc_data_grafana.csv"  # CSV log file for local logging
UDP_ADDRESS_PORT = ("127.0.0.1", 40113)  # Grafana UDP server address and port
MEASUREMENT = "temperaturevals"  # Measurement name for Grafana

DATA_RATE = int(50)  # Rate that data is sent to the Raspberry Pi (Hz)
GRAFANA_RATE_DIVISOR = int(DATA_RATE / 10)  # Stream to Grafana at 10 Hz

tc_queue = queue.Queue(maxsize=20)

stop_event = threading.Event()
global_start = getTime()
prev_time = global_start


def decode_fn(line: bytes) -> list[float | int]:
    return list(struct.unpack("13d2I", line))


def reader(serial: Serial, queue: queue.Queue) -> None:
    while not stop_event.is_set():
        data = read_serial(
            serial_port=serial, expected_packet_length=EXPECTED_PACKET_LENGTH
        )
        queue.put(data)


def process_readings(log_cal: io.TextIOWrapper, udp_connection: socket.socket) -> None:
    board_start_time = None
    while not stop_event.is_set():
        try:
            tc_line = tc_queue.get(block=True, timeout=None)
            tc_queue.task_done()

            decoded_tc = decode_fn(tc_line)

            if not board_start_time:
                board_start_time = decoded_tc[-2]

            calibrated_data = decoded_tc[:-2]
            log_cal.write(
                f"""{global_start + decoded_tc[-2] - board_start_time},{",".join([f"{val:.2f}" for val in calibrated_data])},{decoded_tc[-2]},{decoded_tc[-1]}\n"""
            )

            curr_time = getTime()

            if curr_time - prev_time >= GRAFANA_RATE_DIVISOR:  # type: ignore
                prev_time = curr_time

                # Prepare data for Grafana UDP
                fields = ",".join(
                    [
                        f"""{key}={val:.2f}"""
                        for key, val in zip(DATA_CHANNELS, calibrated_data)
                    ]
                )

                # Create InfluxDB line protocol string
                influx_string = f"{MEASUREMENT} {fields} {int(curr_time) * 1000000}"
                # create influx string -- timestamp it with inaccurate timestamp so that grafana can display it properly
                # here, the priority is to display the value, rather than provide a time accurate dispay
                udp_connection.sendto(influx_string.encode(), UDP_ADDRESS_PORT)

                # print out this debug string at the same time
                logger.debug(influx_string)
        except Exception as e:
            trace_dump = traceback.format_exc()
            logger.warning(
                f"""[LC Processing] encountered an error: {str(e)} | {trace_dump}"""
            )
            pass


if __name__ == "__main__":
    global logger

    setup_dict = setup(
        serial_port_names=[PORT],
        baudrate=BAUDRATE,
        timeout=0.2,
        log_raw_name=None,
        log_cal_name=LOG_FILE,
        reading_type="PTs",
    )
    atexit.register(setup_dict["cleanup_function"])

    tc_reader_thread = threading.Thread(
        target=reader, name="TC Readr", args=(setup_dict["serials"][0], tc_queue)
    )
    processing_thread = threading.Thread(
        target=process_readings,
        name="Process TC reading",
        args=(setup_dict["log_cal_file"], setup_dict["udp_socket"]),
    )

    tc_reader_thread.start()
    processing_thread.start()

    logger = setup_dict["logger"]

    try:
        stop_event.wait()
    except KeyboardInterrupt:
        stop_event.set()

    tc_reader_thread.join(timeout=2)
    processing_thread.join(timeout=2)

    sys.exit(0)
