#!/usr/bin/env python3

"""

 doat_functions.py

 This file contains several support functions for DOAT

 Usage:
        These functions should not be directly invoked by a user

 Copyright (c) 2021 Conor Walsh
 DOAT is licensed under an MIT license (see included license file)

"""

import datetime
import os
import signal
import time
from tqdm import tqdm


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
    for _ in tqdm(range(seconds, 0, -1)):
        time.sleep(1)


def kill_group_pid(pid):
    """
    Function to kill a process and all of its children using PID.

    :param pid: The PID of the desired function.
    :return: This function has no return value.
    """
    os.killpg(os.getpgid(pid), signal.SIGTERM)
