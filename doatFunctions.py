#!/usr/bin/env python
import os
import sys
from tqdm import tqdm
import time
import signal

#https://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python/6940314
def check_pid(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

def doat_motd():
    print("         _____   ____       _______ \n        |  __ \ / __ \   /\|__   __|\n        | |  | | |  | | /  \  | |   \n        | |  | | |  | |/ /\ \ | |   \n        | |__| | |__| / ____ \| |   \n        |_____/ \____/_/    \_\_|   \n                                \n   DPDK Optimisation and Analysis Tool\n            Conor Walsh 2019\n")
    print("         Proof of Concept Version\n         Not for production use\n             DO NOT DEPLOY!\n")
    
def sys_check():
    if "RTE_SDK" not in os.environ:
        sys.exit("RTE_SDK has not been set, ABORT!")
    if "RTE_TARGET" not in os.environ:
        sys.exit("RTE_TARGET has not been set, ABORT!")
    print("System Checks PASSED")

def progress_bar(seconds):
    for x in tqdm(range(seconds, 0, -1)):
        time.sleep(1)

def kill_group_pid(pid):
    os.killpg(os.getpgid(pid), signal.SIGTERM)
