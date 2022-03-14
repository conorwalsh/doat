#!/usr/bin/env python3

"""

 main.py

 DOAT Version: v22.03

 This is the main file for the DOAT platform.
 The DPDK Optimisation and Analysis Tool (DOAT) is an out-of-band tool
    for analysing and optimising DPDK applications.

 Usage:
    1) Setup DOAT by editing the config.cfg file in this directory
    2) Run ./main.py

 Copyright (c) 2022 Conor Walsh
 DOAT is licensed under an MIT license (see included license file)

"""

# Import standard modules.
import atexit
import fileinput
from http.server import SimpleHTTPRequestHandler, HTTPServer
import os
import subprocess
import sys
import time
from time import gmtime, strftime

# Import third-party modules.
try:
    from json2html import json2html
    JSON2HTML_AVAILABLE = True
except ImportError:
    JSON2HTML_AVAILABLE = False
    print('The python module \'json2html\' must be installed to show the DOAT,'
          'configuartion in the report, this has been disabled for now.\n'
          'It can be installed using pip or the supplied requirements.txt')
try:
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit('The python module \'matplotlib\' must be installed to use DOAT.'
             '\nInstall it using pip or the supplied requirements.txt')
try:
    import numpy as np
except ImportError:
    sys.exit('The python module \'numpy\' must be installed to use DOAT.\n'
             'Install it using pip or the supplied requirements.txt')
try:
    import pandas
except ImportError:
    sys.exit('The python module \'pandas\' must be installed to use DOAT.\n'
             'Install it using pip or the supplied requirements.txt')
try:
    import pdfkit
    PDFKIT_AVAILABLE = True
except ImportError:
    PDFKIT_AVAILABLE = False
    print('The python module \'pdfkit\' must be installed to generate PDFs,'
          'PDF generation has been disabled. It can be installed by '
          'installing the wkhtmltopdf package and then install the python '
          'module using pip or the supplied requirements.txt')

# Import custom modules.
from doat_functions import (check_pid, doat_config, doat_motd, kill_group_pid,
                            progress_bar, safe_exit)


