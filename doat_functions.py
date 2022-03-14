#!/usr/bin/env python3

"""

 doat_functions.py

 This file contains several support functions for DOAT

 Usage:
        These functions should not be directly invoked by a user

 Copyright (c) 2021 Conor Walsh
 DOAT is licensed under an MIT license (see included license file)

"""

# Import standard modules.
import datetime
import os
import re
import signal
import subprocess
import sys
import time

# Import third-party modules.
try:
    import configparser
except ImportError:
    sys.exit('The python module \'configparser\' must be installed to use '
             'DOAT.\nInstall it using pip or the supplied requirements.txt')
try:
    from tqdm import tqdm
    TQDM_ENABLED = True
except ImportError:
    TQDM_ENABLED = False


def check_pid(pid):
    """
    Function to check if a process with a given PID is still alive.

    :param pid: The PID of the desired function.
    :return: True if the PID is up or False if not
    """
    # Try to send the process a signal (0 will not kill the process)
    try:
        os.kill(pid, 0)
    # If the OS can't complete the action the process doesn't exist or is dead
    except OSError:
        return False
    # If the signal can be sent the process exists (or is still alive)
    else:
        return True


def doat_motd():
    """
    Function to print a startup message to the terminal.

    :param: This function takes no arguments.
    :return: This function has no return value.
    """
    # Get the current time
    now = datetime.datetime.now()
    # Get current version
    version_file = open('VERSION', 'r')
    lines = version_file.readlines()
    # Print the DOAT ASCII
    print(r'         _____   ____       _______ ')
    print(r'        |  __ \ / __ \   /\|__   __|')
    print(r'        | |  | | |  | | /  \  | |   ')
    print(r'        | |  | | |  | |/ /\ \ | |   ')
    print(r'        | |__| | |__| / ____ \| |   ')
    print(r'        |_____/ \____/_/    \_\_|   ')
    print(r'   DPDK Optimisation and Analysis Tool')
    # Print Author and Year
    print(f'          (c) Conor Walsh {now.year}\n')
    print(f'               Version {lines[0]}')


def progress_bar(seconds):
    """
    Function to make the program wait for a set number of seconds and display
    a progressbar to the user.

    :param seconds: The number of seconds that the progressbar will run for.
    :return: This function has no return value.
    """
    # Use TQDM to show progress if available.
    if TQDM_ENABLED:
        for _ in tqdm(range(seconds, 0, -1)):
            time.sleep(1)
    else:
        for sec in range(seconds, 0, -1):
            print(f'{sec} seconds left: '
                  f'{int(((seconds-sec)/seconds)*100)}%    ',
                  end='\r')
            time.sleep(1)


def kill_group_pid(pid):
    """
    Function to kill a process and all of its children using PID.

    :param pid: The PID of the desired function.
    :return: This function has no return value.
    """
    os.killpg(os.getpgid(pid), signal.SIGTERM)


def safe_exit():
    """
    Once Test Process is spawned add catch to kill test process and cleanup
        if test is abandoned.

    :param: This function takes no arguments.
    :return: This function has no return value.
    """

    try:
        # Remove test results from tmp directory and index.html.
        os.system('rm -rf tmp')
        os.remove('index.html')
    except OSError as err:
        print('Failed to remove temporary files', err)

    print('\nExiting . . .')


