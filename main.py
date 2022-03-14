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

 Copyright (c) 2021 Conor Walsh
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
    proc = subprocess.Popen(config['app_cmd'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT,
                            shell=True,
                            preexec_fn=os.setsid)
    current_test_pid = proc.pid

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
    if proc.poll() is not None:
        sys.exit('DPDK App died or failed to start, ABORT!')
    else:
        print('DPDK App ready for tests, PID:', current_test_pid)

    print('Starting Measurements . . .')

    # Spawn PCM in a new process.
    # PCM will measure cpu and platform metrics.
    pcm = subprocess.Popen(f'{config["pcm_dir"]}pcm.x '
                           f'{config["test_step_size"]} -csv=tmp/pcm.csv',
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT,
                           shell=True,
                           preexec_fn=os.setsid)

    # Spawn ipmitool in a new process.
    # IPMItool is used to measure platform power usage.
    wallp = subprocess.Popen(
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
        telem = subprocess.Popen(
            './tools/dpdk_telemetry_auto_csv.py -c tmp/telemetry.csv -r '
            f'{config["test_runtime"] + 2} -s {config["test_step_size"]} -p '
            f'{config["telemetry_port"]}',
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            shell=True,
            preexec_fn=os.setsid)

    # Wait 2 seconds for the measurement tools to startup.
    progress_bar(2)

    # Check if IMPItool is still alive after startup. Abort if not
    if wallp.poll() is not None:
        # Kill PCM.
        kill_group_pid(pcm.pid)
        # Kill DPDK app.
        kill_group_pid(proc.pid)
        # Kill telemetry if enabled.
        if config['telemetry'] is True:
            kill_group_pid(telem.pid)
        # Exit.
        sys.exit('IPMItool died or failed to start, ABORT!')

    # Check if PCM is still alive after startup. Abort if not.
    if pcm.poll() is not None:
        # Kill IMPItool.
        kill_group_pid(wallp.pid)
        # Kill DPDK app.
        kill_group_pid(proc.pid)
        # Kill telemetry if enabled.
        if config['telemetry'] is True:
            kill_group_pid(telem.pid)
        # Exit.
        sys.exit('PCM died or failed to start, ABORT! (If problem persists, '
                 'try to execute \'modprobe msr\' as root user)')

    # If telemetry enabled check if its still alive. Abort if not.
    if config['telemetry'] is True:
        if telem.poll() is not None:
            # Kill PCM.
            kill_group_pid(pcm.pid)
            # Kill IMPItool.
            kill_group_pid(wallp.pid)
            # Kill DPDK app.
            kill_group_pid(proc.pid)
            # Exit.
            sys.exit('Telemetry died or failed to start, ABORT!')

    # Allow test to run and collect statistics for user specified time.
    print('Running Test . . .')
    progress_bar(config['test_runtime'])

    # Check if the DPDK App is still alive after the test.
    appdiedduringtest = False
    if proc.poll() is None:
        print('SUCCESS: DPDK App is still alive after test')
    else:
        print('ERROR: DPDK App died during test')
        appdiedduringtest = True

    # Kill all tools.
    print('Killing test processes')
    kill_group_pid(current_test_pid)
    kill_group_pid(pcm.pid)
    kill_group_pid(wallp.pid)
    if config['telemetry'] is True:
        kill_group_pid(telem.pid)

    # Abort test if DPDK app died during test.
    if appdiedduringtest is True:
        sys.exit('Test invalid due to DPDK App dying during test, ABORT!')

    # PCM tool exports CSVs that use semicolons instead of the standard comma.
    # Open file and replace all semicolons with commas.
    # This could have been used but its more convenient for the user.
    csv_file = open('tmp/pcm.csv', 'r')
    filedata = csv_file.read()
    csv_file.close()
    newdata = filedata.replace(';', ',')
    csv_file = open('tmp/pcm.csv', 'w')
    csv_file.write(newdata)
    csv_file.close()

    # Read the PCM CSV using pandas.
    pcmdata = pandas.read_csv('tmp/pcm.csv', low_memory=False)

    # Calculate how many datapoints are in the PCM CSV.
    pcmdatapoints = pcmdata.shape[0] * pcmdata.shape[1]

    # Extract socket memory bandwidth read and write to numpy arrays.
    socketread = (np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
        f'Socket {config["app_socket"]}') + 13].tolist())[1:]).astype(float)
                  * 1000)
    socketwrite = (np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
        f'Socket {config["app_socket"]}') + 14].tolist())[1:]).astype(float)
                   * 1000)

    # Calculate the average read and write of the memory bandwidth.
    socketreadavg = round(sum(socketread) / len(socketread), 2)
    socketwriteavg = round(sum(socketwrite) / len(socketwrite), 2)
    # Calculate the ratio of reads to writes.
    socketwritereadratio = round(socketwriteavg / socketreadavg, 2)

    # Declare variables to store cache info for the master core.
    l3missmaster = 0
    l2missmaster = 0
    l3hitmaster = 0
    l2hitmaster = 0
    l3missmasteravg = 0.0
    l2missmasteravg = 0.0
    l3hitmasteravg = 0.0
    l2hitmasteravg = 0.0
    # If the master core stats are enabled extract the data using pandas.
    if config["app_master_enabled"] is True:
        l3missmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 4].tolist())[1:]).astype(
                float) * 1000 * 1000
        l2missmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 5].tolist())[1:]).astype(
                float) * 1000 * 1000
        l3hitmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 6].tolist())[1:]).astype(
                float) * 100
        l2hitmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{config["app_master_core"]} '
            f'(Socket {config["app_socket"]})') + 7].tolist())[1:]).astype(
                float) * 100
        l3missmasteravg = round(sum(l3missmaster) / len(l3missmaster), 1)
        l2missmasteravg = round(sum(l2missmaster) / len(l2missmaster), 1)
        l3hitmasteravg = round(sum(l3hitmaster) / len(l3hitmaster), 1)
        l2hitmasteravg = round(sum(l2hitmaster) / len(l2hitmaster), 1)

    # Declare arrays to store cache info for cores.
    l3misscore = []
    l2misscore = []
    l3hitcore = []
    l2hitcore = []
    # Extract cache data for cores.
    for x in config['app_cores']:
        l3misscore.append(np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{x} (Socket {config["app_socket"]})') + 4].tolist()
                                     )[1:]).astype(float) * 1000 * 1000)
        l2misscore.append(np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{x} (Socket {config["app_socket"]})') + 5].tolist()
                                     )[1:]).astype(float) * 1000 * 1000)
        l3hitcore.append(np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{x} (Socket {config["app_socket"]})') + 6].tolist()
                                     )[1:]).astype(float) * 100)
        l2hitcore.append(np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc(
            f'Core{x} (Socket {config["app_socket"]})') + 7].tolist()
                                     )[1:]).astype(float) * 100)

    # Declare arrays to store average cache info for cores.
    l3misscoreavg = []
    l2misscoreavg = []
    l3hitcoreavg = []
    l2hitcoreavg = []
    # Calculate average cache data for cores.
    for x in l3misscore:
        l3misscoreavg.append(round(sum(x) / len(x), 1))
    for x in l2misscore:
        l2misscoreavg.append(round(sum(x) / len(x), 1))
    for x in l3hitcore:
        l3hitcoreavg.append(round(sum(x) / len(x), 1))
    for x in l2hitcore:
        l2hitcoreavg.append(round(sum(x) / len(x), 1))

    # Create a corresponding time array for the memory bandwidth arrays.
    socketx = []
    timex = 0
    for x in socketread:
        socketx.append(timex)
        timex += config['test_step_size']

    # Generate the read and write memory bandwidth figure.
    # Each figure must have a unique number.
    plt.figure(0)
    # Plot the figure.
    plt.plot(socketx, socketread, label='Read')
    plt.plot(socketx, socketwrite, label='Write')
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
    plt.ylim(top=(max([max(socketread), max(socketwrite)]) + 100))
    plt.xlim(right=max(socketx))
    # Save the figure in the tmp dir.
    plt.savefig('./tmp/membw.png', bbox_inches='tight')

    # Generate the memory bandwidth html code for the report.
    membwhtml = ('<h2>Memory Bandwidth</h2>'
                 '<img src="./tmp/membw.png" style="max-width: 650px"/>'
                 f'<p>Read Avg: {socketreadavg}MBps</p><p>Write Avg: '
                 f'{socketwriteavg}MBps</p><p>Write to Read Ratio: '
                 f'{socketwritereadratio}</p><p><a href="./tmp/pcm.csv" '
                 'class="btn btn-info" role="button">Download Full PCM CSV'
                 '</a>')

    # Read the IPMItool CSV using pandas.
    wallpdata = pandas.read_csv('tmp/wallpower.csv', sep=',', low_memory=False)
    # Calculate how many datapoints are in the IPMItool CSV.
    wallpdatapoints = wallpdata.shape[0] * wallpdata.shape[1]
    # Extract the power data from the CSV.
    wallpower = np.asarray(wallpdata['power'].tolist()).astype(int)
    # Extract the time data from the CSV.
    wallpowertime = np.asarray(wallpdata['time'].tolist()).astype(int)
    # Set the starting time for the time to 0.
    wallpowertimezero = wallpowertime[0]
    wallpowerx = []
    for x in wallpowertime:
        wallpowerx.append(x - wallpowertimezero)
    # Calculate the average power.
    wallpoweravg = round(sum(wallpower) / len(wallpower), 1)

    # Generate the power html for the report.
    wallpowerhtml = ('<h2>Wall Power</h2>'
                     '<img src="./tmp/wallpower.png" '
                     'style="max-width: 650px"/>'
                     f'<p>Wall Power Avg: {wallpoweravg}Watts</p>'
                     '<p><a href="./tmp/wallpower.csv" class="btn btn-info" '
                     'role="button">Download Power CSV</a>')

    # Plot and save the wall power figure.
    plt.figure(1)
    plt.plot(wallpowerx, wallpower, label='Wall Power')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('Power (Watts)')
    plt.title('Wall Power')
    plt.legend()
    plt.ylim(bottom=0)
    plt.ylim(top=(max(wallpower) + 50))
    plt.xlim(left=0)
    plt.xlim(right=max(wallpowerx))
    plt.savefig('./tmp/wallpower.png', bbox_inches='tight')

    # Plot and save the l3 cache miss figure.
    plt.figure(2)
    # Loop through all cores and plot their data.
    for i, y in enumerate(l3misscore):
        plt.plot(socketx, y, label=f'Core {config["app_cores"][i]}')
    # If the master core is enabled then plot its data.
    if config["app_master_enabled"] is True:
        plt.plot(socketx,
                 l3missmaster,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L3 Miss Count')
    plt.title('L3 Cache Misses')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socketx))
    plt.savefig('./tmp/l3miss.png', bbox_inches='tight')

    # Generate the ls cache misses html for the report.
    l3misshtml = (
        '<h2>L3 Cache</h2><img src="./tmp/l3miss.png" '
        'style="max-width: 650px"/>')
    # Generate html for the master core if enabled.
    if config["app_master_enabled"] is True:
        l3misshtml += (f'<p>Master Core ({config["app_master_core"]}) '
                       f'L3 Misses: {l3missmasteravg}</p>')
    # Generate html for all the app cores.
    for i, x in enumerate(l3misscoreavg):
        l3misshtml += f'<p>Core {config["app_cores"][i]} L3 Misses: {x}</p>'

    # Plot and save the l2 cache miss figure.
    # Very similar to l3 cache miss above.
    plt.figure(3)
    for i, y in enumerate(l2misscore):
        plt.plot(socketx, y, label=f'Core {config["app_cores"][i]}')
    if config["app_master_enabled"] is True:
        plt.plot(socketx,
                 l2missmaster,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L2 Miss Count')
    plt.title('L2 Cache Misses')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socketx))
    plt.savefig('./tmp/l2miss.png', bbox_inches='tight')
    l2misshtml = (
        '<h2>L2 Cache</h2><img src="./tmp/l2miss.png" '
        'style="max-width: 650px"/>')
    if config["app_master_enabled"] is True:
        l2misshtml += (f'<p>Master Core ({config["app_master_core"]}) '
                       f'L2 Misses: {l3missmasteravg}</p>')
    for i, x in enumerate(l2misscoreavg):
        l2misshtml += f'<p>Core {config["app_cores"][i]} L2 Misses: {x}</p>'

    # Plot and save the l3 cache hit figure.
    # Very similar to l3 cache miss above.
    plt.figure(4)
    for i, y in enumerate(l3hitcore):
        plt.plot(socketx, y, label=f'Core {config["app_cores"][i]}')
    if config["app_master_enabled"] is True:
        plt.plot(socketx,
                 l3hitmaster,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L3 Hit (%)')
    plt.title('L3 Cache Hits')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socketx))
    plt.savefig('./tmp/l3hit.png', bbox_inches='tight')
    l3hithtml = '<img src="./tmp/l3hit.png" style="max-width: 650px"/>'
    if config["app_master_enabled"] is True:
        l3hithtml += (f'<p>Master Core ({config["app_master_core"]}) '
                      f'L3 Hits: {l3hitmasteravg}%</p>')
    for i, x in enumerate(l3hitcoreavg):
        l3hithtml += f'<p>Core {config["app_cores"][i]} L3 Hits: {x}%</p>'

    # Plot and save the l2 cache hit figure.
    # Very similar to l3 cache miss above.
    plt.figure(5)
    for i, y in enumerate(l2hitcore):
        plt.plot(socketx, y, label=f'Core {config["app_cores"][i]}')
    if config["app_master_enabled"] is True:
        plt.plot(socketx,
                 l2hitmaster,
                 alpha=0.5,
                 label=f'Master Core ({config["app_master_core"]})')
    plt.xlabel('Time (Seconds)')
    plt.ylabel('L2 Hit (%)')
    plt.title('L2 Cache Hits')
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(socketx))
    plt.savefig('./tmp/l2hit.png', bbox_inches='tight')
    l2hithtml = '<img src="./tmp/l2hit.png" style="max-width: 650px"/>'
    if config["app_master_enabled"] is True:
        l2hithtml += (f'<p>Master Core ({config["app_master_core"]}) '
                      f'L3 Hits: {l2hitmasteravg}%</p>')
    for i, x in enumerate(l2hitcoreavg):
        l2hithtml += f'<p>Core {config["app_cores"][i]} L2 Hits: {x}%</p>'

    # If telemetry is enabled then do telemetry calculations.
    telemhtml = ''
    telemdatapoints = 0
    if config['telemetry']:
        # Read telemetry data from CSV.
        telemdata = pandas.read_csv('tmp/telemetry.csv',
                                    sep=',',
                                    low_memory=False)
        # Calculate telemetry datapoints.
        telemdatapoints = telemdata.shape[0] * telemdata.shape[1]
        # Extract telemetry data from pandas (packets and bytes information).
        telempkts = np.asarray(
            telemdata['tx_good_packets'].tolist()).astype(int)
        telembytes = np.asarray(
            telemdata['tx_good_bytes'].tolist()).astype(int)
        telemtime = np.asarray(
            telemdata['time'].tolist()).astype(float)
        # Create array for packet distribution using only specific column set.
        telempktdist = (
            telemdata.loc[:, ['tx_size_64_packets',
                              'tx_size_65_to_127_packets',
                              'tx_size_128_to_255_packets',
                              'tx_size_256_to_511_packets',
                              'tx_size_512_to_1023_packets',
                              'tx_size_1024_to_1522_packets',
                              'tx_size_1523_to_max_packets']
                          ].tail(1).values[0])
        # Array of human readable names for packet distribution.
        telempktsizes = ['64', '65 to 127', '128 to 255', '256 to 511',
                         '512 to 1024', '1024 to 1522', '1523 to max']
        # Extract error and dropped packet data.
        telemrxerrors = telemdata.loc[:, 'rx_errors'].tail(1).values[0]
        telemrxerrorsbool = False
        telemtxerrors = telemdata.loc[:, 'tx_errors'].tail(1).values[0]
        telemtxerrorsbool = False
        telemrxdropped = (
            telemdata.loc[:, 'rx_dropped_packets'].tail(1).values[0])
        telemrxdroppedbool = False

        # Warn the user if any TX or RX errors occurred during the test.
        if int(telemrxerrors) != 0:
            print('ERROR: RX errors occurred during this test (rx_errors:',
                  f'{telemrxerrors})')
            telemrxerrorsbool = True
        if int(telemtxerrors) != 0:
            print('ERROR: TX errors occurred during this test (tx_errors:',
                  f'{telemtxerrors})')
            telemtxerrorsbool = True

        # Warn the user if any packets were dropped during the test.
        if int(telemrxdropped) != 0:
            print('ERROR: RX Packets were dropped during this test',
                  f'(rx_dropped_packets: {telemrxdropped})')
            telemrxdroppedbool = True

        # Generate the packet distribution figure.
        plt.figure(6)
        # Create an x array for the plot.
        x = np.arange(telempktdist.size)
        # Plot the distribution as a bar graph.
        plt.bar(x, height=telempktdist)
        plt.xticks(x, telempktsizes, rotation=45)
        plt.xlabel('Packet Sizes (Bytes)')
        plt.ylabel('Packets')
        plt.title('Packet Size Distribution')
        plt.savefig('./tmp/pktdist.png', bbox_inches='tight')

        # Reset the telemetry time to zero.
        telembyteszero = telembytes[0]
        telembytesreset = []
        for y in telembytes:
            telembytesreset.append(y - telembyteszero)

        # Convert the bytes measurements to gigabytes.
        telemgbytes = [x / 1000000000 for x in telembytesreset]

        # Find how many gigabytes were passed during the test.
        telemgbytesmax = np.round(max(telemgbytes), 1)

        # Reset the starting packet count to zero.
        telempktszero = telempkts[0]
        telempktsreset = []
        for y in telempkts:
            telempktsreset.append(y - telempktszero)

        # Find how many packets were passed during the test.
        telempktsresetmax = max(telempktsreset)

        # Generate a figure of how many packets and how much data was passed
        #   during the test.
        plt.figure(7)
        _, ax1 = plt.subplots()
        # Create a second axis for packets.
        ax2 = ax1.twinx()
        ax1.plot(telemtime,
                 telemgbytes,
                 alpha=1,
                 label='Data Transferred')
        ax2.plot(telemtime,
                 telempktsreset,
                 alpha=0.6,
                 color='orange',
                 label='Packets Transferred')
        ax1.set_xlabel('Time (Seconds)')
        ax1.set_ylabel('Data Transferred (GB)')
        ax2.set_ylabel('Packets Transferred (Packets)')
        ax1.set_ylim(bottom=0)
        ax2.set_ylim(bottom=0)
        # Manually move the legends as they will generate on top of each other
        #   separate because twin axis).
        ax1.legend(loc=2)
        ax2.legend(loc=1)
        plt.title('Data/Packets Transferred')
        plt.xlim(left=0)
        plt.xlim(right=max(telemtime))
        plt.savefig('./tmp/transfer.png', bbox_inches='tight')

        # Using the packets measurements calculate the
        #   packets per second (pps) array.
        telempktssec = []
        for i, y in enumerate(telempktsreset):
            # If not the zeroth or first element calculate and append the pps.
            if i != 0 and i != 1:
                telempktssec.append((y - telempktsreset[i - 1]) /
                                    config['test_step_size'])
            # If the first element calculate the pps, append it to the array
            #   and update zeroth element.
            elif i == 1:
                val = (y - telempktsreset[i - 1]) / config['test_step_size']
                telempktssec.append(val)
                telempktssec[0] = val
            # If the zeroth element dont calculate append placeholder value (0)
            #   as no previous element exists.
            else:
                telempktssec.append(0)

        # Calculate the average pps.
        telempktsecavg = np.round(np.mean(telempktssec), 0)

        # Using the bytes measurements calculate the throughput array.
        telemthroughput = []
        for i, y in enumerate(telembytesreset):
            # If not the zeroth or first element calculate and append the
            #   throughput (Note: bits not bytes as per standard).
            if i != 0 and i != 1:
                telemthroughput.append(
                    (y - telembytesreset[i - 1]) / 1000000000 * 8 /
                    config['test_step_size'])
            # If the first element calculate the throughput, append it to the
            #   array and update zeroth element.
            elif i == 1:
                val = (
                    (y - telembytesreset[i - 1]) / 1000000000 * 8 /
                    config['test_step_size'])
                telemthroughput.append(val)
                telemthroughput[0] = val
            # If the zeroth element dont calculate append placeholder value (0)
            #   as no previous element exists.
            else:
                telemthroughput.append(0)

        # Calculate the average throughput.
        telemthroughputavg = np.round(np.mean(telemthroughput), 2)

        # Generate plot of pps and throughput.
        plt.figure(8)
        _, ax1 = plt.subplots()
        ax2 = ax1.twinx()
        ax1.plot(telemtime,
                 telemthroughput,
                 alpha=1,
                 label='Throughput')
        ax2.plot(telemtime,
                 telempktssec,
                 alpha=0.6,
                 color='orange',
                 label='Packets Per Second')
        ax1.set_xlabel('Time (Seconds)')
        ax1.set_ylabel('Throughput (Gbps)')
        ax2.set_ylabel('Packets Per Second (Packets)')
        ax1.set_ylim(bottom=0)
        ax2.set_ylim(bottom=0)
        ax2.set_ylim(top=max(telempktssec) + 1000000)
        ax1.set_ylim(top=max(telemthroughput) + 1)
        ax1.legend(loc=2)
        ax2.legend(loc=1)
        plt.title('Transfer Speeds')
        plt.xlim(left=0)
        plt.xlim(right=max(telemtime))
        plt.savefig('./tmp/speeds.png', bbox_inches='tight')

        # Add generated figures, averages and maximums to the telemetry html.
        telemhtml += (f'<h2>Telemetry</h2><img src="./tmp/pktdist.png" '
                      'style="max-width: 650px"/><p></p>'
                      '<img src="./tmp/transfer.png" '
                      'style="max-width: 650px"/>'
                      f'<p>Total Data Transferred: {telemgbytesmax}GB</p>'
                      '<p>Total Packets Transferred: '
                      f'{format(telempktsresetmax, ",")} packets</p>'
                      '<img src="./tmp/speeds.png" style="max-width: 650px"/>'
                      f'<p>Average Throughput: {telemthroughputavg} Gbps</p>'
                      '<p>Average Packets Per Second: '
                      f'{format(telempktsecavg, ",")} pps</p>')

        # Add telemetry CSV to telemetry html.
        telemhtml += ('<p><a href="./tmp/telemetry.csv" class="btn btn-info" '
                      'role="button">Download Full Telemetry CSV</a></p>'
                      '<h2>Errors</h2>')

        # Generate Errors and Dropped statistics for telemetry html.
        if telemrxerrorsbool is False:
            telemhtml += ('<h3 style="color:green;font-weight:bold;">'
                          f'RX Errors: {telemrxerrors}</h3>')
        else:
            telemhtml += ('<h3 style="color:red;font-weight:bold;">'
                          f'RX Errors: {telemrxerrors}</h3>')
        if telemtxerrorsbool is False:
            telemhtml += ('<h3 style="color:green;font-weight:bold;">'
                          f'TX Errors: {telemtxerrors}</h3>')
        else:
            telemhtml += ('<h3 style="color:red;font-weight:bold;">'
                          f'TX Errors: {telemtxerrors}</h3>')

        if telemrxdroppedbool is False:
            telemhtml += ('<h3 style="color:green;font-weight:bold;">'
                          f'RX Dropped Packets: {telemrxdropped}</h3>')
        else:
            telemhtml += ('<h3 style="color:red;font-weight:bold;">'
                          f'RX Dropped Packets: {telemrxdropped}</h3>')

    # If telemetry is disabled alert user in the report
    else:
        telemhtml += ('<h2>Telemetry</h2>'
                      '<p style="color:red">Telemetry is disabled</p>')

    # If PDF generation is enabled then add link to html,
    #   if ZIP generation is enabled add link to html.
    reporthtml = ''
    if config['generate_pdf'] is True:
        reporthtml += ('<p style="text-align:center">'
                       '<a href="./tmp/doatreport.pdf" '
                       'class="btn btn-success" role="button" '
                       'style="font-size: 28px;">Download PDF Report</a></p>')
    if config['generate_zip'] is True:
        reporthtml += ('<p style="text-align:center">'
                       '<a href="./tmp/doat_results.zip" '
                       'class="btn btn-success" role="button" '
                       'style="font-size: 28px;">Download Results Zip</a></p>')

    ophtml = ''
    opdatapoints = 0
    stepsenabled = False
    # Check if any optimisation steps are enabled.
    if config['mem_op'] is True:
        stepsenabled = True

    # If optimisation and any optimisation steps are enabled
    #   then perform optimisation.
    if config['op_enabled'] and stepsenabled:
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
        dpdkbuild = subprocess.Popen(f'cd {config["dpdk_location"]}; '
                                     f'{config["dpdk_build_cmd"]};',
                                     shell=True,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)

        # While DPDK and app are building display build time and
        #   running animation.
        # The progress of the build is too hard to track and keep clean,
        #   this animation will however let the user know it hasn't crashed.
        animation = '|/-\\'
        idx = 0
        buildtime = 0.0
        while dpdkbuild.poll() is None:
            m, s = divmod(int(buildtime), 60)
            print('Building . . .',
                  f'{m:02d}:{s:02d}',
                  animation[idx % len(animation)],
                  end='\r')
            idx += 1
            buildtime += 0.1
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
        opproc = subprocess.Popen(config['app_cmd'],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT,
                                  shell=True,
                                  preexec_fn=os.setsid)
        current_test_pid = opproc.pid

        if check_pid(current_test_pid):
            print('DPDK App started successfully')
        else:
            sys.exit('DPDK App failed to start, ABORT!')

        print('Allow application to startup and settle . . .')
        progress_bar(config['startup_time'])

        if opproc.poll() is not None:
            sys.exit('DPDK App died or failed to start, ABORT!')
        else:
            print('DPDK App ready for tests, PID:', current_test_pid)

        print('Starting Measurements . . .')

        oppcm = subprocess.Popen((f'{config["pcm_dir"]}pcm.x '
                                  f'{config["test_step_size"]} '
                                  '-csv=tmp/pcm_op.csv'),
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.STDOUT,
                                 shell=True,
                                 preexec_fn=os.setsid)

        opwallp = subprocess.Popen(
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
            optelem = subprocess.Popen(
                './tools/dpdk_telemetry_auto_csv.py -c tmp/telemetry_op.csv '
                f'-r {config["test_runtime"] + 2} '
                f'-s {config["test_step_size"]} '
                f'-p {config["telemetry_port"]}',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                shell=True,
                preexec_fn=os.setsid)

        progress_bar(2)

        if opwallp.poll() is not None:
            kill_group_pid(oppcm.pid)
            kill_group_pid(opproc.pid)
            if config['telemetry'] is True:
                kill_group_pid(optelem.pid)
            sys.exit('IPMItool died or failed to start, ABORT!')

        if oppcm.poll() is not None:
            kill_group_pid(opwallp.pid)
            kill_group_pid(opproc.pid)
            if config['telemetry'] is True:
                kill_group_pid(optelem.pid)
            sys.exit('PCM died or failed to start, ABORT! (If problem '
                     'persists, try to execute \'modprobe msr\' as root user)')

        if config['telemetry'] is True:
            if optelem.poll() is not None:
                kill_group_pid(oppcm.pid)
                kill_group_pid(opwallp.pid)
                kill_group_pid(opproc.pid)
                sys.exit('Telemetry died or failed to start, ABORT!')

        print('Running Test . . .')
        progress_bar(config['test_runtime'])

        opappdiedduringtest = False
        if opproc.poll() is None:
            print('SUCCESS: DPDK App is still alive after test')
        else:
            print('ERROR: DPDK App died during test')
            opappdiedduringtest = True

        print('Killing test processes')

        kill_group_pid(current_test_pid)

        kill_group_pid(oppcm.pid)

        kill_group_pid(opwallp.pid)

        if config['telemetry'] is True:
            kill_group_pid(optelem.pid)

        if opappdiedduringtest is True:
            sys.exit('Test invalid due to DPDK App dying during test, ABORT!')

        # DOAT will now analyse the new data in the same way as previously
        #   Op section also calculates the difference between the old and
        #   new data.

        f = open('tmp/pcm_op.csv', 'r')
        opfiledata = f.read()
        f.close()

        opnewdata = opfiledata.replace(';', ',')

        f = open('tmp/pcm_op.csv', 'w')
        f.write(opnewdata)
        f.close()

        oppcmdata = pandas.read_csv('tmp/pcm_op.csv', low_memory=False)

        oppcmdatapoints = oppcmdata.shape[0] * oppcmdata.shape[1]

        opsocketread = (np.asarray((oppcmdata.iloc[
            :, oppcmdata.columns.get_loc(
                f'Socket {config["app_socket"]}') + 13].tolist())[1:]).astype(
                    float) * 1000)
        opsocketwrite = (np.asarray((oppcmdata.iloc[
            :, oppcmdata.columns.get_loc(
                f'Socket {config["app_socket"]}') + 14].tolist())[1:]).astype(
                    float) * 1000)

        opsocketreadavg = round(sum(opsocketread) / len(opsocketread), 2)
        opsocketwriteavg = round(sum(opsocketwrite) / len(opsocketwrite), 2)
        opsocketwritereadratio = round(opsocketwriteavg / opsocketreadavg, 2)

        opsocketreadavgdiff = (
            round((((opsocketreadavg - socketreadavg) / socketreadavg) * 100),
                  1))
        opsocketwriteavgdiff = (round((((
            opsocketwriteavg - socketwriteavg) / socketwriteavg) * 100), 1))

        opl3missmaster = 0
        opl2missmaster = 0
        opl3hitmaster = 0
        opl2hitmaster = 0
        opl3missmasteravg = 0.0
        opl3missmasteravgdiff = 0.0
        opl2missmasteravg = 0.0
        opl2missmasteravgdiff = 0.0
        opl3hitmasteravg = 0.0
        opl3hitmasteravgdiff = 0.0
        opl2hitmasteravg = 0.0
        opl2hitmasteravgdiff = 0.0
        if config["app_master_enabled"] is True:
            opl3missmaster = np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 4].tolist(
                        ))[1:]).astype(float) * 1000 * 1000
            opl2missmaster = np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 5].tolist(
                        ))[1:]).astype(float) * 1000 * 1000
            opl3hitmaster = np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 6].tolist(
                        ))[1:]).astype(float) * 100
            opl2hitmaster = np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{config["app_master_core"]} '
                    f'(Socket {config["app_socket"]})') + 7].tolist(
                        ))[1:]).astype(float) * 100
            opl3missmasteravg = round(
                sum(opl3missmaster) / len(opl3missmaster), 1)
            opl3missmasteravgdiff = (round((((
                opl3missmasteravg - l3missmasteravg) / l3missmasteravg) * 100),
                                           1))
            opl2missmasteravg = round(
                sum(opl2missmaster) / len(opl2missmaster), 1)
            opl2missmasteravgdiff = (round((((
                opl2missmasteravg - l2missmasteravg) / l2missmasteravg) * 100),
                                           1))
            opl3hitmasteravg = round(
                sum(opl3hitmaster) / len(opl3hitmaster), 1)
            opl3hitmasteravgdiff = round(
                opl3hitmasteravg - l3hitmasteravg, 1)
            opl2hitmasteravg = round(
                sum(opl2hitmaster) / len(opl2hitmaster), 1)
            opl2hitmasteravgdiff = round(
                opl2hitmasteravg - l2hitmasteravg, 1)

        opl3misscore = []
        opl2misscore = []
        opl3hitcore = []
        opl2hitcore = []

        for x in config['app_cores']:
            opl3misscore.append(np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{x} (Socket {config["app_socket"]})') + 4].tolist(
                        ))[1:]).astype(float) * 1000 * 1000)
            opl2misscore.append(np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{x} (Socket {config["app_socket"]})') + 5].tolist(
                        ))[1:]).astype(float) * 1000 * 1000)
            opl3hitcore.append(np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{x} (Socket {config["app_socket"]})')
                                + 6].tolist())[1:]).astype(float) * 100)
            opl2hitcore.append(np.asarray(
                (oppcmdata.iloc[:, oppcmdata.columns.get_loc(
                    f'Core{x} (Socket {config["app_socket"]})')
                                + 7].tolist())[1:]).astype(float) * 100)

        opl3misscoreavg = []
        opl3misscoreavgdiff = []
        opl2misscoreavg = []
        opl2misscoreavgdiff = []
        opl3hitcoreavg = []
        opl3hitcoreavgdiff = []
        opl2hitcoreavg = []
        opl2hitcoreavgdiff = []
        for i, x in enumerate(opl3misscore):
            misses = round(sum(x) / len(x), 1)
            opl3misscoreavg.append(misses)
            opl3misscoreavgdiff.append(
                round((((misses - l3misscoreavg[i]) / l3misscoreavg[i]) * 100),
                      1))
        for i, x in enumerate(opl2misscore):
            misses = round(sum(x) / len(x), 1)
            opl2misscoreavg.append(misses)
            opl2misscoreavgdiff.append(
                round((((misses - l2misscoreavg[i]) / l2misscoreavg[i]) * 100),
                      1))
        for i, x in enumerate(opl3hitcore):
            hits = round(sum(x) / len(x), 1)
            opl3hitcoreavg.append(hits)
            opl3hitcoreavgdiff.append(round(hits - l3hitcoreavg[i], 1))
        for i, x in enumerate(opl2hitcore):
            hits = round(sum(x) / len(x), 1)
            opl2hitcoreavg.append(hits)
            opl2hitcoreavgdiff.append(round(hits - l2hitcoreavg[i], 1))

        opsocketx = []
        optimex = 0
        for x in opsocketread:
            opsocketx.append(optimex)
            optimex += config['test_step_size']

        # The plots generated are very similar to the plots generated above
        #   except they allow for comparison between the original and new data
        #   by putting them on the same plot.

        # Generate the read and write memory bandwidth op figure.
        plt.figure(10)
        plt.plot(socketx, socketread, alpha=0.7, label='Original Read')
        plt.plot(socketx, socketwrite, alpha=0.7, label='Original Write')
        plt.plot(opsocketx, opsocketread, alpha=0.7, label='Modified Read')
        plt.plot(opsocketx, opsocketwrite, alpha=0.7, label='Modified Write')
        plt.xlabel('Time (Seconds)')
        plt.ylabel('Bandwidth (MBps)')
        plt.title('Memory Bandwidth')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.ylim(top=(max([max(socketread), max(socketwrite)]) + 100))
        plt.xlim(right=max(opsocketx))
        plt.savefig('./tmp/membw_op.png', bbox_inches='tight')

        opmembwhtml = (
            '<h2>Memory Bandwidth</h2>'
            '<img src="./tmp/membw_op.png" style="max-width: 650px"/>'
            f'<p>Read Avg: {opsocketreadavg}MBps ({opsocketreadavgdiff:+0.1f}'
            f'%)</p><p>Write Avg: {opsocketwriteavg}MBps '
            f'({opsocketwriteavgdiff:+0.1f}%)</p><p>Write to Read Ratio: '
            f'{opsocketwritereadratio}</p><p><a href="./tmp/pcm_op.csv" '
            'class="btn btn-info" role="button">Download Full PCM CSV</a>')

        opwallpdata = pandas.read_csv('tmp/wallpower_op.csv',
                                      sep=',',
                                      low_memory=False)
        opwallpdatapoints = opwallpdata.shape[0] * opwallpdata.shape[1]
        opwallpower = np.asarray(opwallpdata['power'].tolist()).astype(int)
        opwallpowertime = np.asarray(opwallpdata['time'].tolist()).astype(int)
        opwallpowertimezero = opwallpowertime[0]
        opwallpowerx = []
        for x in opwallpowertime:
            opwallpowerx.append(x - opwallpowertimezero)
        opwallpoweravg = round(sum(opwallpower) / len(opwallpower), 1)
        opwallpoweravgdiff = (
            round((((opwallpoweravg - wallpoweravg) / wallpoweravg) * 100), 1))

        opwallpowerhtml = (
            '<h2>Wall Power</h2>'
            '<img src="./tmp/wallpower_op.png" style="max-width: 650px"/>'
            f'<p>Wall Power Avg: {opwallpoweravg}Watts '
            f'({opwallpoweravgdiff:+0.1f}%)</p><p>'
            '<a href="./tmp/wallpower_op.csv" class="btn btn-info" '
            '"role="button">Download Power CSV</a>')

        # Plot and save the wall power op figure.
        plt.figure(11)
        plt.plot(wallpowerx,
                 wallpower,
                 alpha=0.7,
                 label='Original Wall Power')
        plt.plot(opwallpowerx,
                 opwallpower,
                 alpha=0.7,
                 label='Modified Wall Power')
        plt.xlabel('Time (Seconds)')
        plt.ylabel('Power (Watts)')
        plt.title('Wall Power')
        plt.legend()
        plt.ylim(bottom=0)
        plt.ylim(top=(max(opwallpower) + 50))
        plt.xlim(left=0)
        plt.xlim(right=max(opwallpowerx))
        plt.savefig('./tmp/wallpower_op.png', bbox_inches='tight')

        # Plot and save the l3 cache miss op figure.
        plt.figure(12)
        for i, y in enumerate(l3misscore):
            plt.plot(socketx,
                     y,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(socketx,
                     l3missmaster,
                     alpha=0.5,
                     label=('Original Master Core '
                            f'({config["app_master_core"]})'))
        for i, y in enumerate(opl3misscore):
            plt.plot(opsocketx,
                     y,
                     alpha=0.7,
                     label=f'Modified Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(opsocketx,
                     opl3missmaster,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L3 Miss Count')
        plt.title('L3 Cache Misses')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(opsocketx))
        plt.savefig('./tmp/l3miss_op.png', bbox_inches='tight')
        opl3misshtml = (
            '<h2>L3 Cache</h2>'
            '<img src="./tmp/l3miss_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            opl3misshtml += (f'<p>Master Core ({config["app_master_core"]}) '
                             f'L3 Misses: {opl3missmasteravg} '
                             f'({opl3missmasteravgdiff:+0.1f}%)</p>')
        for i, x in enumerate(opl3misscoreavg):
            opl3misshtml += (f'<p>Core {config["app_cores"][i]} '
                             f'L3 Misses: {x} '
                             f'({opl3misscoreavgdiff[i]:+0.1f}%)</p>')

        # Plot and save the l2 cache miss op figure.
        plt.figure(13)
        for i, y in enumerate(l2misscore):
            plt.plot(socketx,
                     y,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(socketx,
                     l2missmaster,
                     alpha=0.5,
                     label=('Original Master Core '
                            f'({config["app_master_core"]})'))
        for i, y in enumerate(opl2misscore):
            plt.plot(opsocketx,
                     y,
                     alpha=0.7,
                     label=f'Modified Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(opsocketx,
                     opl2missmaster,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L2 Miss Count')
        plt.title('L2 Cache Misses')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(opsocketx))
        plt.savefig('./tmp/l2miss_op.png', bbox_inches='tight')
        opl2misshtml = (
            '<h2>L2 Cache</h2>'
            '<img src="./tmp/l2miss_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            opl2misshtml += (f'<p>Master Core ({config["app_master_core"]}) '
                             f'L2 Misses: {opl3missmasteravg} '
                             f'({opl2missmasteravgdiff:+0.1f}%)</p>')
        for i, x in enumerate(opl2misscoreavg):
            opl2misshtml += (f'<p>Core {config["app_cores"][i]} '
                             f'L2 Misses: {x} '
                             f'({opl2misscoreavgdiff[i]:+0.1f}%)</p>')

        # Plot and save the l3 cache hit op figure.
        plt.figure(14)
        for i, y in enumerate(l3hitcore):
            plt.plot(socketx,
                     y,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(socketx,
                     l3hitmaster,
                     alpha=0.5,
                     label=(f'Original Master Core '
                            f'({config["app_master_core"]})'))
        for i, y in enumerate(opl3hitcore):
            plt.plot(opsocketx,
                     y,
                     alpha=0.5,
                     label=f'Modified Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(opsocketx,
                     opl3hitmaster,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L3 Hit (%)')
        plt.title('L3 Cache Hits')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(opsocketx))
        plt.savefig('./tmp/l3hit_op.png', bbox_inches='tight')
        opl3hithtml = (
            '<img src="./tmp/l3hit_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            opl3hithtml += (f'<p>Master Core ({config["app_master_core"]}) '
                            f'L3 Hits: {opl3hitmasteravg}% '
                            f'({opl3hitmasteravgdiff:+0.1f}%)</p>')
        for i, x in enumerate(opl3hitcoreavg):
            opl3hithtml += (f'<p>Core {config["app_cores"][i]} L3 Hits: {x}% '
                            f'({opl3hitcoreavgdiff[i]:+0.1f}%)</p>')

        # Plot and save the l2 cache hit op figure.
        plt.figure(15)
        for i, y in enumerate(l2hitcore):
            plt.plot(socketx,
                     y,
                     alpha=0.7,
                     label=f'Original Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(socketx,
                     l2hitmaster,
                     alpha=0.5,
                     label=('Original Master Core '
                            f'({config["app_master_core"]})'))
        for i, y in enumerate(opl2hitcore):
            plt.plot(opsocketx,
                     y,
                     alpha=0.7,
                     label=f'Modified Core {config["app_cores"][i]}')
        if config["app_master_enabled"] is True:
            plt.plot(opsocketx,
                     opl2hitmaster,
                     alpha=0.5,
                     label=('Modified Master Core '
                            f'({config["app_master_core"]})'))
        plt.xlabel('Time (Seconds)')
        plt.ylabel('L2 Hit (%)')
        plt.title('L2 Cache Hits')
        plt.legend()
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        plt.xlim(right=max(opsocketx))
        plt.savefig('./tmp/l2hit_op.png', bbox_inches='tight')
        opl2hithtml = (
            '<img src="./tmp/l2hit_op.png" style="max-width: 650px"/>')
        if config["app_master_enabled"] is True:
            opl2hithtml += (f'<p>Master Core ({config["app_master_core"]}) '
                            f'L2 Hits: {opl2hitmasteravg}% '
                            f'({opl2hitmasteravgdiff:+0.1f}%)</p>')
        for i, x in enumerate(opl2hitcoreavg):
            opl2hithtml += (f'<p>Core {config["app_cores"][i]} L2 Hits: '
                            f'{x}% ({opl2hitcoreavgdiff[i]:+0.1f}%)</p>')

        optelemhtml = ''
        optelemdatapoints = 0
        if config['telemetry'] is True:
            optelemdata = pandas.read_csv('tmp/telemetry_op.csv',
                                          sep=',',
                                          low_memory=False)
            optelemdatapoints = optelemdata.shape[0] * optelemdata.shape[1]
            optelempkts = np.asarray(
                optelemdata['tx_good_packets'].tolist()).astype(int)
            optelembytes = np.asarray(
                optelemdata['tx_good_bytes'].tolist()).astype(int)
            optelemtime = np.asarray(
                optelemdata['time'].tolist()).astype(float)
            optelempktdist = (
                optelemdata.loc[:, ['tx_size_64_packets',
                                    'tx_size_65_to_127_packets',
                                    'tx_size_128_to_255_packets',
                                    'tx_size_256_to_511_packets',
                                    'tx_size_512_to_1023_packets',
                                    'tx_size_1024_to_1522_packets',
                                    'tx_size_1523_to_max_packets']
                                ].tail(1).values[0])
            optelempktsizes = ['64', '65 to 127', '128 to 255', '256 to 511',
                               '512 to 1024', '1024 to 1522', '1523 to max']
            optelemrxerrors = optelemdata.loc[:, 'rx_errors'].tail(1).values[0]
            optelemrxerrorsdiff = optelemrxerrors - telemrxerrors
            optelemrxerrorsbool = False
            optelemtxerrors = optelemdata.loc[:, 'tx_errors'].tail(1).values[0]
            optelemtxerrorsdiff = optelemtxerrors - telemtxerrors
            optelemtxerrorsbool = False
            optelemrxdropped = (
                optelemdata.loc[:, 'rx_dropped_packets'].tail(1).values[0])
            optelemrxdroppeddiff = optelemrxdropped - telemrxdropped
            optelemrxdroppedbool = False

            if int(optelemrxerrors) != 0:
                print('ERROR: RX errors occurred during this test (rx_errors:',
                      f'{optelemrxerrors})')
                optelemrxerrorsbool = True
            if int(optelemtxerrors) != 0:
                print('ERROR: TX errors occurred during this test (tx_errors:',
                      f'{optelemtxerrors})')
                optelemtxerrorsbool = True

            if int(optelemrxdropped) != 0:
                print('ERROR: RX Packets were dropped during this test',
                      f'(rx_dropped_packets: {optelemrxdropped})')
                optelemrxdroppedbool = True

            # Generate an op figure for packet distribution.
            plt.figure(16)
            x = np.arange(optelempktdist.size)
            plt.bar(x, height=optelempktdist)
            plt.xticks(x, optelempktsizes, rotation=45)
            plt.xlabel('Packet Sizes (Bytes)')
            plt.ylabel('Packets')
            plt.title('Packet Size Distribution')
            plt.savefig('./tmp/pktdist_op.png', bbox_inches='tight')

            optelembyteszero = optelembytes[0]
            optelembytesreset = []
            for y in optelembytes:
                optelembytesreset.append(y - optelembyteszero)

            optelemgbytes = [x / 1000000000 for x in optelembytesreset]

            optelemgbytesmax = np.round(max(optelemgbytes), 1)
            optelemgbytesmaxdiff = (
                np.round(optelemgbytesmax - telemgbytesmax, 1))

            optelempktszero = optelempkts[0]
            optelempktsreset = []
            for y in optelempkts:
                optelempktsreset.append(y - optelempktszero)

            optelempktsresetmax = max(optelempktsreset)
            optelempktsresetmaxdiff = (
                np.round(optelempktsresetmax - telempktsresetmax, 1))

            plt.figure(17)
            _, ax1 = plt.subplots()
            ax2 = ax1.twinx()
            ax1.plot(optelemtime,
                     optelemgbytes,
                     alpha=1,
                     label='Data Transferred')
            ax2.plot(optelemtime,
                     optelempktsreset,
                     alpha=0.6,
                     color='orange',
                     label='Packets Transferred')
            ax1.set_xlabel('Time (Seconds)')
            ax1.set_ylabel('Data Transferred (GB)')
            ax2.set_ylabel('Packets Transferred (Packets)')
            ax1.set_ylim(bottom=0)
            ax2.set_ylim(bottom=0)
            ax1.legend(loc=2)
            ax2.legend(loc=1)
            plt.title('Data/Packets Transferred')
            plt.xlim(left=0)
            plt.xlim(right=max(optelemtime))
            plt.savefig('./tmp/transfer_op.png', bbox_inches='tight')

            optelempktssec = []
            for i, y in enumerate(optelempktsreset):
                if i != 0 and i != 1:
                    optelempktssec.append(
                        (y - optelempktsreset[i - 1]) /
                        config['test_step_size'])
                elif i == 1:
                    val = ((y - optelempktsreset[i - 1]) /
                           config['test_step_size'])
                    optelempktssec.append(val)
                    optelempktssec[0] = val
                else:
                    optelempktssec.append(0)

            optelempktsecavg = np.round(np.mean(optelempktssec), 0)
            optelempktsecavgdiff = (
                np.round(optelempktsecavg - telempktsecavg, 0))

            optelemthroughput = []
            for i, y in enumerate(optelembytesreset):
                if i != 0 and i != 1:
                    optelemthroughput.append(
                        (y - optelembytesreset[i - 1])
                        / 1000000000 * 8 / config['test_step_size'])
                elif i == 1:
                    val = ((y - optelembytesreset[i - 1])
                           / 1000000000 * 8 / config['test_step_size'])
                    optelemthroughput.append(val)
                    optelemthroughput[0] = val
                else:
                    optelemthroughput.append(0)

            optelemthroughputavg = np.round(np.mean(optelemthroughput), 2)
            optelemthroughputavgdiff = np.round(
                optelemthroughputavg - optelemthroughputavg, 2)

            # Generate am op figure for throughput and pps.
            plt.figure(18)
            fig, ax1 = plt.subplots()
            ax2 = ax1.twinx()
            ax1.plot(telemtime,
                     telemthroughput,
                     alpha=0.7,
                     label='Original Throughput')
            ax1.plot(optelemtime,
                     optelemthroughput,
                     alpha=0.7,
                     label='Modified Throughput')
            ax2.plot(telemtime,
                     telempktssec,
                     alpha=0.7,
                     color='red',
                     label='Original Packets Per Second')
            ax2.plot(optelemtime,
                     optelempktssec,
                     alpha=0.7,
                     color='green',
                     label='Modified Packets Per Second')
            ax1.set_xlabel('Time (Seconds)')
            ax1.set_ylabel('Throughput (Gbps)')
            ax2.set_ylabel('Packets Per Second (Packets)')
            ax1.set_ylim(bottom=0)
            ax2.set_ylim(bottom=0)
            ax2.set_ylim(top=max(optelempktssec) + 1000000)
            ax1.set_ylim(top=max(optelemthroughput) + 1)
            ax1.legend(loc=3)
            ax2.legend(loc=4)
            plt.title('Transfer Speeds')
            plt.xlim(left=0)
            plt.xlim(right=max(optelemtime))
            plt.savefig('./tmp/speeds_op.png', bbox_inches='tight')

            optelemhtml += (
                '<h2>Telemetry</h2>'
                '<img src="./tmp/pktdist_op.png" style="max-width: 650px"/>'
                '<p></p><img src="./tmp/transfer_op.png" '
                'style="max-width: 650px"/>'
                f'<p>Total Data Transferred: {optelemgbytesmax}GB '
                f'({optelemgbytesmaxdiff:+0.1f}GB)</p>'
                '<p>Total Packets Transferred: '
                f'{format(optelempktsresetmax, ",")}'
                f' packets ({optelempktsresetmaxdiff:+0,.0f} packets)</p>'
                '<img src="./tmp/speeds_op.png" style="max-width: 650px"/>'
                f'<p>Average Throughput: {optelemthroughputavg} Gbps '
                f'({optelemthroughputavgdiff:+0.2f}Gbps)</p>'
                '<p>Average Packets Per Second: '
                f'{format(optelempktsecavg, ",")}'
                f' pps ({optelempktsecavgdiff:+0,.0f} pps)</p>')

            optelemhtml += (
                '<p><a href="./tmp/telemetry_op.csv" class="btn btn-info" '
                'role="button">Download Full Telemetry CSV</a></p>'
                '<h2>Errors</h2>')

            if optelemrxerrorsbool is False:
                optelemhtml += (
                    '<h3 style="color:green;font-weight:bold;">RX Errors: '
                    f'{optelemrxerrors} ({optelemrxerrorsdiff:+0d})</h3>')
            else:
                optelemhtml += (
                    '<h3 style="color:red;font-weight:bold;">RX Errors: '
                    f'{optelemrxerrors} ({optelemrxerrorsdiff:+0d})</h3>')
            if optelemtxerrorsbool is False:
                optelemhtml += (
                    '<h3 style="color:green;font-weight:bold;">TX Errors: '
                    f'{optelemtxerrors} ({optelemtxerrorsdiff:+0d})</h3>')
            else:
                optelemhtml += (
                    '<h3 style="color:red;font-weight:bold;">TX Errors: '
                    f'{optelemtxerrors} ({optelemtxerrorsdiff:+0d})</h3>')

            if optelemrxdroppedbool is False:
                optelemhtml += (
                    '<h3 style="color:green;font-weight:bold;">'
                    f'RX Dropped Packets: {optelemrxdropped} '
                    f'({optelemrxdroppeddiff:+0d})</h3>')
            else:
                optelemhtml += (
                    '<h3 style="color:red;font-weight:bold;">'
                    f'RX Dropped Packets: {optelemrxdropped} '
                    f'({optelemrxdroppeddiff:+0d})</h3>')
        else:
            optelemhtml += (
                '<h2>Telemetry</h2><p style="color:red">'
                'Telemetry is disabled</p>')

        oprechtml = "<h2>Optimisation Recommendations</h2>"
        # Generate op recommendations.
        # If the mem b/w has improved while there was no decrease in throughput
        #   and no errors or drops, then recommend mem op if not dont.
        if ((opsocketreadavgdiff < -25.0) and (opsocketwriteavgdiff < -25.0)
                and (optelemthroughputavgdiff > -0.2)
                and optelemrxdropped <= 0):
            oprechtml += (
                '<p>It is recommended to change from ring mempools to stack '
                'mempools based on the optimisation results.<br/>'
                'This can be done by setting '
                'RTE_MBUF_DEFAULT_MEMPOOL_OPS="stack" '
                'in the DPDK /config/rte_config.h file.</br>'
                'Please manually review this report to confirm that this '
                'recommendation is right for your project.</p>')
        else:
            oprechtml += (
                '<p>It is recommended not to change from ring mempools to '
                'stack mempools based on the optimisation results</p>')

        # Generate optimisation html.
        ophtml = (
            '<div class="row mt-5" style="page-break-after: always;">'
            f'{opmembwhtml}</div>'
            '<div class="row mt-5" style="page-break-after: always;">'
            f'{opwallpowerhtml}</div><div class="row mt-5" '
            f'style="page-break-after: always;">{opl3misshtml}</div>'
            f'<div class="row" style="page-break-after: always;">{opl3hithtml}'
            f'</div><div class="row mt-5" style="page-break-after: always;">'
            f'{opl2misshtml}</div><div class="row"'
            f'style="page-break-after: always;">{opl2hithtml}</div>'
            f'<div class="row mt-5">{optelemhtml}</div>'
            '<div class="row mt-5" style="page-break-after: always;">'
            f'{oprechtml}</div>')

        # Calculate op datapoints.
        opdatapoints = oppcmdatapoints + opwallpdatapoints + optelemdatapoints

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
        dpdkrebuild = subprocess.Popen(f'cd {config["dpdk_location"]}; '
                                       f'{config["dpdk_build_cmd"]};',
                                       shell=True,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        # Building animation.
        animation = '|/-\\'
        idx = 0
        buildtime = 0.0
        while dpdkrebuild.poll() is None:
            m, s = divmod(int(buildtime), 60)
            print('Building . . .',
                  f'{m:02d}:{s:02d}',
                  animation[idx % len(animation)],
                  end='\r')
            idx += 1
            buildtime += 0.1
            time.sleep(0.1)

    # If no op steps are enabled then dont run optimisation.
    elif stepsenabled is False:
        print('\nNo Optimisation Steps are enabled skipping optimisation')

    print('\n\nGenerating report')

    # Sum all datapoints used in report.
    datapoints = (
        pcmdatapoints + wallpdatapoints + telemdatapoints + opdatapoints)

    # Get report generation time in 2 formats
    reporttime1 = strftime('%I:%M%p on %d %B %Y', gmtime())
    reporttime2 = strftime('%I:%M%p %d/%m/%Y', gmtime())

    # If a project name is specified add it to the report.
    projectdetailshtml = ''
    if config['project_name']:
        projectdetailshtml += (
            '<p style="font-size: 18px;">'
            f'Project: {config["project_name"]}</p>')
    # If a tester is specified add their details to the report.
    if config['tester_name'] and config['tester_email']:
        projectdetailshtml += ('<p style="font-size: 18px;">'
                               f'Tester: {config["tester_name"]} '
                               f'({config["tester_email"]})</p>')

    # If op enabled then split the report under 2 main headings.
    testheader1 = ''
    testheader2 = ''
    if config['op_enabled'] is True:
        testheader1 = (
            '<div class="row mt-5"><h1 style="font-weight:bold;">'
            'Original DPDK App</h1></div>')
        testheader2 = (
            '<div class="row mt-5"><h1 style="font-weight:bold;">'
            'Modified DPDK App</h1></div>')

    # Generate acknowledgement html if enabled.
    reportheader = ''
    ackhtml = ''
    if config['doat_ack'] is True:
        reportheader = (
            '<img src="./webcomponents/doat_logo.png" height="49px" '
            'name="logo" style="margin-bottom: 11px;"/> Report')
        ackhtml = (
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
        reportheader = 'DOAT Report'

    # Create a html file to save the html report.
    indexfile = open('index.html', 'w')
    jsontable = ''
    if JSON2HTML_AVAILABLE:
        jsontable = ((json2html.convert(json=(str(
            {section: dict(config['full_json'][section])
             for section in config['full_json'].sections()}
            )).replace("\'", "\""))).replace("border=\"1\"", "")).replace(
                "table", "table class=\"table\"", 1)
    else:
        jsontable = ('<p>The json2html python module must be installed to '
                     'show the test configuration.</p>')
    # Write all parts of the report to the html file.
    indexfile.write(
        '<html><head><title>DOAT Report</title><link rel="stylesheet"'
        'href="./webcomponents/bootstrap.513.min.css">'
        '</script><script src="./webcomponents/bootstrap.513.min.js"></script>'
        '<style>@media print{a:not([name="git"]){display:none!important}'
        'img:not([name="logo"]){max-width:100%!important}}</style></head>'
        f'<body><div class="p-5 bg-light text-center"><h1>{reportheader}</h1>'
        '<p style="font-size: 14px">DPDK Optimisation & Analysis Tool</p>'
        f'<p>Report compiled at {reporttime1} using {format(datapoints, ",")} '
        f'data points</p>{projectdetailshtml}</div><div class="container">'
        f'{testheader1}'
        f'<div class="row mt-5" style="page-break-after: always;">{membwhtml}'
        '</div><div class="row mt-5" style="page-break-after: always;">'
        f'{wallpowerhtml}</div><div class="row mt-5" style="page-break-after: '
        f'always;">{l3misshtml}</div><div class="row" '
        f'style="page-break-after: always;">{l3hithtml}</div><div '
        f'class="row mt-5" style="page-break-after: always;">{l2misshtml}'
        '</div><div class="row" style="page-break-after: always;">'
        f'{l2hithtml}</div><div class="row mt-5" style="page-break-after:'
        f' always;">{telemhtml}</div>'
        f'{testheader2}'
        f'{ophtml}'
        '<div class="row mt-5"><h2>Test Configuration</h2>'
        f'{jsontable}'
        f'</div><div class="row mt-5">{ackhtml}</div><br/>'
        f'<div class="row mt-5">{reporthtml}</div></div></body></html>')
    # Close the html file.
    indexfile.close()

    # If PDF generation is on then generate the PDF report using the
    #   pdfkit (wkhtmltopdf).
    if config['generate_pdf'] is True:
        pdfoptions = {'page-size': 'A4',
                      'quiet': '',
                      'margin-top': '19.1',
                      'margin-right': '25.4',
                      'margin-bottom': '25.4',
                      'margin-left': '25.4',
                      'encoding': "UTF-8",
                      'footer-right': 'Page [page] of [topage]',
                      'footer-left': reporttime2,
                      'footer-line': '',
                      'print-media-type': ''
                      }
        wkhtmltopdfloc = subprocess.check_output(
            'which wkhtmltopdf', shell=True).decode(
                sys.stdout.encoding).strip()
        pdfconfig = pdfkit.configuration(wkhtmltopdf=wkhtmltopdfloc)
        pdfkit.from_file('index.html',
                         './tmp/doatreport.pdf',
                         configuration=pdfconfig,
                         options=pdfoptions)

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
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    # Try to serve the report forever until exception.
    try:
        httpd.serve_forever()
    except Exception:
        httpd.server_close()


if __name__ == '__main__':
    main()
