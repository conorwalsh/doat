#!/usr/bin/env python3
import os
from doatFunctions import *
import signal
import subprocess
import time
from tqdm import tqdm
import configparser

#Print startup message
doat_motd()

#Check system setup
sys_check()

#Read and check config options from config file
print("Gathering configuration")
config = configparser.ConfigParser()
config.read('config.cfg')
dpdkcmd=config['DOAT']['dpdkcmd']
if dpdkcmd is not None:
    print("DPDK app launch command: ",dpdkcmd)
else:
    sys.exit("No DPDK command was specified (dpdkcmd in config.cfg), ABORT!")
startuptime=int(config['DOAT']['startuptime'])
if startuptime is not None:
    print("Startup time for DPDK App: ",startuptime)
else:
    sys.exit("No startup time was specified (startuptime in config.cfg), ABORT!")
testruntime=int(config['DOAT']['testruntime'])
if testruntime is not None:
    print("Startup time for DPDK App: ",testruntime)
else:
    sys.exit("No test run time was specified (testruntime in config.cfg), ABORT!")

print("Starting Process")
FNULL = open(os.devnull, 'w')
proc = subprocess.Popen(dpdkcmd, stdout=FNULL, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setsid) 
testpid = proc.pid

if check_pid(testpid):
    print("Test process starting")
else:
    sys.exit("Test process failed to start, ABORT!")

print("Allow application to startup . . .")

for x in tqdm(range(startuptime, 0, -1)):
    time.sleep(1)

if proc.poll() is not None:
    #os.killpg(os.getpgid(testpid), signal.SIGTERM)
    sys.exit("Application died or failed to start, ABORT!")
else:
    print("Test process started successfully, , PID: ",testpid)

print("Running Test . . .")

for x in tqdm(range(testruntime, 0, -1)):
    time.sleep(1)

if proc.poll() is None:
    print("SUCCESS: Test process is still alive after test")
else:
    print("ERROR: Test process died during test")

print("Killing test process")
os.killpg(os.getpgid(testpid), signal.SIGTERM)

print("Exiting . . .")
