#!/usr/bin/env python3

"""

 doatFunctions.py

 This file contains several support functions for DOAT

 Usage:
        These functions should not be directly invoked by a user

 Copyright (c) 2020 Conor Walsh
 DOAT is licensed under an MIT license (see included license file)

"""

import os
import sys
from tqdm import tqdm
import time
import signal
import datetime


# Function to check if a process with a given PID is still alive
def check_pid(pid):
    # Try to send the process a signal (0 will not kill the process)
    try:
        os.kill(pid, 0)
    # If the OS cant complete the action the process doesnt exist (or is dead)
    except OSError:
        return False
    # If the signal can be sent the process exists (or is still alive)
    else:
        return True


# Function to print a startup message to the terminal
def doat_motd():
    # Get the current time
    now = datetime.datetime.now()
    # Print the DOAT ASCII
    print("         _____   ____       _______ ")
    print("        |  __ \ / __ \   /\|__   __|")
    print("        | |  | | |  | | /  \  | |   ")
    print("        | |  | | |  | |/ /\ \ | |   ")
    print("        | |__| | |__| / ____ \| |   ")
    print("        |_____/ \____/_/    \_\_|   ")
    print("   DPDK Optimisation and Analysis Tool")
    # Print Author and Year
    print("          (c) Conor Walsh "+str(now.year)+"\n")
    print("           Release Candidate 1")
    print("          Not for production use")
    print("             DO NOT DEPLOY!\n")


# Function to check if the required environment variables are set
def sys_check():
    # Abort if RTE_SDK is not set
    if "RTE_SDK" not in os.environ:
        sys.exit("RTE_SDK has not been set, ABORT!")
    # Abort if RTE_TARGET is not set
    if "RTE_TARGET" not in os.environ:
        sys.exit("RTE_TARGET has not been set, ABORT!")
    # Alert user if the checks have passed
    print("System Checks PASSED")


# Function to make the program wait for a set number of seconds
#   and display a progressbar to the user
def progress_bar(seconds):
    for x in tqdm(range(seconds, 0, -1)):
        time.sleep(1)


# Function to kill a process and all of its children using PID
def kill_group_pid(pid):
    os.killpg(os.getpgid(pid), signal.SIGTERM)
