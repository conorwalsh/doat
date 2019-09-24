#!/usr/bin/env python3
import os
from doatFunctions import *
import signal
import subprocess
import time
from tqdm import tqdm

doat_motd()

print("Starting Process")

FNULL = open(os.devnull, 'w')
proc = subprocess.Popen("/root/walshc/dpdk/examples/qos_sched_custom/run.sh", stdout=FNULL, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setsid) 
testpid = proc.pid

if check_pid(testpid):
    print("Process started, PID: ",testpid)
else:
    sys.exit("Test process failed to start, ABORT!")

print("Allow application to startup . . .")

for x in tqdm(range(10, 0, -1)):
    time.sleep(1)

print("Running Test . . .")

for x in tqdm(range(30, 0, -1)):
    #print("Time left: ",x," seconds")
    time.sleep(1)

print("Attempting to kill test process")
os.killpg(os.getpgid(testpid), signal.SIGTERM)

print("Exiting . . .")
