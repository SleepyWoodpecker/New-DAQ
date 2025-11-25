import atexit
import io
import queue
import socket
import struct
import sys
import threading
import traceback

from serial import Serial

from util import getTime, read_serial, setup, sync

PORT_HV = (
    "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_B4:3A:45:B3:70:B0-if00"
)
PORT_LV = (
    "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_B4:3A:45:B6:7E:D0-if00"
)
# LOG_RAW_FILE = f"/home/ares_gs/synnax_node/scripts/logs/pt_2_data_raw_grafana.csv"
# LOG_CAL_FILE = f"/home/ares_gs/synnax_node/scripts/logs/pt_2_data_cal_grafana.csv"

LOG_RAW_FILE = f"./logs/pt_2_data_raw_grafana.csv"
LOG_CAL_FILE = f"./logs/pt_2_data_cal_grafana.csv"

BAUDRATE = 460800
EXPECTED_PACKET_LENGTH = 40 + 2

NUM_SENSORS_HV = 8  # HV system (8 sensors)
NUM_SENSORS_LV = 8  # LV system (8 sensors)
NUM_SENSORS_TOTAL = NUM_SENSORS_HV + NUM_SENSORS_LV

DATA_CHANNELS = [f"pt{i}" for i in range(NUM_SENSORS_TOTAL)]
UDP_ADDRESS_PORT = ("127.0.0.1", 4020)
MEASUREMENT = "pressurevals"

DATA_RATE = int(500)  # Rate that data is sent to the Raspberry Pi (Hz)
GRAFANA_RATE_DIVISOR = int(DATA_RATE / 5)  # Stream to Grafana at 5 Hz

# calibration coefficients
a = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
b = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


# set up the thread queues
hv_queue = queue.Queue(maxsize=20)
lv_queue = queue.Queue(maxsize=20)

# global event for checking if something is set
stop_event = threading.Event()
global_start = getTime()


def decode_fn(line: bytes) -> list[float | int]:
    """Return data in format 8 floats, board timestamp, packet number"""
    return list(struct.unpack("8f2I", line))


def reader(serial_port: Serial, queue: queue.Queue) -> None:
    sync(serial_port=serial_port)
    while not stop_event.is_set():
        data = read_serial(
            serial_port=serial_port, expected_packet_length=EXPECTED_PACKET_LENGTH
        )
        queue.put(data)


def process_readings(
    log_raw: io.TextIOWrapper, log_cal: io.TextIOWrapper, udp_connection: socket.socket
) -> None:
    board_start_time = None
    prev_time = getTime()

    while not stop_event.is_set():
        try:
            hv_line = hv_queue.get(block=True, timeout=None)
            hv_queue.task_done()

            lv_line = lv_queue.get(block=True, timeout=None)
            lv_queue.task_done()

            decoded_hv = decode_fn(hv_line)
            decoded_lv = decode_fn(lv_line)

            largest_time = max(decoded_hv[-2], decoded_lv[-2])

            combined_readings = decoded_hv[:-2] + decoded_lv[:-2]

            if not board_start_time:
                board_start_time = largest_time

            log_raw.write(
                f"""{global_start + largest_time - board_start_time},{",".join([f"{val:.2f}" for val in combined_readings])},{decoded_hv[-2]},{decoded_hv[-1]},{decoded_lv[-2]},{decoded_lv[-1]}\n"""
            )

            calibrated_data = [
                a[i] * combined_readings[i] + b[i] for i in range(NUM_SENSORS_TOTAL)
            ]
            log_cal.write(
                f"""{global_start + largest_time - board_start_time},{",".join([f"{val:.2f}" for val in calibrated_data])},{decoded_hv[-2]},{decoded_hv[-1]},{decoded_lv[-2]},{decoded_lv[-1]}\n"""
            )

            curr_time = getTime()

            if curr_time - prev_time >= GRAFANA_RATE_DIVISOR:
                prev_time = curr_time

                fields = ",".join(
                    [
                        f"""{key}={val:.2f}"""
                        for key, val in zip(DATA_CHANNELS, calibrated_data)
                    ]
                )
                # create influx string -- timestamp it with inaccurate timestamp so that grafana can display it properly
                # here, the priority is to display the value, rather than provide a time accurate dispay
                influx_string = f"""{MEASUREMENT} {fields} {curr_time * 1000000}"""
                udp_connection.sendto(influx_string.encode(), UDP_ADDRESS_PORT)

                # print out this debug string at the same time
                logger.info(influx_string)
        except Exception as e:
            trace_dump = traceback.format_exc()
            logger.warning(
                f"""[LC Processing] encountered an error: {str(e)} | {trace_dump}"""
            )
            pass


if __name__ == "__main__":
    global logger

    setup_dict = setup(
        serial_port_names=[PORT_HV, PORT_LV],
        baudrate=BAUDRATE,
        timeout=0.05,
        log_raw_name=LOG_RAW_FILE,
        log_cal_name=LOG_CAL_FILE,
        reading_type="PTs",
    )
    atexit.register(setup_dict["cleanup_function"])

    hv_reader_thread = threading.Thread(
        target=reader, name="HV Reader", args=(setup_dict["serials"][0], hv_queue)
    )
    lv_reader_thread = threading.Thread(
        target=reader, name="LV Reader", args=(setup_dict["serials"][1], lv_queue)
    )
    processing_thread = threading.Thread(
        target=process_readings,
        name="Process PT Readings",
        args=(
            setup_dict["log_raw_file"],
            setup_dict["log_cal_file"],
            setup_dict["udp_socket"],
        ),
    )

    hv_reader_thread.start()
    lv_reader_thread.start()
    processing_thread.start()

    logger = setup_dict["logger"]

    try:
        stop_event.wait()
    except KeyboardInterrupt:
        stop_event.set()

    hv_reader_thread.join(timeout=2)
    lv_reader_thread.join(timeout=2)
    processing_thread.join(timeout=2)

    sys.exit(0)