def doat_config(config_file):
    """
    Function to parse all DOAt configuration options.

    :param config_file: The name of the required config file.
    :return: Dictionary with all the required config options.
    """
    # Import main to get global variables.
    import main

    # Dictionary to store the returnable values
    config = {}

    # Declare parser and read in config.cfg.
    config_parsed = configparser.ConfigParser()
    config_parsed.read(config_file)

    # Store the full json to use for the test configuration in the report.
    config['full_json'] = config_parsed

    # Read and store value for startuptime (will abort if not present).
    # This is the time in seconds that you want to allow for your app
    #   to stabilise.
    config['startup_time'] = config_parsed['DOAT'].get('startuptime')
    if config['startup_time']:
        config['startup_time'] = int(config['startup_time'])
        print('Startup time for DPDK App:', config['startup_time'])
    else:
        sys.exit('No startup time was specified (startuptime in config.cfg), '
                 'ABORT!')

    # Read and store value for testruntime (will abort if not present).
    # This is the time in seconds that you want the test to run for.
    config['test_runtime'] = config_parsed['DOAT'].get('testruntime')
    if config['test_runtime']:
        config['test_runtime'] = int(config['test_runtime'])
        print('Run time for Test:', config['test_runtime'])
    else:
        sys.exit('No test run time was specified (testruntime in config.cfg), '
                 'ABORT!')

    # Read and store value for teststepsize (will abort if not present).
    # This is the resolution of the test in seconds.
    config['test_step_size'] = config_parsed['DOAT'].get('teststepsize')
    if config['test_step_size']:
        config['test_step_size'] = float(config['test_step_size'])
        print('Step size for Test:', config['test_step_size'])
    else:
        sys.exit('No test run time was specified (testruntime in config.cfg), '
                 'ABORT!')

    # Read and store value for serverport (will abort if not present).
    # This is the port that the results server will run on.
    config['server_port'] = config_parsed['DOAT'].get('serverport')
    if config['server_port']:
        config['server_port'] = int(config['server_port'])
        print('Results server port:', config['server_port'])
    else:
        sys.exit('No server port was specified (serverport in config.cfg), '
                 'ABORT!')

    # Read and store value for projectname.
    # This specifies the name of the project for the report.
    #   This can be left blank if not required.
    config['project_name'] = config_parsed['REPORTING'].get('projectname')
    if config['project_name'] and config['project_name'] != '':
        print('\nProject Name:', config['project_name'])
    else:
        config['project_name'] = None
        print('No project name was specified (projectname in config.cfg), '
              'continuing without')

    # Read and store value for testername and testeremail.
    # This specifies the name and email of the tester for traceability.
    #   These can be left blank if not required.
    config['tester_name'] = config_parsed['REPORTING'].get('testername')
    config['tester_email'] = config_parsed['REPORTING'].get('testeremail')
    if (config['tester_name'] and config['tester_email'] and
            config['tester_name'] != '' and config['tester_email'] != ''):
        print('Tester:', config['tester_name'], '-', config['tester_email'])
    else:
        config['tester_name'] = None
        config['tester_email'] = None
        print('Tester name and/or email was not specified (testername & '
              'testeremail in config.cfg), continuing without')

    # Read and store value for generatepdf.
    # This sets if a PDF report will be generated or not.
    config['generate_pdf'] = False
    if (config_parsed['REPORTING'].getboolean('generatepdf') is True and
            main.PDFKIT_AVAILABLE is True):
        config['generate_pdf'] = True
        print('PDF report generation is enabled')
    else:
        print('PDF report generation is disabled')

    # Read and store value for generatezip.
    # This sets if a ZIP Archive will be generated or not.
    config['generate_zip'] = False
    if config_parsed['REPORTING'].getboolean('generatezip') is True:
        config['generate_zip'] = True
        print('ZIP Archive generation is enabled')
    else:
        print('ZIP Archive generation is disabled')

    # Read and store value for doatack.
    # This sets if doat will be acknowledged in the reports.
    config['doat_ack'] = False
    if config_parsed['REPORTING'].getboolean('doatack') is True:
        config['doat_ack'] = True
        print('The DOAT Project will be acknowledged in the report')
    else:
        print('The DOAT Project will not be acknowledged in the report')

    # Read and store value for dpdklocation.
    # This is the root path of DPDK.
    config['dpdk_location'] = config_parsed['APPPARAM'].get('dpdklocation')
    if config['dpdk_location'] and config['dpdk_location'] != '':
        print('\nDPDK Location:', config['dpdk_location'])
    else:
        sys.exit('No DPDK location was specified (dpdklocation in config.cfg),'
                 ' ABORT!')

    # Read and store value for appcmd (will abort if not present).
    # This is the command or script used to launch your DPDK app.
    config['app_cmd'] = config_parsed['APPPARAM'].get('appcmd')
    if config['app_cmd']:
        print('DPDK app launch command:', config['app_cmd'])
    else:
        sys.exit('No DPDK command was specified (appcmd in config.cfg), '
                 'ABORT!')

    # Read and store value for telemetryenabled.
    # If telemetry statistics are required they can be enabled here.
    # If DPDK telemetry is not compiled telemetry will not be enabled.
    config['telemetry'] = False
    if config_parsed['APPPARAM'].getboolean('telemetry') is True:
        config['telemetry'] = True
        print('DPDK telemetry is enabled')
    else:
        print('DPDK telemetry is disabled')

    # Read and store value for telemetryport.
    if config['telemetry'] is True:
        config['telemetry_port'] = (
            config_parsed['APPPARAM'].get('telemetryport'))
        if config['telemetry_port']:
            config['telemetry_port'] = int(config['telemetry_port'])
            print('DPDK telemetry port:', config['telemetry_port'])
        else:
            sys.exit('No port was specified for telemetry (telemetryport in '
                     'config.cfg), ABORT!')

    # Read and store value for openabled.
    # To run optimisation it is enabled here.
    config['op_enabled'] = False
    if config_parsed['OPTIMISATION'].getboolean('optimisation') is True:
        config['op_enabled'] = True
        print('\nOptimisation is enabled')
    else:
        print('\nOptimisation is disabled')

    # Read and store value for dpdkbuildcmd
    #   (will abort if not present and optimisation enabled).
    # The command that is run in $RTE_SDK to build DPDK.
    config['dpdk_build_cmd'] = (
        config_parsed['OPTIMISATION'].get('dpdkbuildcmd'))
    if config['dpdk_build_cmd'] and config['op_enabled'] is True:
        print('DPDK Build Command:', config['dpdk_build_cmd'])
    elif config['op_enabled'] is True:
        sys.exit('Optimisation is enabled but dpdkbuildcmd in config.cfg has '
                 'not been set, ABORT!')

    # Read and store value for memop.
    # If this is enabled the memory optimisation step will be run.
    # In order to use this the DPDK build must be configured correctly
    #   will abort if any of the configuration options are incorrect
    #   instructions are given to the user about how to rectify the problem.
    config['mem_op'] = False
    config['cache_new'] = ''
    config['cache_orig'] = ''
    config['cache_adjust'] = False
    if (config_parsed['OPTIMISATION'].getboolean('memop') is True and
            config['op_enabled'] is True):
        memdriver = subprocess.check_output(
            f'cat {config["dpdk_location"]}/config/rte_config.h | '
            'grep -m1 RTE_MBUF_DEFAULT_MEMPOOL_OPS ',
            shell=True).decode(sys.stdout.encoding).rstrip().strip()
        config['cache_orig'] = (
            str(re.sub('[^0-9]',
                       '',
                       subprocess.check_output(
                           f'cat {config["dpdk_location"]}/config/'
                           'rte_config.h | grep -m1 '
                           'RTE_MEMPOOL_CACHE_MAX_SIZE ',
                           shell=True).decode(sys.stdout.encoding).strip())))
        if 'ring_mp_mc' in memdriver:
            config['mem_op'] = True
            print('Memory Optimisation Step is enabled')
            if config_parsed['OPTIMISATION'].getboolean('cacheadjust') is True:
                config['cache_new'] = (
                    config_parsed['OPTIMISATION'].get('newcache', 256))
                config['cache_adjust'] = True
                print('Mempool cache will be adjusted as part of the '
                      'Memory Optimisation Step. New Cache Size:',
                      config['cache_new'],
                      '\b, Original Cache Size:',
                      config['cache_orig'])
            else:
                print('Mempool cache will not be adjusted as part of the '
                      'Memory Optimisation Step')
        elif 'ring_mp_mc' not in memdriver:
            print('Memory Optimisation Step is disabled',
                  '(RTE_MBUF_DEFAULT_MEMPOOL_OPS is not set to ring, set',
                  'RTE_MBUF_DEFAULT_MEMPOOL_OPS=\"ring_mp_mc\")')
    elif config['op_enabled'] is True:
        print('Memory Optimisation Step is disabled')

    # Read and store value for testcore.
    # This core will run the test software.
    #   (If more than 1 socket use socket not running DPDK app).
    config['test_core'] = config_parsed['CPU'].get('testcore')

    # Read and store value for testsocket using the value for testcore.
    # This is the socket the tests will run on.
    config['test_socket'] = int(subprocess.check_output(
        r"cat /proc/cpuinfo | grep -A 18 'processor\s\+: "
        f"{config['test_core']}' | grep 'physical id' | head -1 | awk "
        r"'{print substr($0,length,1)}'",
        shell=True))

    # Abort test if the testcore is not specified.
    if config['test_core']:
        config['test_core'] = int(config['test_core'])
        print('\nTest software core:',
              config['test_core'],
              '(Socket:',
              f'{config["test_socket"]})')
    else:
        sys.exit('No test core was specified (testcore in config.cfg), ABORT!')

    # Read and store value for appmaster.
    # This is the master core of the DPDK app.
    config['app_master_enabled'] = True
    config['app_master_core'] = config_parsed['CPU'].get('appmaster')
    # Find the socket that the master core runs on.
    config['app_master_socket'] = int(subprocess.check_output(
        r"cat /proc/cpuinfo | grep -A 18 'processor\s\+: "
        f"{config['app_master_core']}' | grep 'physical id' | head -1 "
        r"| awk '{print substr($0,length,1)}'",
        shell=True))
    if config['app_master_core']:
        config['app_master_core'] = int(config['app_master_core'])
        print('DPDK app master core:',
              config['app_master_core'],
              '(Socket:',
              f'{config["app_master_socket"]})')
    else:
        config['app_master_enabled'] = False
        print('DPDK app has no master core')

    # Read and store value for includemaster.
    # If stats from the master core are required in the report set it here.
    if config_parsed['REPORTING'].getboolean('includemaster') is False:
        config['app_master_enabled'] = False
        print('DPDK app master core will not be included in reports')

    # Read and store value for appcores (will abort if not present).
    # These are the cores that the DPDK app runs on.
    config['app_cores'] = config_parsed['CPU'].get('appcores')
    config['app_cores_no'] = 0
    if config['app_cores']:
        config['app_cores'] = [int(e) for e in config['app_cores'].split(',')]
        config['app_cores_no'] = len(config['app_cores'])
        print('DPDK app has',
              config['app_cores_no'],
              'cores:',
              config['app_cores'])
    else:
        sys.exit('No DPDK app cores were specified (appcores in config.cfg), '
                 'ABORT!')

    # Find and store the values of the sockets that the DPDK app cores are on.
    config['app_cores_sockets'] = []
    for cores in config['app_cores']:
        config['app_cores_sockets'].append(int(subprocess.check_output(
            r"cat /proc/cpuinfo | grep -A 18 'processor\s\+: "
            f"{cores}' | grep 'physical id' | head -1 "
            r"| awk '{print substr($0,length,1)}'",
            shell=True)))

    # Check that all DPDK cores are on the same socket.
    # Will abort if the are not on the same socket as this is very bad
    #   for performance.
    config['app_socket'] = None
    if config['app_master_enabled']:
        if (all(x == config['app_cores_sockets'][0]
                for x in config['app_cores_sockets']) and
                config['app_master_socket'] == config['app_cores_sockets'][0]):
            config['app_socket'] = config['app_cores_sockets'][0]
            print('DPDK app running on socket', config['app_socket'])
        else:
            sys.exit('DPDK app cores and master core must be on the same '
                     'socket, ABORT!')
    else:
        if all(x == config['app_cores_sockets'][0]
               for x in config['app_cores_sockets']):
            config['app_socket'] = config['app_cores_sockets'][0]
            print('DPDK app running on socket', config['app_socket'])
        else:
            sys.exit('DPDK app cores must be on the same socket, ABORT!')

    # Read and store value for pcmdir (will abort if not present).
    # This is the path where you have installed PCM tools.
    config['pcm_dir'] = config_parsed['TOOLS'].get('pcmdir')
    if config['pcm_dir']:
        print('\nPCM directory:', config['pcm_dir'])
    else:
        sys.exit('No PCM directory was specified (pcmdir in config.cfg), '
                 'ABORT!')

    # Store the original cpu affinity that programs are launched with
    #   before we pin DOAT to a core this means we can unpin DOAT.
    config['cpu_aff_orig'] = subprocess.check_output(
        f'taskset -cp {os.getpid()}',
        shell=True).decode(
            sys.stdout.encoding).rstrip().split(':', 1)[-1].strip()
    print('\nOriginal CPU Affinity:', config['cpu_aff_orig'])

    # Return all config options in a dict
    return config
