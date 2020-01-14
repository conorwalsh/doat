#! /usr/bin/env python

"""

 dpdk-telemetry-auto-csv.py

 This is a tool for automatically collecting statistics from the DPDK JSON
    API and collating these stats into a CSV file

 Copyright (c) 2020 Conor Walsh
 This tool is licensed under an MIT license (see included license file)

 This tool was based on the dpdk-telemetry-client.py and as per it's original
    BSD-3 licence the original copyright and licence are maintained below
 ---------------------------------------
  SPDK-License-Identifier: BSD-3-Clause
  Copyright(c) 2018 Intel Corporation
 ---------------------------------------

"""

# Import required modules and libraries
import socket
import os
import sys
import time
import json
from collections import OrderedDict

# How much info to receive from socket in one go
BUFFER_SIZE = 200000

# JSON API Commands
METRICS_REQ = "{\"action\":0,\"command\":\"ports_all_stat_values\",\"data\":null}"
API_REG = "{\"action\":1,\"command\":\"clients\",\"data\":{\"client_path\":\""
API_UNREG = "{\"action\":2,\"command\":\"clients\",\"data\":{\"client_path\":\""

# Program default values
DEFAULT_FP = "/var/run/dpdk/default_client"
DEFAULT_RT = 10.0
DEFAULT_ST = 0.25
DEFAULT_CSV = "tmp/telemetry.csv"

# Ordered dictionary containing all data points required and there key for the JSON file
OBJECTITEMS = OrderedDict()
OBJECTITEMS["tx_good_packets"] = 1
OBJECTITEMS["tx_good_bytes"] = 3
OBJECTITEMS["tx_errors"] = 6
OBJECTITEMS["tx_dropped"] = 21
OBJECTITEMS["tx_size_64_packets"] = 45
OBJECTITEMS["tx_size_65_to_127_packets"] = 46
OBJECTITEMS["tx_size_128_to_255_packets"] = 47
OBJECTITEMS["tx_size_256_to_511_packets"] = 48
OBJECTITEMS["tx_size_512_to_1023_packets"] = 49
OBJECTITEMS["tx_size_1024_to_1522_packets"] = 50
OBJECTITEMS["tx_size_1523_to_max_packets"] = 51


# Class to setup and teardown the socket connection
class Socket:

    def __init__(self):
        self.send_fd = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.recv_fd = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.client_fd = None

    def __del__(self):
        try:
            self.send_fd.close()
            self.recv_fd.close()
            self.client_fd.close()
        except:
            print("Error - Sockets could not be closed")


# Class to run the client
class Client:

    # Initialise a client instance
    def __init__(self):
        self.socket = Socket()
        self.file_path = None
        self.choice = None
        self.unregistered = 0

    # Delete client instance
    def __del__(self):
        try:
            if self.unregistered == 0:
                self.unregister()
        except:
            print("Error - Client could not be destroyed")

    # Setup filepath to socket specified elsewhere (see main)
    def getFilepath(self, file_path):
        self.file_path = file_path

    # Register the client and connect to the DPDK app
    def register(self):
        if os.path.exists(self.file_path):
            os.unlink(self.file_path)
        try:
            self.socket.recv_fd.bind(self.file_path)
        except socket.error as msg:
            print ("Error - Socket binding error: " + str(msg) + "\n")
        self.socket.recv_fd.settimeout(2)
        self.socket.send_fd.connect("/var/run/dpdk/rte/telemetry")
        JSON = (API_REG + self.file_path + "\"}}")
        self.socket.send_fd.sendall(JSON)
        self.socket.recv_fd.listen(1)
        self.socket.client_fd = self.socket.recv_fd.accept()[0]

    # Unregister and disconnect a client
    def unregister(self):
        self.socket.client_fd.send(API_UNREG + self.file_path + "\"}}")
        self.socket.client_fd.close()

    # Function to control the automatic collection of results
    def autoRun(self, sleep_time, run_time, csv_path):
        # Run stats collection every step size until test over
        currenttime = 0
        while currenttime <= run_time:
            self.saveMetrics(currenttime, csv_path)
            time.sleep(sleep_time)
            currenttime += sleep_time
        # Unregister and disconnect client when finished
        self.unregister()
        self.unregistered = 1

    # Function to request the needed metrics and save them to csv
    def saveMetrics(self, currenttime, csv_path):
        self.socket.client_fd.send(METRICS_REQ)
        data = self.socket.client_fd.recv(BUFFER_SIZE)
        jdata = json.loads(data)
        f = open(csv_path, 'a+')
        f.write(str(currenttime)+',')
        for oitem in OBJECTITEMS.values():
            jdata1 = jdata['data'][0]['stats'][oitem]['value']
            f.write(str(jdata1) + ',')
        f.write('\n')
        f.close()


# Main Method
if __name__ == "__main__":

    # Get command args if available
    sleep_time = DEFAULT_ST
    run_time = DEFAULT_RT
    file_path = DEFAULT_FP
    if len(sys.argv) == 4:
        file_path = sys.argv[1]
        run_time = float(sys.argv[2])
        sleep_time = float(sys.argv[3])
    else:
        print("Warning the correct arguments were not passed running using defaults")
        print("To set these values use the format ./script.py socket_path test_length step_size")
        print("Socket Path: " + file_path)
        print("Test length: " + str(run_time) + " seconds")
        print("Test step size: " + str(sleep_time) + " seconds")

    # Set the path for the csv
    csv_path = DEFAULT_CSV

    # Create directory if it doesnt exist
    if not os.path.exists("tmp"):
        os.makedirs('tmp')

    # Delete file if already exists
    if os.path.exists(csv_path):
        os.remove(csv_path)

    # Setup CSV header row
    f = open(csv_path, 'w')
    f.write('time,')
    for key in OBJECTITEMS.keys():
          f.write(key + ',')
    f.write('\n')
    f.close()

    # Create new client
    client = Client()
    # Set file path
    client.getFilepath(file_path)
    # Register and connect client
    client.register()
    # Run stats collection using parameters
    client.autoRun(sleep_time, run_time, csv_path)
