#! /usr/bin/env python3

"""

 dpdk_telemetry_auto_csv.py

 This is a Python3 tool for automatically collecting statistics from the DPDK
    JSON API and collating these stats into a CSV file

 Copyright (c) 2022 Conor Walsh
 This tool is licensed under an MIT license (see included license file)

 This tool was based on the dpdk-telemetry.py and as per it's original
    BSD-3 license the original copyright and license are maintained below
 ---------------------------------------
  SPDX-License-Identifier: BSD-3-Clause
  Copyright(c) 2020 Intel Corporation
 ---------------------------------------

"""


import argparse
import glob
import json
import os
import socket
import time


# global vars
TELEMETRY_VERSION = 'v2'
METRICS = ['tx_good_packets', 'tx_good_bytes', 'rx_errors', 'tx_errors',
           'rx_dropped_packets', 'tx_size_64_packets',
           'tx_size_65_to_127_packets', 'tx_size_128_to_255_packets',
           'tx_size_256_to_511_packets', 'tx_size_512_to_1023_packets',
           'tx_size_1024_to_1522_packets', 'tx_size_1523_to_max_packets']


def read_socket(sock, buf_len, echo=True):
    """
    Read data from socket and return it in JSON format.

    :param sock: Desired telemtery socket object.
    :param buf_len: The length of the telemetry buffer.
    :param echo: If the data is to be printed or not, default=True.
    :return: The JSON data that was returned from the telemetry socket.
    """
    reply = sock.recv(buf_len).decode()
    try:
        ret = json.loads(reply)
    except json.JSONDecodeError:
        print('Error in reply:', reply)
        sock.close()
        raise
    if echo:
        print(json.dumps(ret))
    return ret


def handle_socket(sock_path, run_time, step_time, port, csv_path):
    """
    Connect to socket and handle user input.

    :param sock_path: The path to the desired telemetry socket.
    :param run_time: The length of time to run the test for.
    :param step_time: The time between measurements.
    :param port: The desired port.
    :param csv_path: The path of the csv to store the data.
    :return: This function has no return value.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        sock.connect(sock_path)
    except OSError:
        print(f'Error connecting to {sock_path}')
        sock.close()
        return
    json_reply = read_socket(sock, 1024)
    output_buf_len = json_reply['max_output_len']

    # Run stats collection every step size until test over
    current_time = 0
    while current_time <= run_time:
        sock.send(f'/ethdev/xstats,{port}'.encode())
        data = read_socket(sock, output_buf_len, False)
        csv_file = open(csv_path, 'a+')
        csv_file.write(f'{current_time},')
        for metric in METRICS:
            data1 = data['/ethdev/xstats'][metric]
            csv_file.write(f'{data1},')
        csv_file.write('\n')
        csv_file.close()
        time.sleep(step_time)
        current_time += step_time
    sock.close()


def args_parse():
    """
    Function to parse the arguments passed to the script.

    :param: This function takes no arguments.
    :return: The arguments object with all the inputted arguments.
    """
    parser = argparse.ArgumentParser(
        description=('This is a Python3 tool for automatically collecting '
                     'statistics from the DPDK JSON API and collating these '
                     'stats into a CSV file.'),
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-r', '--run-time', type=float, dest='run_time',
                        help='Set the run time for the test, default: 10.0',
                        default=10.0)
    parser.add_argument('-s', '--step-time', type=float, dest='step_time',
                        help='Set the step time for the test (values '
                             'collected every X seconds) default: 0.25',
                        default=0.25)
    parser.add_argument('-c', '--csv', type=str, dest='csv_path',
                        help='Set the path of the CSV file, default: '
                             '\'tmp/telemetry.csv\'',
                        default='tmp/telemetry.csv')
    parser.add_argument('-p', '--port', type=int, dest='port',
                        help='The port to get the stats from',
                        default=0)
    return parser.parse_args()


def main():
    """
    Main function for the script.

    :param: This function takes no arguments.
    :return: This function has no return value.
    """

    args = args_parse()

    print(f'CSV Path: {args.csv_path}')
    print(f'Test length: {args.run_time} seconds')
    print(f'Test step size: {args.step_time} seconds')
    print(f'Port: {args.port}')

    # Create directory if it doesn't exist
    if not os.path.exists('tmp'):
        os.makedirs('tmp')

    # Delete file if already exists
    if os.path.exists(args.csv_path):
        os.remove(args.csv_path)

    # Setup CSV header row
    csv_file = open(args.csv_path, 'w')
    csv_file.write('time,')
    for metric in METRICS:
        csv_file.write(f'{metric},')
    csv_file.write('\n')
    csv_file.close()

    # Path to sockets for processes run as a root user
    for root_sock in glob.glob('/var/run/dpdk/*/dpdk_telemetry.'
                               f'{TELEMETRY_VERSION}'):
        handle_socket(root_sock, args.run_time, args.step_time, args.port,
                      args.csv_path)
    # Path to sockets for processes run as a regular user
    for unp_sock in glob.glob(f'{os.environ.get("XDG_RUNTIME_DIR", "/tmp")}/'
                              f'dpdk/*/dpdk_telemetry.{TELEMETRY_VERSION}'):
        handle_socket(unp_sock, args.run_time, args.step_time, args.port,
                      args.csv_path)


if __name__ == '__main__':
    main()
