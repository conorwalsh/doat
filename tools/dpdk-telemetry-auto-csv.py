#! /usr/bin/env python3

"""

 dpdk-telemetry-auto-csv.py

 This is a Python3 tool for automatically collecting statistics from the DPDK JSON
    API and collating these stats into a CSV file

 Usage: ./dpdk-telemetry-auto-csv.py csv_path test_length step_size

 Copyright (c) 2021 Conor Walsh
 This tool is licensed under an MIT license (see included license file)

 This tool was based on the dpdk-telemetry.py and as per it's original
    BSD-3 licence the original copyright and licence are maintained below
 ---------------------------------------
  SPDX-License-Identifier: BSD-3-Clause
  Copyright(c) 2020 Intel Corporation
 ---------------------------------------

"""

import sys
import socket
import os
import glob
import json
import time

# global vars
TELEMETRY_VERSION = "v2"
DEFAULT_RT = 10.0
DEFAULT_ST = 0.25
DEFAULT_CSV = "tmp/telemetry.csv"
DEFAULT_PORT = 0
METRICS = ["tx_good_packets", "tx_good_bytes", "rx_errors", "tx_errors",
           "rx_dropped_packets", "tx_size_64_packets", "tx_size_65_to_127_packets",
           "tx_size_128_to_255_packets", "tx_size_256_to_511_packets",
           "tx_size_512_to_1023_packets", "tx_size_1024_to_1522_packets",
	   "tx_size_1523_to_max_packets"]


def read_socket(sock, buf_len, echo=True):
    """ Read data from socket and return it in JSON format """
    reply = sock.recv(buf_len).decode()
    try:
        ret = json.loads(reply)
    except json.JSONDecodeError:
        print("Error in reply: ", reply)
        sock.close()
        raise
    if echo:
        print(json.dumps(ret))
    return ret


def handle_socket(path):
    """ Connect to socket and handle user input """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        sock.connect(path)
    except OSError:
        print("Error connecting to " + path)
        sock.close()
        return
    json_reply = read_socket(sock, 1024)
    output_buf_len = json_reply["max_output_len"]

    # Run stats collection every step size until test over
    currenttime = 0
    while currenttime <= run_time:
        sock.send("/ethdev/xstats,{}".format(port).encode())
        data = read_socket(sock, output_buf_len, False)
        f = open(csv_path, 'a+')
        f.write(str(currenttime) + ',')
        for metric in METRICS:
            data1 = data['/ethdev/xstats'][metric]
            f.write(str(data1) + ',')
        f.write('\n')
        f.close()
        time.sleep(sleep_time)
        currenttime += sleep_time
    sock.close()


def main():
    global run_time
    global sleep_time
    global csv_path
    global port

    run_time = DEFAULT_RT
    sleep_time = DEFAULT_ST
    csv_path = DEFAULT_CSV
    port = DEFAULT_PORT
    if len(sys.argv) == 5:
        csv_path = sys.argv[1]
        run_time = float(sys.argv[2])
        sleep_time = float(sys.argv[3])
        port = int(sys.argv[4])
    else:
        print("Warning the correct arguments were not passed running using defaults")
        print("To set these values use the format ./script.py csv_path test_length step_size port")
        print("CSV Path: " + csv_path)
        print("Test length: " + str(run_time) + " seconds")
        print("Test step size: " + str(sleep_time) + " seconds")
        print("Port: " + str(port))

    # Create directory if it doesn't exist
    if not os.path.exists("tmp"):
        os.makedirs('tmp')

    # Delete file if already exists
    if os.path.exists(csv_path):
        os.remove(csv_path)

    # Setup CSV header row
    f = open(csv_path, 'w')
    f.write('time,')
    for metric in METRICS:
        f.write(metric + ',')
    f.write('\n')
    f.close()

    # Path to sockets for processes run as a root user
    for f in glob.glob('/var/run/dpdk/*/dpdk_telemetry.%s' % TELEMETRY_VERSION):
        handle_socket(f)
    # Path to sockets for processes run as a regular user
    for f in glob.glob('%s/dpdk/*/dpdk_telemetry.%s' %
                       (os.environ.get('XDG_RUNTIME_DIR', '/tmp'), TELEMETRY_VERSION)):
        handle_socket(f)


if __name__ == "__main__":
    main()