def main():
    """
    Main function for the script.
    :param: This function takes no arguments.
    :return: This function has no return value.
    """
    # Print startup message.
    doat_motd()

    # DOAT takes all of its configuration options from the user using a config
    #   file (config.cfg).
    config = doat_config('config.cfg')

    # All of the test results are stored in a tmp directory while
    #   DOAT is running, create the dir if it doesn't exist.
    if not os.path.exists('tmp'):
        os.makedirs('tmp')

    # Pin DOAT to the core specified by the user.
    subprocess.call(f'taskset -cp {config["test_core"]} {os.getpid()}',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
    print('DOAT pinned to core', config['test_core'], 'PID:', os.getpid())

    # DOAT will start the first analysis of the DPDK app
    #   if no optimisation is enabled this will be the only analysis.
    if config['op_enabled']:
        print('\nStarting Analysis of Original unmodified DPDK App')
    else:
        print('\nStarting Analysis of DPDK App')

    # Spawn the DPDK app in a new process
    print('Starting DPDK App')
    dpdk_proc = subprocess.Popen(config['app_cmd'],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.STDOUT,
                                 shell=True,
                                 preexec_fn=os.setsid)
    current_test_pid = dpdk_proc.pid

    # Register the safe_exit function to run on exit.
    atexit.register(safe_exit)

    # Check that the DPDK app started.
    if check_pid(current_test_pid):
        print('DPDK App started successfully')
    # Abort if the ap died
    else:
        sys.exit('DPDK App failed to start, ABORT!')

    # Wait for the time specified by the user for the app to start and settle.
    print('Allow application to startup and settle . . .')
    progress_bar(config['startup_time'])

    # Check that the DPDK app is still alive if not abort.
    if dpdk_proc.poll() is not None:
        sys.exit('DPDK App died or failed to start, ABORT!')
    else:
        print('DPDK App ready for tests, PID:', current_test_pid)

    print('Starting Measurements . . .')

    # Spawn PCM in a new process.
    # PCM will measure cpu and platform metrics.
    pcm_proc = subprocess.Popen(f'{config["pcm_dir"]}pcm.x '
                                f'{config["test_step_size"]} -csv=tmp/pcm.csv',
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.STDOUT,
                                shell=True,
                                preexec_fn=os.setsid)

    # Spawn ipmitool in a new process.
    # IPMItool is used to measure platform power usage.
    power_proc = subprocess.Popen(
        r"echo 'power,time\n' > tmp/wallpower.csv; while true; do ipmitool sdr"
        r" | grep 'PS1 Input Power' | cut -c 20- | cut -f1 -d 'W' | tr -d '\n'"
        r" | sed 's/.$//' >> tmp/wallpower.csv; echo -n ',' >> "
        r"tmp/wallpower.csv; date +%s >> tmp/wallpower.csv; sleep "
        f"{config['test_step_size']}   ; done",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        shell=True,
        preexec_fn=os.setsid)

    # If telemetry is enabled then spawn the telemetry tool in a new process.
    # This tool uses the DPDK telemetry API to get statistics about the
    #   DPDK app.
    if config['telemetry'] is True:
        telemetry_proc = subprocess.Popen(
            './tools/dpdk_telemetry_auto_csv.py -c tmp/telemetry.csv -r '
            f'{config["test_runtime"] + 2} -s {config["test_step_size"]} '
            f'-f {config["file_prefix"]} -p {config["telemetry_port"]}',
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            shell=True,
            preexec_fn=os.setsid)

    # Wait 2 seconds for the measurement tools to startup.
    progress_bar(2)

    # Check if IMPItool is still alive after startup. Abort if not
    if power_proc.poll() is not None:
        # Kill PCM.
        kill_group_pid(pcm_proc.pid)
        # Kill DPDK app.
        kill_group_pid(dpdk_proc.pid)
        # Kill telemetry if enabled.
        if config['telemetry'] is True:
            kill_group_pid(telemetry_proc.pid)
        # Exit.
        sys.exit('IPMItool died or failed to start, ABORT!')

    # Check if PCM is still alive after startup. Abort if not.
    if pcm_proc.poll() is not None:
        # Kill IMPItool.
        kill_group_pid(power_proc.pid)
        # Kill DPDK app.
        kill_group_pid(dpdk_proc.pid)
        # Kill telemetry if enabled.
        if config['telemetry'] is True:
            kill_group_pid(telemetry_proc.pid)
        # Exit.
        sys.exit('PCM died or failed to start, ABORT! (If problem persists, '
                 'try to execute \'modprobe msr\' as root user)')

    # If telemetry enabled check if its still alive. Abort if not.
    if config['telemetry'] is True:
        if telemetry_proc.poll() is not None:
            # Kill PCM.
            kill_group_pid(pcm_proc.pid)
            # Kill IMPItool.
            kill_group_pid(power_proc.pid)
            # Kill DPDK app.
            kill_group_pid(dpdk_proc.pid)
            # Exit.
            sys.exit('Telemetry died or failed to start, ABORT!')

    # Allow test to run and collect statistics for user specified time.
    print('Running Test . . .')
    progress_bar(config['test_runtime'])

    # Check if the DPDK App is still alive after the test.
    app_died_during_test = False
    if dpdk_proc.poll() is None:
        print('SUCCESS: DPDK App is still alive after test')
    else:
        print('ERROR: DPDK App died during test')
        app_died_during_test = True

    # Kill all tools.
    print('Killing test processes')
    kill_group_pid(current_test_pid)
    kill_group_pid(pcm_proc.pid)
    kill_group_pid(power_proc.pid)
    if config['telemetry'] is True:
        kill_group_pid(telemetry_proc.pid)

    # Abort test if DPDK app died during test.
    if app_died_during_test is True:
        sys.exit('Test invalid due to DPDK App dying during test, ABORT!')

    # PCM tool exports CSVs that use semicolons instead of the standard comma.
    # Open file and replace all semicolons with commas.
    # This could have been used but its more convenient for the user.
    csv_file = open('tmp/pcm.csv', 'r')
    file_data = csv_file.read()
    csv_file.close()
    new_data = file_data.replace(';', ',')
    csv_file = open('tmp/pcm.csv', 'w')
    csv_file.write(new_data)
    csv_file.close()

    # Read the PCM CSV using pandas.
    pcm_data = pandas.read_csv('tmp/pcm.csv', low_memory=False)

    # Calculate how many datapoints are in the PCM CSV.
    pcm_datapoints = pcm_data.shape[0] * pcm_data.shape[1]

    # Extract socket memory bandwidth read and write to numpy arrays.
    socket_read = (np.asarray((pcm_data.iloc[:, pcm_data.columns.get_loc(
        f'Socket {config["app_socket"]}') + 17].tolist())[1:]).astype(float)
                   * 1000)
    socket_write = (np.asarray((pcm_data.iloc[:, pcm_data.columns.get_loc(
        f'Socket {config["app_socket"]}') + 18].tolist())[1:]).astype(float)
                    * 1000)

    # Calculate the average read and write of the memory bandwidth.
    socket_read_avg = round(sum(socket_read) / len(socket_read), 2)
    socket_write_avg = round(sum(socket_write) / len(socket_write), 2)
    # Calculate the ratio of reads to writes.
    socketwritereadratio = round(socket_write_avg / socket_read_avg, 2)

    # Declare variables to store cache info for the master core.
    l3_miss_master = 0
    l2_miss_master = 0
    l3_hit_master = 0
    l2_hit_master = 0
    l3_miss_master_avg = 0.0
    l2_miss_master_avg = 0.0
    l3_hit_master_avg = 0.0
    l2_hit_master_avg = 0.0
    # If the master core stats are enabled extract the data using pandas.
    if config["app_master_enabled"] is True:
        l3_miss_master = np.asarray((pcm_data.iloc[:, pcm_data.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 4].tolist())[1:]).astype(
                float) * 1000 * 1000
        l2_miss_master = np.asarray((pcm_data.iloc[:, pcm_data.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 5].tolist())[1:]).astype(
                float) * 1000 * 1000
        l3_hit_master = np.asarray((pcm_data.iloc[:, pcm_data.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 6].tolist())[1:]).astype(
                float) * 100
        l2_hit_master = np.asarray((pcm_data.iloc[:, pcm_data.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 7].tolist())[1:]).astype(
                float) * 100
        l3_miss_master_avg = round(
            sum(l3_miss_master) / len(l3_miss_master), 1)
        l2_miss_master_avg = round(
            sum(l2_miss_master) / len(l2_miss_master), 1)
        l3_hit_master_avg = round(sum(l3_hit_master) / len(l3_hit_master), 1)
        l2_hit_master_avg = round(sum(l2_hit_master) / len(l2_hit_master), 1)

    # Declare arrays to store cache info for cores.
    l3_miss_core = []
    l2_miss_core = []
    l3_hit_core = []
    l2_hit_core = []
    # Extract cache data for cores.
    for core in config['app_cores']:
        l3_miss_core.append(np.asarray((pcm_data.iloc[
            :, pcm_data.columns.get_loc(
                f'Core{core} (Socket {config["app_socket"]})') + 4].tolist()
                                       )[1:]).astype(float) * 1000 * 1000)
        l2_miss_core.append(np.asarray((pcm_data.iloc[
            :, pcm_data.columns.get_loc(
                f'Core{core} (Socket {config["app_socket"]})') + 5].tolist()
                                        )[1:]).astype(float) * 1000 * 1000)
        l3_hit_core.append(np.asarray((pcm_data.iloc[
            :, pcm_data.columns.get_loc(
                f'Core{core} (Socket {config["app_socket"]})') + 6].tolist()
                                       )[1:]).astype(float) * 100)
        l2_hit_core.append(np.asarray((pcm_data.iloc[
            :, pcm_data.columns.get_loc(
                f'Core{core} (Socket {config["app_socket"]})') + 7].tolist()
                                       )[1:]).astype(float) * 100)

    # Declare arrays to store average cache info for cores.
    l3_miss_core_avg = []
    l2_miss_core_avg = []
    l3_hit_core_avg = []
    l2_hit_core_avg = []
    # Calculate average cache data for cores.
    for l3_miss in l3_miss_core:
        l3_miss_core_avg.append(round(sum(l3_miss) / len(l3_miss), 1))
    for l2_miss in l2_miss_core:
        l2_miss_core_avg.append(round(sum(l2_miss) / len(l2_miss), 1))
    for l3_hit in l3_hit_core:
        l3_hit_core_avg.append(round(sum(l3_hit) / len(l3_hit), 1))
    for l2_hit in l2_hit_core:
        l2_hit_core_avg.append(round(sum(l2_hit) / len(l2_hit), 1))

    # Create a corresponding time array for the memory bandwidth arrays.
    socket_x_axis = []
    time_x = 0
    for _ in socket_read:
        socket_x_axis.append(time_x)
        time_x += config['test_step_size']

    # Generate the read and write memory bandwidth figure.
    # Each figure must have a unique number.
    plt.figure(0)
    # Plot the figure.
    plt.plot(socket_x_axis, socket_read, label='Read')
    plt.plot(socket_x_axis, socket_write, label='Write')
    # Label the x and y axis.
    plt.xlabel('Time (Seconds)')
    plt.ylabel('Bandwidth (MBps)')
    # Title the figure
    plt.title('Memory Bandwidth')
    # Enable the legend for the figure.
    plt.legend()
    # Set lower x and y limit.
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    # Set upper x and y limit.
    plt.ylim(top=(max([max(socket_read), max(socket_write)]) + 100))
    plt.xlim(right=max(socket_x_axis))
    # Save the figure in the tmp dir.
    plt.savefig('./tmp/membw.png', bbox_inches='tight')

    # Generate the memory bandwidth html code for the report.
    mem_bw_html = ('<h2>Memory Bandwidth</h2>'
                   '<img src="./tmp/membw.png" style="max-width: 650px"/>'
                   f'<p>Read Avg: {socket_read_avg}MBps</p><p>Write Avg: '
                   f'{socket_write_avg}MBps</p><p>Write to Read Ratio: '
                   f'{socketwritereadratio}</p><p><a href="./tmp/pcm.csv" '
                   'class="btn btn-info" role="button">Download Full PCM CSV'
                   '</a>')

    # Read the IPMItool CSV using pandas.
    power_data_raw = pandas.read_csv('tmp/wallpower.csv',
                                     sep=',',
                                     low_memory=False)
    # Calculate how many datapoints are in the IPMItool CSV.
    power_datapoints = power_data_raw.shape[0] * power_data_raw.shape[1]
    # Extract the power data from the CSV.
    power_data = np.asarray(power_data_raw['power'].tolist()).astype(int)
    # Extract the time data from the CSV.
    power_times = np.asarray(power_data_raw['time'].tolist()).astype(int)
    # Set the starting time for the time to 0.
    power_time_zero = power_times[0]
    power_x_axis = []
    for power_time in power_times:
        power_x_axis.append(power_time - power_time_zero)
    # Calculate the average power.
    power_avg = round(sum(power_data) / len(power_data), 1)

    # Generate the power html for the report.
    wallpowerhtml = ('<h2>Wall Power</h2>'
                     '<img src="./tmp/wallpower.png" '
                     'style="max-width: 650px"/>'
                     f'<p>Wall Power Avg: {power_avg}Watts</p>'
                     '<p><a href="./tmp/wallpower.csv" class="btn btn-info" '
                     'role="button">Download Power CSV</a>')

    # Plot and save the wall power figure.
    plt.figure(1)
    plt.plot(power_x_axis, power_data, label='Wall Power')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('Power (Watts)')
    plt.title('Wall Power')
    plt.legend()
    plt.ylim(bottom=0)
    plt.ylim(top=(max(power_data) + 50))
    plt.xlim(left=0)
    plt.xlim(right=max(power_x_axis))
    plt.savefig('./tmp/wallpower.png', bbox_inches='tight')

    # Plot and save the l3 cache miss figure.
    plt.figure(2)
    # Loop through all cores and plot their data.
    for core, data in enumerate(l3_miss_core):
        plt.plot(socket_x_axis,
                 data,
                 label=f'Core {config["app_cores"][core]}')
    # If the master core is enabled then plot its data.
    if config["app_master_enabled"] is True:
        plt.plot(socket_x_axis,
                 l3_miss_master,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L3 Miss Count')
    plt.title('L3 Cache Misses')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socket_x_axis))
    plt.savefig('./tmp/l3miss.png', bbox_inches='tight')

    # Generate the ls cache misses html for the report.
    l3_miss_html = (
        '<h2>L3 Cache</h2><img src="./tmp/l3miss.png" '
        'style="max-width: 650px"/>')
    # Generate html for the master core if enabled.
    if config["app_master_enabled"] is True:
        l3_miss_html += (f'<p>Master Core ({config["app_master_core"]}) '
                         f'L3 Misses: {l3_miss_master_avg}</p>')
    # Generate html for all the app cores.
    for core, data in enumerate(l3_miss_core_avg):
        l3_miss_html += (
            f'<p>Core {config["app_cores"][core]} L3 Misses: {data}</p>')

    # Plot and save the l2 cache miss figure.
    # Very similar to l3 cache miss above.
    plt.figure(3)
    for core, data in enumerate(l2_miss_core):
        plt.plot(socket_x_axis,
                 data,
                 label=f'Core {config["app_cores"][core]}')
    if config["app_master_enabled"] is True:
        plt.plot(socket_x_axis,
                 l2_miss_master,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L2 Miss Count')
    plt.title('L2 Cache Misses')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socket_x_axis))
    plt.savefig('./tmp/l2miss.png', bbox_inches='tight')
    l2_miss_html = (
        '<h2>L2 Cache</h2><img src="./tmp/l2miss.png" '
        'style="max-width: 650px"/>')
    if config["app_master_enabled"] is True:
        l2_miss_html += (f'<p>Master Core ({config["app_master_core"]}) '
                         f'L2 Misses: {l3_miss_master_avg}</p>')
    for core, data in enumerate(l2_miss_core_avg):
        l2_miss_html += (
            f'<p>Core {config["app_cores"][core]} L2 Misses: {data}</p>')

    # Plot and save the l3 cache hit figure.
    # Very similar to l3 cache miss above.
    plt.figure(4)
    for core, data in enumerate(l3_hit_core):
        plt.plot(socket_x_axis,
                 data,
                 label=f'Core {config["app_cores"][core]}')
    if config["app_master_enabled"] is True:
        plt.plot(socket_x_axis,
                 l3_hit_master,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L3 Hit (%)')
    plt.title('L3 Cache Hits')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socket_x_axis))
    plt.savefig('./tmp/l3hit.png', bbox_inches='tight')
    l3_hit_html = '<img src="./tmp/l3hit.png" style="max-width: 650px"/>'
    if config["app_master_enabled"] is True:
        l3_hit_html += (f'<p>Master Core ({config["app_master_core"]}) '
                        f'L3 Hits: {l3_hit_master_avg}%</p>')
    for core, data in enumerate(l3_hit_core_avg):
        l3_hit_html += (
            f'<p>Core {config["app_cores"][core]} L3 Hits: {data}%</p>')

    # Plot and save the l2 cache hit figure.
    # Very similar to l3 cache miss above.
    plt.figure(5)
    for core, data in enumerate(l2_hit_core):
        plt.plot(socket_x_axis,
                 data,
                 label=f'Core {config["app_cores"][core]}')
    if config["app_master_enabled"] is True:
        plt.plot(socket_x_axis,
                 l2_hit_master,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L2 Hit (%)')
    plt.title('L2 Cache Hits')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socket_x_axis))
    plt.savefig('./tmp/l2hit.png', bbox_inches='tight')
    l2_hit_html = '<img src="./tmp/l2hit.png" style="max-width: 650px"/>'
    if config["app_master_enabled"] is True:
        l2_hit_html += (f'<p>Master Core ({config["app_master_core"]}) '
                        f'L3 Hits: {l2_hit_master_avg}%</p>')
    for core, data in enumerate(l2_hit_core_avg):
        l2_hit_html += (
            f'<p>Core {config["app_cores"][core]} L2 Hits: {data}%</p>')

    # If telemetry is enabled then do telemetry calculations.
    telem_html = ''
    telem_datapoints = 0
    if config['telemetry']:
        # Read telemetry data from CSV.
        telem_data = pandas.read_csv('tmp/telemetry.csv',
                                     sep=',',
                                     low_memory=False)
        # Calculate telemetry datapoints.
        telem_datapoints = telem_data.shape[0] * telem_data.shape[1]
        # Extract telemetry data from pandas (packets and bytes information).
        telem_packets = np.asarray(
            telem_data['tx_good_packets'].tolist()).astype(int)
        telem_bytes = np.asarray(
            telem_data['tx_good_bytes'].tolist()).astype(int)
        telem_time = np.asarray(
            telem_data['time'].tolist()).astype(float)
        # Create array for packet distribution using only specific column set.
        telem_packet_dist = (
            telem_data.loc[:, ['tx_size_64_packets',
                               'tx_size_65_to_127_packets',
                               'tx_size_128_to_255_packets',
                               'tx_size_256_to_511_packets',
                               'tx_size_512_to_1023_packets',
                               'tx_size_1024_to_1522_packets',
                               'tx_size_1523_to_max_packets']
                           ].tail(1).values[0])
        # Array of human readable names for packet distribution.
        telem_packet_sizes = ['64', '65 to 127', '128 to 255', '256 to 511',
                              '512 to 1024', '1024 to 1522', '1523 to max']
        # Extract error and dropped packet data.
        telem_rx_errors = telem_data.loc[:, 'rx_errors'].tail(1).values[0]
        telem_rx_errors_bool = False
        telem_tx_errors = telem_data.loc[:, 'tx_errors'].tail(1).values[0]
        telem_tx_errors_bool = False
        telem_rx_dropped = (
            telem_data.loc[:, 'rx_dropped_packets'].tail(1).values[0])
        telem_rx_dropped_bool = False

        # Warn the user if any TX or RX errors occurred during the test.
        if int(telem_rx_errors) != 0:
            print('ERROR: RX errors occurred during this test (rx_errors:',
                  f'{telem_rx_errors})')
            telem_rx_errors_bool = True
        if int(telem_tx_errors) != 0:
            print('ERROR: TX errors occurred during this test (tx_errors:',
                  f'{telem_tx_errors})')
            telem_tx_errors_bool = True

        # Warn the user if any packets were dropped during the test.
        if int(telem_rx_dropped) != 0:
            print('ERROR: RX Packets were dropped during this test',
                  f'(rx_dropped_packets: {telem_rx_dropped})')
            telem_rx_dropped_bool = True

        # Generate the packet distribution figure.
        plt.figure(6)
        # Create an x axis for the plot.
        telem_x_axis = np.arange(telem_packet_dist.size)
        # Plot the distribution as a bar graph.
        plt.bar(telem_x_axis, height=telem_packet_dist)
        plt.xticks(telem_x_axis, telem_packet_sizes, rotation=45)
        plt.xlabel('Packet Sizes (Bytes)')
        plt.ylabel('Packets')
        plt.title('Packet Size Distribution')
        plt.savefig('./tmp/pktdist.png', bbox_inches='tight')

        # Reset the telemetry time to zero.
        telem_bytes_zero = telem_bytes[0]
        telem_bytes_reset = []
        for telem_byte in telem_bytes:
            telem_bytes_reset.append(telem_byte - telem_bytes_zero)

        # Convert the bytes measurements to gigabytes.
        telem_gigabytes = (
            [telem_x_axis / 1000000000 for telem_x_axis in telem_bytes_reset])

        # Find how many gigabytes were passed during the test.
        telem_gigabytes_max = np.round(max(telem_gigabytes), 1)

        # Reset the starting packet count to zero.
        telem_packets_zero = telem_packets[0]
        telem_packets_reset = []
        for packets in telem_packets:
            telem_packets_reset.append(packets - telem_packets_zero)

        # Find how many packets were passed during the test.
        telem_packets_reset_max = max(telem_packets_reset)

        # Generate a figure of how many packets and how much data was passed
        #   during the test.
        plt.figure(7)
        _, axis_1 = plt.subplots()
        # Create a second axis for packets.
        axis_2 = axis_1.twinx()
        axis_1.plot(telem_time,
                    telem_gigabytes,
                    alpha=1,
                    label='Data Transferred')
        axis_2.plot(telem_time,
                    telem_packets_reset,
                    alpha=0.6,
                    color='orange',
                    label='Packets Transferred')
        axis_1.set_xlabel('Time (Seconds)')
        axis_1.set_ylabel('Data Transferred (GB)')
        axis_2.set_ylabel('Packets Transferred (Packets)')
        axis_1.set_ylim(bottom=0)
        axis_2.set_ylim(bottom=0)
        # Manually move the legends as they will generate on top of each other
        #   separate because twin axis).
        axis_1.legend(loc=2)
        axis_2.legend(loc=1)
        plt.title('Data/Packets Transferred')
        plt.xlim(left=0)
        plt.xlim(right=max(telem_time))
        plt.savefig('./tmp/transfer.png', bbox_inches='tight')

        # Using the packets measurements calculate the
        #   packets per second (pps) array.
        telem_packets_per_sec = []
        for packets_x, packets_y in enumerate(telem_packets_reset):
            # If not the zeroth or first element calculate and append the pps.
            if packets_x not in (0, 1):
                telem_packets_per_sec.append(
                    (packets_y - telem_packets_reset[packets_x - 1]) /
                    config['test_step_size'])
            # If the first element calculate the pps, append it to the array
            #   and update zeroth element.
            elif packets_x == 1:
                val = ((packets_y - telem_packets_reset[packets_x - 1]) /
                       config['test_step_size'])
                telem_packets_per_sec.append(val)
                telem_packets_per_sec[0] = val
            # If the zeroth element dont calculate append placeholder value (0)
            #   as no previous element exists.
            else:
                telem_packets_per_sec.append(0)

        # Calculate the average pps.
        telem_packets_sec_avg = np.round(np.mean(telem_packets_per_sec), 0)

        # Using the bytes measurements calculate the throughput array.
        telem_throughput = []
        for bytes_x, bytes_y in enumerate(telem_bytes_reset):
            # If not the zeroth or first element calculate and append the
            #   throughput (Note: bits not bytes as per standard).
            if bytes_x not in (0, 1):
                telem_throughput.append(
                    (bytes_y - telem_bytes_reset[bytes_x - 1]) / 1000000000
                    * 8 / config['test_step_size'])
            # If the first element calculate the throughput, append it to the
            #   array and update zeroth element.
            elif bytes_x == 1:
                val = (
                    (bytes_y - telem_bytes_reset[bytes_x - 1]) / 1000000000
                    * 8 / config['test_step_size'])
                telem_throughput.append(val)
                telem_throughput[0] = val
            # If the zeroth element dont calculate append placeholder value (0)
            #   as no previous element exists.
            else:
                telem_throughput.append(0)

        # Calculate the average throughput.
        telem_throughput_avg = np.round(np.mean(telem_throughput), 2)

        # Generate plot of pps and throughput.
        plt.figure(8)
        _, axis_1 = plt.subplots()
        axis_2 = axis_1.twinx()
        axis_1.plot(telem_time,
                    telem_throughput,
                    alpha=1,
                    label='Throughput')
        axis_2.plot(telem_time,
                    telem_packets_per_sec,
                    alpha=0.6,
                    color='orange',
                    label='Packets Per Second')
        axis_1.set_xlabel('Time (Seconds)')
        axis_1.set_ylabel('Throughput (Gbps)')
        axis_2.set_ylabel('Packets Per Second (Packets)')
        axis_1.set_ylim(bottom=0)
        axis_2.set_ylim(bottom=0)
        axis_2.set_ylim(top=max(telem_packets_per_sec) + 1000000)
        axis_1.set_ylim(top=max(telem_throughput) + 1)
        axis_1.legend(loc=2)
        axis_2.legend(loc=1)
        plt.title('Transfer Speeds')
        plt.xlim(left=0)
        plt.xlim(right=max(telem_time))
        plt.savefig('./tmp/speeds.png', bbox_inches='tight')

        # Add generated figures, averages and maximums to the telemetry html.
        telem_html += (f'<h2>Telemetry</h2><img src="./tmp/pktdist.png" '
                       'style="max-width: 650px"/><p></p>'
                       '<img src="./tmp/transfer.png" '
                       'style="max-width: 650px"/>'
                       f'<p>Total Data Transferred: {telem_gigabytes_max}GB'
                       '</p><p>Total Packets Transferred: '
                       f'{format(telem_packets_reset_max, ",")} packets</p>'
                       '<img src="./tmp/speeds.png" style="max-width: 650px"/>'
                       f'<p>Average Throughput: {telem_throughput_avg} Gbps'
                       '</p><p>Average Packets Per Second: '
                       f'{format(telem_packets_sec_avg, ",")} pps</p>')

        # Add telemetry CSV to telemetry html.
        telem_html += ('<p><a href="./tmp/telemetry.csv" class="btn btn-info" '
                       'role="button">Download Full Telemetry CSV</a></p>'
                       '<h2>Errors</h2>')

        # Generate Errors and Dropped statistics for telemetry html.
        if telem_rx_errors_bool is False:
            telem_html += ('<h3 style="color:green;font-weight:bold;">'
                           f'RX Errors: {telem_rx_errors}</h3>')
        else:
            telem_html += ('<h3 style="color:red;font-weight:bold;">'
                           f'RX Errors: {telem_rx_errors}</h3>')
        if telem_tx_errors_bool is False:
            telem_html += ('<h3 style="color:green;font-weight:bold;">'
                           f'TX Errors: {telem_tx_errors}</h3>')
        else:
            telem_html += ('<h3 style="color:red;font-weight:bold;">'
                           f'TX Errors: {telem_tx_errors}</h3>')

        if telem_rx_dropped_bool is False:
            telem_html += ('<h3 style="color:green;font-weight:bold;">'
                           f'RX Dropped Packets: {telem_rx_dropped}</h3>')
        else:
            telem_html += ('<h3 style="color:red;font-weight:bold;">'
                           f'RX Dropped Packets: {telem_rx_dropped}</h3>')

    # If telemetry is disabled alert user in the report
    else:
        telem_html += ('<h2>Telemetry</h2>'
                       '<p style="color:red">Telemetry is disabled</p>')

    # If PDF generation is enabled then add link to html,
    #   if ZIP generation is enabled add link to html.
    report_html = ''
    if config['generate_pdf'] is True:
        report_html += ('<p style="text-align:center">'
                        '<a href="./tmp/doatreport.pdf" '
                        'class="btn btn-success" role="button" '
                        'style="font-size: 28px;">Download PDF Report</a></p>')
    if config['generate_zip'] is True:
        report_html += ('<p style="text-align:center">'
                        '<a href="./tmp/doat_results.zip" '
                        'class="btn btn-success" role="button" '
                        'style="font-size: 28px;">Download Results Zip</a>'
                        '</p>')

    op_html = ''
    op_datapoints = 0
    steps_enabled = False
    # Check if any optimisation steps are enabled.
    if config['mem_op'] is True:
        steps_enabled = True

    # If optimisation and any optimisation steps are enabled
    #   then perform optimisation.
    if config['op_enabled'] and steps_enabled:
        # Rewrite DPDK configuration (/config/rte_config.h) with
        #   updated options.
        print('\nModifying DPDK Configuration')
        for line in fileinput.FileInput(f'{config["dpdk_location"]}'
                                        '/config/rte_config.h',
                                        inplace=1):
            # Change mempool type.
            if ('RTE_MBUF_DEFAULT_MEMPOOL_OPS' in line and
                    config['mem_op'] is True):
                sys.stdout.write('#define RTE_MBUF_DEFAULT_MEMPOOL_OPS '
                                 '"stack"\n')
            # Disable mempool cache.
            elif ('RTE_MEMPOOL_CACHE_MAX_SIZE' in line and
                  config['mem_op'] is True and config['cache_adjust'] is True):
                sys.stdout.write(f'#define RTE_MEMPOOL_CACHE_MAX_SIZE '
                                 '{newcache}\n')
            # As more steps are added then more elif's will be added here.
            else:
                sys.stdout.write(line)

        # Set the CPU Affinity for DOAT back to normal this will speed up the
        #   build of DPDK as it will run on all available cores instead of one.
        #   In tests while pinned build took ~15 mins while unpinned
        #       took ~2 mins.
        subprocess.call(f'taskset -cp {config["cpu_aff_orig"]} {os.getpid()}',
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        print('DOAT unpinned from core to speed up build')

        # Build DPDK and DPDK app with new DPDK configuration.
        print('Building DPDK and DPDK App with new configuration options',
              '(This can take several minutes)')
        dpdk_build = subprocess.Popen(f'cd {config["dpdk_location"]}; '
                                      f'{config["dpdk_build_cmd"]};',
                                      shell=True,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)

        # While DPDK and app are building display build time and
        #   running animation.
        # The progress of the build is too hard to track and keep clean,
        #   this animation will however let the user know it hasn't crashed.
        animation = '|/-\\'
        animation_index = 0
        build_time = 0.0
        while dpdk_build.poll() is None:
            mins, secs = divmod(int(build_time), 60)
            print('Building . . .',
                  f'{mins:02d}:{secs:02d}',
                  animation[animation_index % len(animation)],
                  end='\r')
            animation_index += 1
            build_time += 0.1
            time.sleep(0.1)

        # Pin DOAT to specified core again.
        subprocess.call(f'taskset -cp {config["test_core"]} {os.getpid()}',
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        print('\nDOAT pinned to core',
              config['test_core'],
              'PID:',
              os.getpid())

        print('\nAnalysing Modified DPDK App')
        print('Starting DPDK App')

        # The process of running the test is the same as done above.
        op_dpdk_proc = subprocess.Popen(config['app_cmd'],
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.STDOUT,
                                        shell=True,
                                        preexec_fn=os.setsid)
        current_test_pid = op_dpdk_proc.pid

        if check_pid(current_test_pid):
            print('DPDK App started successfully')
        else:
            sys.exit('DPDK App failed to start, ABORT!')

        print('Allow application to startup and settle . . .')
        progress_bar(config['startup_time'])

        if op_dpdk_proc.poll() is not None:
            sys.exit('DPDK App died or failed to start, ABORT!')
        else:
            print('DPDK App ready for tests, PID:', current_test_pid)

        print('Starting Measurements . . .')

        op_pcm_proc = subprocess.Popen((f'{config["pcm_dir"]}pcm.x '
                                        f'{config["test_step_size"]} '
                                        '-csv=tmp/pcm_op.csv'),
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.STDOUT,
                                       shell=True,
                                       preexec_fn=os.setsid)

        op_power_proc = subprocess.Popen(
            r"echo 'power,time\n' > tmp/wallpower_op.csv; while true; "
            r"do ipmitool sdr | grep 'PS1 Input Power' | cut -c 20- |"
            r" cut -f1 -d 'W' | tr -d '\n' | sed 's/.$//' >> "
            r"tmp/wallpower_op.csv; echo -n ',' >> tmp/wallpower_op.csv; "
            r"date +%s >> tmp/wallpower_op.csv; sleep "
            f"{config['test_step_size']}; done",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            shell=True,
            preexec_fn=os.setsid)

        if config['telemetry']:
            op_telemetry_proc = subprocess.Popen(
                './tools/dpdk_telemetry_auto_csv.py -c tmp/telemetry_op.csv '
                f'-r {config["test_runtime"] + 2} '
                f'-s {config["test_step_size"]} '
                f'-f {config["file_prefix"]} '
                f'-p {config["telemetry_port"]}',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                shell=True,
                preexec_fn=os.setsid)

        progress_bar(2)

        if op_power_proc.poll() is not None:
            kill_group_pid(op_pcm_proc.pid)
            kill_group_pid(op_dpdk_proc.pid)
            if config['telemetry'] is True:
                kill_group_pid(op_telemetry_proc.pid)
            sys.exit('IPMItool died or failed to start, ABORT!')

        if op_pcm_proc.poll() is not None:
            kill_group_pid(op_power_proc.pid)
            kill_group_pid(op_dpdk_proc.pid)
            if config['telemetry'] is True:
                kill_group_pid(op_telemetry_proc.pid)
            sys.exit('PCM died or failed to start, ABORT! (If problem '
                     'persists, try to execute \'modprobe msr\' as root user)')

        if config['telemetry'] is True:
            if op_telemetry_proc.poll() is not None:
                kill_group_pid(op_pcm_proc.pid)
                kill_group_pid(op_power_proc.pid)
                kill_group_pid(op_dpdk_proc.pid)
                sys.exit('Telemetry died or failed to start, ABORT!')

        print('Running Test . . .')
        progress_bar(config['test_runtime'])

        op_app_died_during_test = False
        if op_dpdk_proc.poll() is None:
            print('SUCCESS: DPDK App is still alive after test')
        else:
            print('ERROR: DPDK App died during test')
            op_app_died_during_test = True

        print('Killing test processes')

        kill_group_pid(current_test_pid)

        kill_group_pid(op_pcm_proc.pid)

        kill_group_pid(op_power_proc.pid)

        if config['telemetry'] is True:
            kill_group_pid(op_telemetry_proc.pid)

        if op_app_died_during_test is True:
            sys.exit('Test invalid due to DPDK App dying during test, ABORT!')

        # DOAT will now analyse the new data in the same way as previously
        #   Op section also calculates the difference between the old and
        #   new data.

        csv_file = open('tmp/pcm_op.csv', 'r')
        op_file_data = csv_file.read()
        csv_file.close()

        op_new_data = op_file_data.replace(';', ',')

        csv_file = open('tmp/pcm_op.csv', 'w')
        csv_file.write(op_new_data)
        csv_file.close()

        op_pcm_data = pandas.read_csv('tmp/pcm_op.csv', low_memory=False)

        op_pcm_datapoints = op_pcm_data.shape[0] * op_pcm_data.shape[1]

        op_socket_read = (np.asarray((op_pcm_data.iloc[
            :, op_pcm_data.columns.get_loc(
                f'Socket {config["app_socket"]}') + 17].tolist())[1:]).astype(
                    float) * 1000)
        op_socket_write = (np.asarray((op_pcm_data.iloc[
            :, op_pcm_data.columns.get_loc(
                f'Socket {config["app_socket"]}') + 18].tolist())[1:]).astype(
                    float) * 1000)

        op_socket_read_avg = round(
            sum(op_socket_read) / len(op_socket_read), 2)
        op_socket_write_avg = round(
            sum(op_socket_write) / len(op_socket_write), 2)
        op_socket_write_read_ratio = round(
            op_socket_write_avg / op_socket_read_avg, 2)

        op_socket_read_avg_diff = (round((((
            op_socket_read_avg - socket_read_avg) / socket_read_avg) * 100),
                                         1))
        opsocketwriteavgdiff = (round((((
            op_socket_write_avg - socket_write_avg) / socket_write_avg) * 100),
                                      1))

        op_l3_miss_master = 0
        op_l2_miss_master = 0
        op_l3_hit_master = 0
        op_l2_hit_master = 0
        op_l3_miss_master_avg = 0.0
        op_l3_miss_master_avg_diff = 0.0
        op_l2_miss_master_avg = 0.0
        op_l2_miss_master_avg_diff = 0.0
        op_l3_hit_master_avg = 0.0
        op_l3_hit_master_avg_diff = 0.0
        op_l2_hit_master_avg = 0.0
        op_l2_hit_master_avg_diff = 0.0
        if config["app_master_enabled"] is True:
            op_l3_miss_master = np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 4].tolist(
                        ))[1:]).astype(float) * 1000 * 1000
            op_l2_miss_master = np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 5].tolist(
                        ))[1:]).astype(float) * 1000 * 1000
            op_l3_hit_master = np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 6].tolist(
                        ))[1:]).astype(float) * 100
            op_l2_hit_master = np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 7].tolist(
                        ))[1:]).astype(float) * 100
            op_l3_miss_master_avg = round(
                sum(op_l3_miss_master) / len(op_l3_miss_master), 1)
            op_l3_miss_master_avg_diff = (
                round((((op_l3_miss_master_avg - l3_miss_master_avg) /
                        l3_miss_master_avg) * 100), 1))
            op_l2_miss_master_avg = round(
                sum(op_l2_miss_master) / len(op_l2_miss_master), 1)
            op_l2_miss_master_avg_diff = (
                round((((op_l2_miss_master_avg - l2_miss_master_avg) /
                        l2_miss_master_avg) * 100), 1))
            op_l3_hit_master_avg = round(
                sum(op_l3_hit_master) / len(op_l3_hit_master), 1)
            op_l3_hit_master_avg_diff = round(
                op_l3_hit_master_avg - l3_hit_master_avg, 1)
            op_l2_hit_master_avg = round(
                sum(op_l2_hit_master) / len(op_l2_hit_master), 1)
            op_l2_hit_master_avg_diff = round(
                op_l2_hit_master_avg - l2_hit_master_avg, 1)

        op_l3_miss_core = []
        op_l2_miss_core = []
        op_l3_hit_core = []
        op_l2_hit_core = []

        for core in config['app_cores']:
            op_l3_miss_core.append(np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{core} (Socket {config["app_socket"]})') + 4].tolist(
                        ))[1:]).astype(float) * 1000 * 1000)
            op_l2_miss_core.append(np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{core} (Socket {config["app_socket"]})') + 5].tolist(
                        ))[1:]).astype(float) * 1000 * 1000)
            op_l3_hit_core.append(np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{core} (Socket {config["app_socket"]})')
                                  + 6].tolist())[1:]).astype(float) * 100)
            op_l2_hit_core.append(np.asarray(
                (op_pcm_data.iloc[:, op_pcm_data.columns.get_loc(
                    f'Core{core} (Socket {config["app_socket"]})')
                                  + 7].tolist())[1:]).astype(float) * 100)

        op_l3_miss_core_avg = []
        op_l3_miss_core_avg_diff = []
        op_l2_miss_core_avg = []
        op_l2_miss_core_avg_diff = []
        op_l3_hit_core_avg = []
        op_l3_hit_core_avg_diff = []
        op_l2_hit_core_avg = []
        op_l2_hit_core_avg_diff = []
        for core, data in enumerate(op_l3_miss_core):
            misses = round(sum(data) / len(data), 1)
            op_l3_miss_core_avg.append(misses)
            op_l3_miss_core_avg_diff.append(
                round((((misses - l3_miss_core_avg[core]) /
                        l3_miss_core_avg[core]) * 100), 1))
        for core, data in enumerate(op_l2_miss_core):
            misses = round(sum(data) / len(data), 1)
            op_l2_miss_core_avg.append(misses)
            op_l2_miss_core_avg_diff.append(
                round((((misses - l2_miss_core_avg[core]) /
                        l2_miss_core_avg[core]) * 100), 1))
        for core, data in enumerate(op_l3_hit_core):
            hits = round(sum(data) / len(data), 1)
            op_l3_hit_core_avg.append(hits)
            op_l3_hit_core_avg_diff.append(round(
                hits - l3_hit_core_avg[core], 1))
        for core, data in enumerate(op_l2_hit_core):
            hits = round(sum(data) / len(data), 1)
            op_l2_hit_core_avg.append(hits)
            op_l2_hit_core_avg_diff.append(
                round(hits - l2_hit_core_avg[core], 1))

        op_socket_x_axis = []
        op_time_x_axis = 0
        for _ in op_socket_read:
            op_socket_x_axis.append(op_time_x_axis)
            op_time_x_axis += config['test_step_size']

        # The plots generated are very similar to the plots generated above
        #   except they allow for comparison between the original and new data
        #   by putting them on the same plot.

        # Generate the read and write memory bandwidth op figure.
        plt.figure(10)
        plt.plot(socket_x_axis,
                 socket_read,
                 alpha=0.7,
                 label='Original Read')
        plt.plot(socket_x_axis,
                 socket_write,
                 alpha=0.7,
                 label='Original Write')
        plt.plot(op_socket_x_axis,
                 op_socket_read,
                 alpha=0.7,
                 label='Modified Read')
        plt.plot(op_socket_x_axis,
                 op_socket_write,
                 alpha=0.7,
                 label='Modified Write')
        plt.xlabel('Time (Seconds)')
        plt.ylabel('Bandwidth (MBps)')
        plt.title('Memory Bandwidth')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.ylim(top=(max([max(socket_read), max(socket_write)]) + 100))
        plt.xlim(right=max(op_socket_x_axis))
        plt.savefig('./tmp/membw_op.png', bbox_inches='tight')

        op_mem_bw_html = (
            '<h2>Memory Bandwidth</h2>'
            '<img src="./tmp/membw_op.png" style="max-width: 650px"/>'
            f'<p>Read Avg: {op_socket_read_avg}MBps '
            f'({op_socket_read_avg_diff:+0.1f}%)</p><p>'
            f'Write Avg: {op_socket_write_avg}MBps '
            f'({opsocketwriteavgdiff:+0.1f}%)</p><p>Write to Read Ratio: '
            f'{op_socket_write_read_ratio}</p><p><a href="./tmp/pcm_op.csv" '
            'class="btn btn-info" role="button">Download Full PCM CSV</a>')

        op_power_data_raw = pandas.read_csv('tmp/wallpower_op.csv',
                                            sep=',',
                                            low_memory=False)
        op_power_datapoints = (
            op_power_data_raw.shape[0] * op_power_data_raw.shape[1])
        op_power_data = (
            np.asarray(op_power_data_raw['power'].tolist()).astype(int))
        op_power_time = (
            np.asarray(op_power_data_raw['time'].tolist()).astype(int))
        op_power_time_zero = op_power_time[0]
        op_power_x_axis = []
        for power_time in op_power_time:
            op_power_x_axis.append(power_time - op_power_time_zero)
        op_power_avg = round(sum(op_power_data) / len(op_power_data), 1)
        op_power_avg_diff = (
            round((((op_power_avg - power_avg) / power_avg) * 100), 1))

        op_power_html = (
            '<h2>Wall Power</h2>'
            '<img src="./tmp/wallpower_op.png" style="max-width: 650px"/>'
            f'<p>Wall Power Avg: {op_power_avg}Watts '
            f'({op_power_avg_diff:+0.1f}%)</p><p>'
            '<a href="./tmp/wallpower_op.csv" class="btn btn-info" '
            '"role="button">Download Power CSV</a>')

        # Plot and save the wall power op figure.
        plt.figure(11)
        plt.plot(power_x_axis,
                 power_data,
                 alpha=0.7,
                 label='Original Wall Power')
        plt.plot(op_power_x_axis,
                 op_power_data,
                 alpha=0.7,
                 label='Modified Wall Power')
        plt.xlabel('Time (Seconds)')
        plt.ylabel('Power (Watts)')
        plt.title('Wall Power')
        plt.legend()
        plt.ylim(bottom=0)
        plt.ylim(top=(max(op_power_data) + 50))
        plt.xlim(left=0)
        plt.xlim(right=max(op_power_x_axis))
        plt.savefig('./tmp/wallpower_op.png', bbox_inches='tight')

        # Plot and save the l3 cache miss op figure.
        plt.figure(12)
        for core, data in enumerate(l3_miss_core):
            plt.plot(socket_x_axis,
                     data,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(socket_x_axis,
                     l3_miss_master,
                     alpha=0.5,
                     label=('Original Master Core '
                            f'({config["app_master_core"]})'))
        for core, data in enumerate(op_l3_miss_core):
            plt.plot(op_socket_x_axis,
                     data,
                     alpha=0.7,
                     label=f'Modified Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(op_socket_x_axis,
                     op_l3_miss_master,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L3 Miss Count')
        plt.title('L3 Cache Misses')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(op_socket_x_axis))
        plt.savefig('./tmp/l3miss_op.png', bbox_inches='tight')
        op_l3_miss_html = (
            '<h2>L3 Cache</h2>'
            '<img src="./tmp/l3miss_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            op_l3_miss_html += (f'<p>Master Core ({config["app_master_core"]})'
                                f' L3 Misses: {op_l3_miss_master_avg} '
                                f'({op_l3_miss_master_avg_diff:+0.1f}%)</p>')
        for core, data in enumerate(op_l3_miss_core_avg):
            op_l3_miss_html += (f'<p>Core {config["app_cores"][core]} '
                                f'L3 Misses: {data} '
                                f'({op_l3_miss_core_avg_diff[core]:+0.1f}%)'
                                '</p>')

        # Plot and save the l2 cache miss op figure.
        plt.figure(13)
        for core, data in enumerate(l2_miss_core):
            plt.plot(socket_x_axis,
                     data,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(socket_x_axis,
                     l2_miss_master,
                     alpha=0.5,
                     label=('Original Master Core '
                            f'({config["app_master_core"]})'))
        for core, data in enumerate(op_l2_miss_core):
            plt.plot(op_socket_x_axis,
                     data,
                     alpha=0.7,
                     label=f'Modified Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(op_socket_x_axis,
                     op_l2_miss_master,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L2 Miss Count')
        plt.title('L2 Cache Misses')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(op_socket_x_axis))
        plt.savefig('./tmp/l2miss_op.png', bbox_inches='tight')
        op_l2_miss_html = (
            '<h2>L2 Cache</h2>'
            '<img src="./tmp/l2miss_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            op_l2_miss_html += (f'<p>Master Core ({config["app_master_core"]})'
                                f' L2 Misses: {op_l3_miss_master_avg} '
                                f'({op_l2_miss_master_avg_diff:+0.1f}%)</p>')
        for core, data in enumerate(op_l2_miss_core_avg):
            op_l2_miss_html += (f'<p>Core {config["app_cores"][core]} '
                                f'L2 Misses: {data} '
                                f'({op_l2_miss_core_avg_diff[core]:+0.1f}%)'
                                '</p>')

        # Plot and save the l3 cache hit op figure.
        plt.figure(14)
        for core, data in enumerate(l3_hit_core):
            plt.plot(socket_x_axis,
                     data,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(socket_x_axis,
                     l3_hit_master,
                     alpha=0.5,
                     label=(f'Original Master Core '
                            f'({config["app_master_core"]})'))
        for core, data in enumerate(op_l3_hit_core):
            plt.plot(op_socket_x_axis,
                     data,
                     alpha=0.5,
                     label=f'Modified Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(op_socket_x_axis,
                     op_l3_hit_master,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L3 Hit (%)')
        plt.title('L3 Cache Hits')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(op_socket_x_axis))
        plt.savefig('./tmp/l3hit_op.png', bbox_inches='tight')
        op_l3_hit_html = (
            '<img src="./tmp/l3hit_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            op_l3_hit_html += (f'<p>Master Core ({config["app_master_core"]}) '
                               f'L3 Hits: {op_l3_hit_master_avg}% '
                               f'({op_l3_hit_master_avg_diff:+0.1f}%)</p>')
        for core, data in enumerate(op_l3_hit_core_avg):
            op_l3_hit_html += (f'<p>Core {config["app_cores"][core]} '
                               f'L3 Hits: {data}% '
                               f'({op_l3_hit_core_avg_diff[core]:+0.1f}%)</p>')

        # Plot and save the l2 cache hit op figure.
        plt.figure(15)
        for core, data in enumerate(l2_hit_core):
            plt.plot(socket_x_axis,
                     data,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(socket_x_axis,
                     l2_hit_master,
                     alpha=0.5,
                     label=('Original Master Core '
                            f'({config["app_master_core"]})'))
        for core, data in enumerate(op_l2_hit_core):
            plt.plot(op_socket_x_axis,
                     data,
                     alpha=0.7,
                     label=f'Modified Core {config["app_cores"][core]}')
        if config["app_master_enabled"] is True:
            plt.plot(op_socket_x_axis,
                     op_l2_hit_master,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L2 Hit (%)')
        plt.title('L2 Cache Hits')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(op_socket_x_axis))
        plt.savefig('./tmp/l2hit_op.png', bbox_inches='tight')
        op_l2_hit_html = (
            '<img src="./tmp/l2hit_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            op_l2_hit_html += (f'<p>Master Core ({config["app_master_core"]}) '
                               f'L2 Hits: {op_l2_hit_master_avg}% '
                               f'({op_l2_hit_master_avg_diff:+0.1f}%)</p>')
        for core, data in enumerate(op_l2_hit_core_avg):
            op_l2_hit_html += (f'<p>Core {config["app_cores"][core]} L2 Hits: '
                               f'{data}% '
                               f'({op_l2_hit_core_avg_diff[core]:+0.1f}%)</p>')

        op_telem_html = ''
        op_telem_datapoints = 0
        if config['telemetry'] is True:
            op_telem_data = pandas.read_csv('tmp/telemetry_op.csv',
                                            sep=',',
                                            low_memory=False)
            op_telem_datapoints = (
                op_telem_data.shape[0] * op_telem_data.shape[1])
            op_telem_packets = np.asarray(
                op_telem_data['tx_good_packets'].tolist()).astype(int)
            op_telem_bytes = np.asarray(
                op_telem_data['tx_good_bytes'].tolist()).astype(int)
            op_telem_time = np.asarray(
                op_telem_data['time'].tolist()).astype(float)
            op_telem_packet_dist = (
                op_telem_data.loc[:, ['tx_size_64_packets',
                                      'tx_size_65_to_127_packets',
                                      'tx_size_128_to_255_packets',
                                      'tx_size_256_to_511_packets',
                                      'tx_size_512_to_1023_packets',
                                      'tx_size_1024_to_1522_packets',
                                      'tx_size_1523_to_max_packets']
                                  ].tail(1).values[0])
            op_telem_packet_sizes = ['64', '65 to 127', '128 to 255',
                                     '256 to 511', '512 to 1024',
                                     '1024 to 1522', '1523 to max']
            op_telem_rx_errors = (
                op_telem_data.loc[:, 'rx_errors'].tail(1).values[0])
            op_telem_rx_errors_diff = op_telem_rx_errors - telem_rx_errors
            op_telem_rx_errors_bool = False
            op_telem_tx_errors = (
                op_telem_data.loc[:, 'tx_errors'].tail(1).values[0])
            op_telem_tx_errors_diff = op_telem_tx_errors - telem_tx_errors
            op_telem_tx_errors_bool = False
            op_telem_rx_dropped = (
                op_telem_data.loc[:, 'rx_dropped_packets'].tail(1).values[0])
            op_telem_rx_dropped_diff = op_telem_rx_dropped - telem_rx_dropped
            op_telem_rx_dropped_bool = False

            if int(op_telem_rx_errors) != 0:
                print('ERROR: RX errors occurred during this test (rx_errors:',
                      f'{op_telem_rx_errors})')
                op_telem_rx_errors_bool = True
            if int(op_telem_tx_errors) != 0:
                print('ERROR: TX errors occurred during this test (tx_errors:',
                      f'{op_telem_tx_errors})')
                op_telem_tx_errors_bool = True

            if int(op_telem_rx_dropped) != 0:
                print('ERROR: RX Packets were dropped during this test',
                      f'(rx_dropped_packets: {op_telem_rx_dropped})')
                op_telem_rx_dropped_bool = True

            # Generate an op figure for packet distribution.
            plt.figure(16)
            packet_dist_x_axis = np.arange(op_telem_packet_dist.size)
            plt.bar(packet_dist_x_axis, height=op_telem_packet_dist)
            plt.xticks(packet_dist_x_axis, op_telem_packet_sizes, rotation=45)
            plt.xlabel('Packet Sizes (Bytes)')
            plt.ylabel('Packets')
            plt.title('Packet Size Distribution')
            plt.savefig('./tmp/pktdist_op.png', bbox_inches='tight')

            op_telem_bytes_zero = op_telem_bytes[0]
            op_telem_bytes_reset = []
            for op_byte in op_telem_bytes:
                op_telem_bytes_reset.append(op_byte - op_telem_bytes_zero)

            op_telem_gigabytes = (
                [op_bytes / 1000000000 for op_bytes in op_telem_bytes_reset])

            op_telem_gigabytes_max = np.round(max(op_telem_gigabytes), 1)
            op_telem_gigabytes_max_diff = (
                np.round(op_telem_gigabytes_max - telem_gigabytes_max, 1))

            op_telem_packet_zero = op_telem_packets[0]
            op_telem_packet_reset = []
            for op_packets in op_telem_packets:
                op_telem_packet_reset.append(op_packets - op_telem_packet_zero)

            op_telem_packet_reset_max = max(op_telem_packet_reset)
            op_telem_packet_reset_max_diff = (
                np.round(op_telem_packet_reset_max - telem_packets_reset_max,
                         1))

            plt.figure(17)
            _, axis_1 = plt.subplots()
            axis_2 = axis_1.twinx()
            axis_1.plot(op_telem_time,
                        op_telem_gigabytes,
                        alpha=1,
                        label='Data Transferred')
            axis_2.plot(op_telem_time,
                        op_telem_packet_reset,
                        alpha=0.6,
                        color='orange',
                        label='Packets Transferred')
            axis_1.set_xlabel('Time (Seconds)')
            axis_1.set_ylabel('Data Transferred (GB)')
            axis_2.set_ylabel('Packets Transferred (Packets)')
            axis_1.set_ylim(bottom=0)
            axis_2.set_ylim(bottom=0)
            axis_1.legend(loc=2)
            axis_2.legend(loc=1)
            plt.title('Data/Packets Transferred')
            plt.xlim(left=0)
            plt.xlim(right=max(op_telem_time))
            plt.savefig('./tmp/transfer_op.png', bbox_inches='tight')

            op_telem_packet_sec = []
            for packet_x, data in enumerate(op_telem_packet_reset):
                if packet_x in (0, 1):
                    op_telem_packet_sec.append(
                        (data - op_telem_packet_reset[packet_x - 1]) /
                        config['test_step_size'])
                elif packet_x == 1:
                    val = ((data - op_telem_packet_reset[packet_x - 1]) /
                           config['test_step_size'])
                    op_telem_packet_sec.append(val)
                    op_telem_packet_sec[0] = val
                else:
                    op_telem_packet_sec.append(0)

            op_telem_packet_sec_avg = np.round(np.mean(op_telem_packet_sec), 0)
            op_telem_packet_sec_avg_diff = (
                np.round(op_telem_packet_sec_avg - telem_packets_sec_avg, 0))

            op_telem_throughput = []
            for bytes_x, data in enumerate(op_telem_bytes_reset):
                if bytes_x in (0, 1):
                    op_telem_throughput.append(
                        (data - op_telem_bytes_reset[bytes_x - 1])
                        / 1000000000 * 8 / config['test_step_size'])
                elif bytes_x == 1:
                    val = ((data - op_telem_bytes_reset[bytes_x - 1])
                           / 1000000000 * 8 / config['test_step_size'])
                    op_telem_throughput.append(val)
                    op_telem_throughput[0] = val
                else:
                    op_telem_throughput.append(0)

            op_telem_throughput_avg = np.round(np.mean(op_telem_throughput), 2)
            op_telem_throughput_avg_diff = np.round(
                op_telem_throughput_avg - op_telem_throughput_avg, 2)

            # Generate am op figure for throughput and pps.
            plt.figure(18)
            _, axis_1 = plt.subplots()
            axis_2 = axis_1.twinx()
            axis_1.plot(telem_time,
                        telem_throughput,
                        alpha=0.7,
                        label='Original Throughput')
            axis_1.plot(op_telem_time,
                        op_telem_throughput,
                        alpha=0.7,
                        label='Modified Throughput')
            axis_2.plot(telem_time,
                        telem_packets_per_sec,
                        alpha=0.7,
                        color='red',
                        label='Original Packets Per Second')
            axis_2.plot(op_telem_time,
                        op_telem_packet_sec,
                        alpha=0.7,
                        color='green',
                        label='Modified Packets Per Second')
            axis_1.set_xlabel('Time (Seconds)')
            axis_1.set_ylabel('Throughput (Gbps)')
            axis_2.set_ylabel('Packets Per Second (Packets)')
            axis_1.set_ylim(bottom=0)
            axis_2.set_ylim(bottom=0)
            axis_2.set_ylim(top=max(op_telem_packet_sec) + 1000000)
            axis_1.set_ylim(top=max(op_telem_throughput) + 1)
            axis_1.legend(loc=3)
            axis_2.legend(loc=4)
            plt.title('Transfer Speeds')
            plt.xlim(left=0)
            plt.xlim(right=max(op_telem_time))
            plt.savefig('./tmp/speeds_op.png', bbox_inches='tight')

            op_telem_html += (
                '<h2>Telemetry</h2>'
                '<img src="./tmp/pktdist_op.png" style="max-width: 650px"/>'
                '<p></p><img src="./tmp/transfer_op.png" '
                'style="max-width: 650px"/>'
                f'<p>Total Data Transferred: {op_telem_gigabytes_max}GB '
                f'({op_telem_gigabytes_max_diff:+0.1f}GB)</p>'
                '<p>Total Packets Transferred: '
                f'{format(op_telem_packet_reset_max, ",")}'
                f' packets ({op_telem_packet_reset_max_diff:+0,.0f} packets)'
                '</p><img src="./tmp/speeds_op.png" style="max-width: 650px"/>'
                f'<p>Average Throughput: {op_telem_throughput_avg} Gbps '
                f'({op_telem_throughput_avg_diff:+0.2f}Gbps)</p>'
                '<p>Average Packets Per Second: '
                f'{format(op_telem_packet_sec_avg, ",")}'
                f' pps ({op_telem_packet_sec_avg_diff:+0,.0f} pps)</p>')

            op_telem_html += (
                '<p><a href="./tmp/telemetry_op.csv" class="btn btn-info" '
                'role="button">Download Full Telemetry CSV</a></p>'
                '<h2>Errors</h2>')

            if op_telem_rx_errors_bool is False:
                op_telem_html += (
                    '<h3 style="color:green;font-weight:bold;">RX Errors: '
                    f'{op_telem_rx_errors} ({op_telem_rx_errors_diff:+0d})'
                    '</h3>')
            else:
                op_telem_html += (
                    '<h3 style="color:red;font-weight:bold;">RX Errors: '
                    f'{op_telem_rx_errors} ({op_telem_rx_errors_diff:+0d})'
                    '</h3>')
            if op_telem_tx_errors_bool is False:
                op_telem_html += (
                    '<h3 style="color:green;font-weight:bold;">TX Errors: '
                    f'{op_telem_tx_errors} ({op_telem_tx_errors_diff:+0d})'
                    '</h3>')
            else:
                op_telem_html += (
                    '<h3 style="color:red;font-weight:bold;">TX Errors: '
                    f'{op_telem_tx_errors} ({op_telem_tx_errors_diff:+0d})'
                    '</h3>')

            if op_telem_rx_dropped_bool is False:
                op_telem_html += (
                    '<h3 style="color:green;font-weight:bold;">'
                    f'RX Dropped Packets: {op_telem_rx_dropped} '
                    f'({op_telem_rx_dropped_diff:+0d})</h3>')
            else:
                op_telem_html += (
                    '<h3 style="color:red;font-weight:bold;">'
                    f'RX Dropped Packets: {op_telem_rx_dropped} '
                    f'({op_telem_rx_dropped_diff:+0d})</h3>')
        else:
            op_telem_html += (
                '<h2>Telemetry</h2><p style="color:red">'
                'Telemetry is disabled</p>')

        op_rec_html = "<h2>Optimisation Recommendations</h2>"
        # Generate op recommendations.
        # If the mem b/w has improved while there was no decrease in throughput
        #   and no errors or drops, then recommend mem op if not dont.
        if ((op_socket_read_avg_diff < -25.0) and
                (opsocketwriteavgdiff < -25.0) and
                (op_telem_throughput_avg_diff > -0.2) and
                op_telem_rx_dropped <= 0):
            op_rec_html += (
                '<p>It is recommended to change from ring mempools to stack '
                'mempools based on the optimisation results.<br/>'
                'This can be done by setting '
                'RTE_MBUF_DEFAULT_MEMPOOL_OPS="stack" '
                'in the DPDK /config/rte_config.h file.</br>'
                'Please manually review this report to confirm that this '
                'recommendation is right for your project.</p>')
        else:
            op_rec_html += (
                '<p>It is recommended not to change from ring mempools to '
                'stack mempools based on the optimisation results</p>')

        # Generate optimisation html.
        op_html = (
            '<div class="row mt-5" style="page-break-after: always;">'
            f'{op_mem_bw_html}</div>'
            '<div class="row mt-5" style="page-break-after: always;">'
            f'{op_power_html}</div><div class="row mt-5" '
            f'style="page-break-after: always;">{op_l3_miss_html}</div>'
            '<div class="row" style="page-break-after: always;">'
            f'{op_l3_hit_html}</div><div class="row mt-5" '
            'style="page-break-after: always;">'
            f'{op_l2_miss_html}</div><div class="row"'
            f'style="page-break-after: always;">{op_l2_hit_html}</div>'
            f'<div class="row mt-5">{op_telem_html}</div>'
            '<div class="row mt-5" style="page-break-after: always;">'
            f'{op_rec_html}</div>')

        # Calculate op datapoints.
        op_datapoints = (
            op_pcm_datapoints + op_power_datapoints + op_telem_datapoints)

        # Write old DPDK config file back.
        print('\nSetting DPDK Configuration back to original')
        for line in fileinput.FileInput(f'{config["dpdk_location"]}'
                                        'config/rte_config.h',
                                        inplace=1):
            if ('RTE_MBUF_DEFAULT_MEMPOOL_OPS' in line and
                    config['mem_op'] is True):
                sys.stdout.write('#define RTE_MBUF_DEFAULT_MEMPOOL_OPS '
                                 '"ring_mp_mc"\n')
            elif ('RTE_MEMPOOL_CACHE_MAX_SIZE' in line and
                  config['mem_op'] is True and
                  config['cache_adjust'] is True):
                sys.stdout.write('#define RTE_MEMPOOL_CACHE_MAX_SIZE '
                                 f'{config["cache_orig"]}\n')
            else:
                sys.stdout.write(line)

        # Unpin DOAT for DPDK build.
        subprocess.call(f'taskset -cp {config["cpu_aff_orig"]} {os.getpid()}',
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        print('DOAT unpinned from core to speed up build')

        # Rebuild DPDK with original DPDK config.
        print('Rebuilding DPDK and DPDK App with original configuration',
              'options (This can take several minutes)')
        dpdk_rebuild = subprocess.Popen(f'cd {config["dpdk_location"]}; '
                                        f'{config["dpdk_build_cmd"]};',
                                        shell=True,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
        # Building animation.
        animation = '|/-\\'
        animation_index = 0
        build_time = 0.0
        while dpdk_rebuild.poll() is None:
            animation_mins, animation_secs = divmod(int(build_time), 60)
            print('Building . . .',
                  f'{animation_mins:02d}:{animation_secs:02d}',
                  animation[animation_index % len(animation)],
                  end='\r')
            animation_index += 1
            build_time += 0.1
            time.sleep(0.1)

    # If no op steps are enabled then dont run optimisation.
    elif steps_enabled is False:
        print('\nNo Optimisation Steps are enabled skipping optimisation')

    print('\n\nGenerating report')

    # Sum all datapoints used in report.
    datapoints = (
        pcm_datapoints + power_datapoints + telem_datapoints + op_datapoints)

    # Get report generation time in 2 formats
    report_time_sentence = strftime('%I:%M%p on %d %B %Y', gmtime())
    report_time = strftime('%I:%M%p %d/%m/%Y', gmtime())

    # If a project name is specified add it to the report.
    project_details_html = ''
    if config['project_name']:
        project_details_html += (
            '<p style="font-size: 18px;">'
            f'Project: {config["project_name"]}</p>')
    # If a tester is specified add their details to the report.
    if config['tester_name'] and config['tester_email']:
        project_details_html += ('<p style="font-size: 18px;">'
                                 f'Tester: {config["tester_name"]} '
                                 f'({config["tester_email"]})</p>')

    # If op enabled then split the report under 2 main headings.
    test_header_unmod = ''
    test_header_mod = ''
    if config['op_enabled'] is True:
        test_header_unmod = (
            '<div class="row mt-5"><h1 style="font-weight:bold;">'
            'Original DPDK App</h1></div>')
        test_header_mod = (
            '<div class="row mt-5"><h1 style="font-weight:bold;">'
            'Modified DPDK App</h1></div>')

    # Generate acknowledgement html if enabled.
    report_header = ''
    ack_html = ''
    if config['doat_ack'] is True:
        report_header = (
            '<img src="./webcomponents/doat_logo.png" height="49px" '
            'name="logo" style="margin-bottom: 11px;"/> Report')
        ack_html = (
            '<h2>DOAT Acknowledgement</h2><p>'
            '<img src="./webcomponents/doat_logo.png" height="80px" '
            'name="logo"/></p>'
            '<p>This report was compiled using the DPDK Optimisation &amp; '
            'Analysis Tool or DOAT for short (<i>Pronunciation: d&omacr;t</i>)'
            '</p><p>DOAT is a tool for analysing and assisting in the '
            'optimisation of applications built using DPDK. DOAT is an out of '
            'band analysis tool that does not require the DPDK app being '
            'analysed to be changed.</p><p>DOAT was developed by '
            '<a href="http://conorwalsh.net" target="_blank">Conor Walsh '
            '(conor@conorwalsh.net)</a> as part of his final year project for '
            'his degree in Electronic and Computer Engineering at the '
            'University of Limerick. Hardware and guidance for the project '
            'was provided by the Networks Platform Group in Intel (Shannon, '
            'Ireland).</p><p>DOAT is available as an open source project.'
            '<a href="https://github.com/conorwalsh/doat/" name="git" '
            'target="_blank>github.com/conorwalsh/doat</a></p>')
    else:
        report_header = 'DOAT Report'

    # Create a html file to save the html report.
    html_index_file = open('index.html', 'w')
    json_table = ''
    if JSON2HTML_AVAILABLE:
        json_table = ((json2html.convert(json=(str(
            {section: dict(config['full_json'][section])
             for section in config['full_json'].sections()}
            )).replace("\'", "\""))).replace("border=\"1\"", "")).replace(
                "table", "table class=\"table\"", 1)
    else:
        json_table = ('<p>The json2html python module must be installed to '
                      'show the test configuration.</p>')
    # Write all parts of the report to the html file.
    html_index_file.write(
        '<html><head><title>DOAT Report</title><link rel="stylesheet"'
        'href="./webcomponents/bootstrap.513.min.css">'
        '</script><script src="./webcomponents/bootstrap.513.min.js"></script>'
        '<style>@media print{a:not([name="git"]){display:none!important}'
        'img:not([name="logo"]){max-width:100%!important}}</style></head>'
        f'<body><div class="p-5 bg-light text-center"><h1>{report_header}</h1>'
        '<p style="font-size: 14px">DPDK Optimisation & Analysis Tool</p>'
        f'<p>Report compiled at {report_time_sentence} using '
        f'{format(datapoints, ",")} data points</p>{project_details_html}'
        f'</div><div class="container">{test_header_unmod}'
        '<div class="row mt-5" style="page-break-after: always;">'
        f'{mem_bw_html}</div><div class="row mt-5" '
        'style="page-break-after: always;">'
        f'{wallpowerhtml}</div><div class="row mt-5" style="page-break-after: '
        f'always;">{l3_miss_html}</div><div class="row" '
        f'style="page-break-after: always;">{l3_hit_html}</div><div '
        f'class="row mt-5" style="page-break-after: always;">{l2_miss_html}'
        '</div><div class="row" style="page-break-after: always;">'
        f'{l2_hit_html}</div><div class="row mt-5" style="page-break-after:'
        f' always;">{telem_html}</div>'
        f'{test_header_mod}'
        f'{op_html}'
        '<div class="row mt-5"><h2>Test Configuration</h2>'
        f'{json_table}'
        f'</div><div class="row mt-5">{ack_html}</div><br/>'
        f'<div class="row mt-5">{report_html}</div></div></body></html>')
    # Close the html file.
    html_index_file.close()

    # If PDF generation is on then generate the PDF report using the
    #   pdfkit (wkhtmltopdf).
    if config['generate_pdf'] is True:
        pdf_options = {'page-size': 'A4',
                       'quiet': '',
                       'margin-top': '19.1',
                       'margin-right': '25.4',
                       'margin-bottom': '25.4',
                       'margin-left': '25.4',
                       'encoding': "UTF-8",
                       'footer-right': 'Page [page] of [topage]',
                       'footer-left': report_time,
                       'footer-line': '',
                       'print-media-type': ''
                       }
        wkhtml_to_pdf_loc = subprocess.check_output(
            'which wkhtmltopdf', shell=True).decode(
                sys.stdout.encoding).strip()
        pdf_config = pdfkit.configuration(wkhtmltopdf=wkhtml_to_pdf_loc)
        pdfkit.from_file('index.html',
                         './tmp/doatreport.pdf',
                         configuration=pdf_config,
                         options=pdf_options)

    # If Zip generation is enabled then sort all available files into
    #   directories, zip the dir and clean up after.
    if config['generate_zip'] is True:
        subprocess.call('cp -r tmp archive; cp config.cfg ./archive; '
                        'cd archive; mkdir raw_data; mkdir figures; '
                        'mv *.png ./figures; mv *.csv ./raw_data; '
                        'zip -r ../doat_results.zip *; cd ..; '
                        'mv doat_results.zip ./tmp/; rm -rf archive;',
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT,
                        shell=True)

    # Create a new html server at localhost and the specified port.
    server_address = ('', config['server_port'])
    print('Serving results on port', config['server_port'])
    print('CTRL+c to kill server and exit')
    # Setup the server
    http_server = HTTPServer(server_address, SimpleHTTPRequestHandler)
    # Try to serve the report forever until exception.
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http_server.server_close()


if __name__ == '__main__':
    main()
