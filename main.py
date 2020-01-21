#!/usr/bin/env python3

from doatFunctions import *
import sys
import subprocess
import configparser
import pandas
import numpy as np
import atexit
import matplotlib.pyplot as plt
from http.server import SimpleHTTPRequestHandler, HTTPServer
from time import gmtime, strftime
import pdfkit
from json2html import *
import re
import string
import fileinput
from datetime import datetime
import time

# Print startup message
doat_motd()

# Check system setup
sys_check()

config = configparser.ConfigParser()
config.read('config.cfg')

startuptime = int(config['DOAT']['startuptime'])
if startuptime is not None:
    print("Startup time for DPDK App:", startuptime)
else:
    sys.exit("No startup time was specified (startuptime in config.cfg), ABORT!")

testruntime = int(config['DOAT']['testruntime'])
if testruntime is not None:
    print("Run time for Test:", testruntime)
else:
    sys.exit("No test run time was specified (testruntime in config.cfg), ABORT!")

teststepsize = float(config['DOAT']['teststepsize'])
if teststepsize is not None:
    print("Step size for Test:", teststepsize)
else:
    sys.exit("No test run time was specified (testruntime in config.cfg), ABORT!")

serverport = int(config['DOAT']['serverport'])
if serverport is not None:
    print("Results server port:", serverport)
else:
    sys.exit("No server port was specified (serverport in config.cfg), ABORT!")

projectname = config['REPORTING']['projectname']
if projectname is not None and projectname is not "":
    print("Project Name:", projectname)
else:
    print("No project name was specified (projectname in config.cfg), continuing without")

testername = config['REPORTING']['testername']
testeremail = config['REPORTING']['testeremail']
if testername is not None and testeremail is not None and testername is not "" and testeremail is not "":
    print("Tester:",testername,'-',testeremail)
else:
    testername = None
    testeremail = None
    print("Tester name and/or email was not specified (testername & testeremail in config.cfg), continuing without")

generatepdf = False
if config['REPORTING'].getboolean('generatepdf') is True:
    generatepdf = True
    print("PDF report geneneration is enabled")
else:
    print("PDF report geneneration is disabled")

generatezip = False
if config['REPORTING'].getboolean('generatezip') is True:
    generatezip = True
    print("ZIP Archive geneneration is enabled")
else:
    print("ZIP Archive geneneration is disabled")

rtesdk = os.environ['RTE_SDK']
print("RTE SDK:",rtesdk)

rtetarget = os.environ['RTE_TARGET']
print("RTE TARGET:",rtetarget)

appcmd = config['APPPARAM']['appcmd']
if appcmd is not None:
    print("DPDK app launch command:", appcmd)
else:
    sys.exit("No DPDK command was specified (appcmd in config.cfg), ABORT!")

applocation = config['APPPARAM']['applocation']
if applocation is not None:
    print("DPDK app location:",applocation)
else:
    sys.exit("No DPDK app location was specified (applocation in config.cfg), ABORT!")

telemenabledraw = subprocess.check_output("cat $RTE_SDK/config/common_base | grep CONFIG_RTE_LIBRTE_TELEMETRY", shell=True).decode(sys.stdout.encoding).rstrip().strip()[-1:]
telemetryenableddpdk = False
if telemenabledraw is "y":
    telemetryenableddpdk = True

telemetryenabled = False
if config['APPPARAM'].getboolean('telemetry') is True and telemetryenableddpdk is True:
    telemetryenabled = True
    print("DPDK telemetry is enabled")
elif telemetryenableddpdk is False:
    print("Telemetry is disabled in your build of DPDK set CONFIG_RTE_LIBRTE_TELEMETRY=y to use telemetry")
else:
    print("DPDK telemetry is disabled")

socketpath = config['APPPARAM']['socketpath']
if socketpath is not None and telemetryenabled is True:
    print("DPDK app telemetry socket path:", socketpath)
elif telemetryenabled is True:
    sys.exit("Telemetry is enabled but socketpath in config.cfg has not been set, ABORT!")

openabled = False
if config['OPTIMISATION'].getboolean('optimisation') is True:
    openabled = True
    print("Optimisation is enabled")
else:
    print("Optimisation is disabled")

dpdkmakecmd = config['OPTIMISATION']['dpdkmakecmd']
if dpdkmakecmd is not None and openabled is True:
    print("DPDK Make Command:",dpdkmakecmd)
elif openabled is True:
    sys.exit("Optimisation is enabled but dpdkmakecmd in config.cfg has not been set, ABORT!")

appmakecmd = config['OPTIMISATION']['appmakecmd']
if appmakecmd is not None and openabled is True:
    print("DPDK App Make Command:",appmakecmd)
elif openabled is True:
    sys.exit("Optimisation is enabled but appmakecmd in config.cfg has not been set, ABORT!")

memop = False
if config['OPTIMISATION'].getboolean('memop') is True and openabled is True:
    stacklibcompiled = subprocess.check_output("cat $RTE_SDK/config/common_base | grep -m1 CONFIG_RTE_LIBRTE_STACK=", shell=True).decode(sys.stdout.encoding).rstrip().strip()[-1:]
    stackdrivercomplied = subprocess.check_output("cat $RTE_SDK/config/common_base | grep -m1 CONFIG_RTE_DRIVER_MEMPOOL_STACK=", shell=True).decode(sys.stdout.encoding).rstrip().strip()[-1:]
    memdriver = subprocess.check_output("cat $RTE_SDK/config/common_base | grep -m1 CONFIG_RTE_MBUF_DEFAULT_MEMPOOL_OPS=", shell=True).decode(sys.stdout.encoding).rstrip().strip()
    if stacklibcompiled is "y" and stackdrivercomplied is "y" and "ring_mp_mc" in memdriver:
        memop = True
        print("Memory Optimisation Step is enabled (LIBRTE_STACK and RTE_DRIVER_MEMPOOL_STACK are compiled")
    elif stacklibcompiled is "n":
        print("Memory Optimisation Step is disabled (LIBRTE_STACK is not compiled, set CONFIG_RTE_LIBRTE_STACK=y)")
    elif stackdrivercomplied is "n":
        print("Memory Optimisation Step is disabled (RTE_DRIVER_MEMPOOL_STACK is not compiled, set CONFIG_RTE_DRIVER_MEMPOOL_STACK=y)")
    elif "ring_mp_mc" not in memdriver:
         print("Memory Optimisation Step is disabled (CONFIG_RTE_MBUF_DEFAULT_MEMPOOL_OPS is not set to ring, set CONFIG_RTE_MBUF_DEFAULT_MEMPOOL_OPS=\"ring_mp_mc\")")
elif openabled is True:
    print("Memory Optimisation Step is disabled")

testcore = int(config['CPU']['testcore'])

testsocket = int(subprocess.check_output("cat /proc/cpuinfo | grep -A 18 'processor\s\+: " +
                                         str(testcore) +
                                         "' | grep 'physical id' | head -1 | awk '{print substr($0,length,1)}'",
                                         shell=True))

if testcore is not None:
    print("Test software core:", testcore, "(Socket: " + str(testsocket) + ")")
else:
    sys.exit("No test core was specified (testcore in config.cfg), ABORT!")

appmasterenabled = True
appmaster = int(config['CPU']['appmaster'])
appmastersocket = int(subprocess.check_output("cat /proc/cpuinfo | grep -A 18 'processor\s\+: " +
                                              str(appmaster) +
                                              "' | grep 'physical id' | head -1 | awk '{print substr($0,length,1)}'",
                                              shell=True))
if appmaster is not None:
    print("DPDK app master core:", appmaster, "(Socket: "+str(appmastersocket)+")")
else:
    appmasterenabled = False
    print("DPDK app has no master core")

appcores = [int(e) for e in (config['CPU']['appcores']).split(",")]
appcoresno = len(appcores)
if appcores is not None:
    print("DPDK app has", appcoresno, "cores:", appcores)
else:
    sys.exit("No DPDK app cores were specified (appcores in config.cfg), ABORT!")

appcoressockets = []
appsocket = None
for x in appcores:
    appcoressockets.append(int(subprocess.check_output("cat /proc/cpuinfo | grep -A 18 'processor\s\+: " +
                                                       str(x) +
                                                       "' | grep 'physical id' | head -1 | awk '{print substr($0,length,1)}'",
                                                       shell=True)))

if appmasterenabled:
    if all(x == appcoressockets[0] for x in appcoressockets) and appmastersocket == appcoressockets[0]:
        appsocket = appcoressockets[0]
        print("DPDK app running on socket", appsocket)
    else:
        sys.exit("DPDK app cores and master core must be on the same socket, ABORT!")
else:
    if all(x == appcoressockets[0] for x in appcoressockets):
        appsocket = appcoressockets[0]
        print("DPDK app running on socket", appsocket)
    else:
        sys.exit("DPDK app cores must be on the same socket, ABORT!")

pcmdir = config['TOOLS']['pcmdir']
if pcmdir is not None:
    print("PCM directory:", pcmdir)
else:
    sys.exit("No PCM directory was specified (pcmdir in config.cfg), ABORT!")

if not os.path.exists("tmp"):
    os.makedirs('tmp')

cpuafforig = subprocess.check_output("taskset -cp " +
                                     str(os.getpid()),
                                     shell=True).decode(sys.stdout.encoding).rstrip().split(':', 1)[-1].strip()

print("Original CPU Affinity: " + cpuafforig)

subprocess.call("taskset -cp " +
                str(testcore) + " " +
                str(os.getpid()),
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)

print("DOAT pinned to core",
      testcore,
      "PID:",
      os.getpid())

if openabled:
    print("\nStarting Analysis of Original unmodified DPDK App")
else:
    print("\nStarting Analysis of DPDK App")

print("Starting DPDK App")
proc = subprocess.Popen(applocation+appcmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT,
                        shell=True,
                        preexec_fn=os.setsid)
testpid = proc.pid


# TODO Deal with measurement
# Once Test Process is spawned add catch to kill test process if test abandoned
def safeexit():
    try:
        os.system("rm -rf tmp")
        os.remove("index.html")
        kill_group_pid(testpid)
    except:
        pass
    print("Exiting . . .")


atexit.register(safeexit)

if check_pid(testpid):
    print("DPDK App started successfully")
else:
    sys.exit("DPDK App failed to start, ABORT!")

print("Allow application to startup and settle . . .")
progress_bar(startuptime)

if proc.poll() is not None:
    sys.exit("DPDK App died or failed to start, ABORT!")
else:
    print("DPDK App ready for tests, PID: ",
          testpid)

print('Starting Measurements . . .')

pcm = subprocess.Popen(pcmdir+'pcm.x '+str(teststepsize)+' -csv=tmp/pcm.csv',
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT,
                       shell=True,
                       preexec_fn=os.setsid)

wallp = subprocess.Popen("echo 'power,time\n' > tmp/wallpower.csv; while true; do ipmitool sdr | grep 'PS1 Input Power' | cut -c 20- | cut -f1 -d 'W' | tr -d '\n' | sed 's/.$//' >> tmp/wallpower.csv; echo -n ',' >> tmp/wallpower.csv; date +%s >> tmp/wallpower.csv; sleep "+str(teststepsize)+"; done",
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.STDOUT,
                         shell=True,
                         preexec_fn=os.setsid)

if telemetryenabled is True:
    telem = subprocess.Popen('./tools/dpdk-telemetry-auto-csv.py '+socketpath+' tmp/telemetry.csv '+str(testruntime+2)+' '+str(teststepsize),
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.STDOUT,
                             shell=True,
                             preexec_fn=os.setsid)

progress_bar(2)

if wallp.poll() is not None:
    kill_group_pid(pcm.pid)
    kill_group_pid(proc.pid)
    if telemetryenabled is True:
        kill_group_pid(telem.pid)
    sys.exit("IPMItool died or failed to start, ABORT!")

if pcm.poll() is not None:
    kill_group_pid(wallp.pid)
    kill_group_pid(proc.pid)
    if telemetryenabled is True:
        kill_group_pid(telem.pid)
    sys.exit("PCM died or failed to start, ABORT! (If problem persists, try to execute 'modprobe msr' as root user)")

if telemetryenabled is True:
    if telem.poll() is not None:
        kill_group_pid(pcm.pid)
        kill_group_pid(wallp.pid)
        kill_group_pid(proc.pid)
        sys.exit("Telemetry died or failed to start, ABORT!")

print("Running Test . . .")
progress_bar(testruntime)

appdiedduringtest = False
if proc.poll() is None:
    print("SUCCESS: DPDK App is still alive after test")
else:
    print("ERROR: DPDK App died during test")
    appdiedduringtest = True

print("Killing test processes")

kill_group_pid(testpid)

kill_group_pid(pcm.pid)

kill_group_pid(wallp.pid)

if telemetryenabled is True:
    kill_group_pid(telem.pid)

if appdiedduringtest is True:
    sys.exit("Test invalid due to DPDK App dying during test, ABORT!")

#print("Generating report")

f = open('tmp/pcm.csv', 'r')
filedata = f.read()
f.close()

newdata = filedata.replace(";", ",")

f = open('tmp/pcm.csv', 'w')
f.write(newdata)
f.close()

pcmdata = pandas.read_csv('tmp/pcm.csv', low_memory=False)

pcmdatapoints = pcmdata.shape[0]*pcmdata.shape[1]

socketread = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc("Socket"+str(appsocket))+13].tolist())[1:]).astype(np.float) * 1000
socketwrite = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc("Socket"+str(appsocket))+14].tolist())[1:]).astype(np.float) * 1000

socketreadavg = round(sum(socketread)/len(socketread), 2)
socketwriteavg = round(sum(socketwrite)/len(socketwrite), 2)
socketwritereadratio = round(socketwriteavg/socketreadavg,2)

l3missmaster = 0
l2missmaster = 0
l3hitmaster = 0
l2hitmaster = 0
l3missmasteravg = 0.0
l2missmasteravg = 0.0
l3hitmasteravg = 0.0
l2hitmasteravg = 0.0
if appmasterenabled is True:
    l3missmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+4].tolist())[1:]).astype(np.float)*1000*1000
    l2missmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+5].tolist())[1:]).astype(np.float)*1000*1000
    l3hitmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+6].tolist())[1:]).astype(np.float)*100
    l2hitmaster = np.asarray((pcmdata.iloc[:, pcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+7].tolist())[1:]).astype(np.float)*100
    l3missmasteravg = round(sum(l3missmaster)/len(l3missmaster), 1)
    l2missmasteravg = round(sum(l2missmaster)/len(l2missmaster), 1)
    l3hitmasteravg = round(sum(l3hitmaster)/len(l3hitmaster), 1)
    l2hitmasteravg = round(sum(l2hitmaster)/len(l2hitmaster), 1)

l3misscore = []
l2misscore = []
l3hitcore = []
l2hitcore = []

for x in appcores:
    l3misscore.append(np.asarray((pcmdata.iloc[:,pcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+4].tolist())[1:]).astype(np.float)*1000*1000)
    l2misscore.append(np.asarray((pcmdata.iloc[:,pcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+5].tolist())[1:]).astype(np.float)*1000*1000)
    l3hitcore.append(np.asarray((pcmdata.iloc[:,pcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+6].tolist())[1:]).astype(np.float)*100)
    l2hitcore.append(np.asarray((pcmdata.iloc[:,pcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+7].tolist())[1:]).astype(np.float)*100)

l3misscoreavg = []
l2misscoreavg = []
l3hitcoreavg = []
l2hitcoreavg = []
for x in l3misscore:
    l3misscoreavg.append(round(sum(x)/len(x), 1))
for x in l2misscore:
    l2misscoreavg.append(round(sum(x)/len(x), 1))
for x in l3hitcore:
    l3hitcoreavg.append(round(sum(x)/len(x), 1))
for x in l2hitcore:
    l2hitcoreavg.append(round(sum(x)/len(x), 1))

socketx = []
timex = 0
for x in socketread:
    socketx.append(timex)
    timex += teststepsize

plt.figure(0)
plt.plot(socketx, socketread, label="Read")
plt.plot(socketx, socketwrite, label="Write")
plt.xlabel("Time (Seconds)")
plt.ylabel("Bandwidth (MBps)")
plt.title("Memory Bandwidth")
plt.legend()
plt.ylim(bottom=0)
plt.xlim(left=0)
plt.ylim(top=(max(socketwrite)+100))
plt.xlim(right=max(socketx))
plt.savefig("./tmp/membw.png", bbox_inches="tight")

membwhtml = "<h2>Memory Bandwidth</h2><img src='./tmp/membw.png'/><p>Read Avg: " +\
            str(socketreadavg) +\
            "MBps</p><p>Write Avg: " +\
            str(socketwriteavg) +\
            "MBps</p><p>Write to Read Ratio: " +\
            str(socketwritereadratio) +\
            "</p><p><a href='./tmp/pcm.csv' class='btn btn-info' role='button'>Download Full PCM CSV</a>"

wallpdata = pandas.read_csv('tmp/wallpower.csv', sep=',', low_memory=False)
wallpdatapoints = wallpdata.shape[0]*wallpdata.shape[1]
wallpower = np.asarray(wallpdata["power"].tolist()).astype(np.int)
wallpowertime = np.asarray(wallpdata["time"].tolist()).astype(np.int)
wallpowertimezero = wallpowertime[0]
wallpowerx = []
for x in wallpowertime:
    wallpowerx.append(x-wallpowertimezero)
wallpoweravg = round(sum(wallpower)/len(wallpower), 1)

wallpowerhtml = "<h2>Wall Power</h2><img src='./tmp/wallpower.png'/><p>Wall Power Avg: " +\
                str(wallpoweravg) +\
                "Watts</p><p><a href='./tmp/wallpower.csv' class='btn btn-info' role='button'>Download Power CSV</a>"

plt.figure(1)
plt.plot(wallpowerx, wallpower, label="Wall Power")
plt.xlabel("Time (Seconds)")
plt.ylabel("Power (Watts)")
plt.title("Wall Power")
plt.legend()
plt.ylim(bottom=0)
plt.ylim(top=(max(wallpower)+50))
plt.xlim(left=0)
plt.xlim(right=max(wallpowerx))
plt.savefig("./tmp/wallpower.png", bbox_inches="tight")

plt.figure(2)
for i, y in enumerate(l3misscore):
    plt.plot(socketx, y, label="Core " + str(appcores[i]))
if appmasterenabled is True:
    plt.plot(socketx, l3missmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
plt.xlabel("Time (Seconds)")
plt.ylabel("L3 Miss Count")
plt.title("L3 Cache Misses")
plt.legend()
plt.ylim(bottom=0)
plt.xlim(left=0)
plt.xlim(right=max(socketx))
plt.savefig("./tmp/l3miss.png", bbox_inches="tight")
l3misshtml = "<h2>L3 Cache</h2><img src='./tmp/l3miss.png'/>"
if appmasterenabled is True:
    l3misshtml += "<p>Master Core (" +\
                  str(appmaster) +\
                  ") L3 Misses: " +\
                  str(l3missmasteravg) +\
                  "</p>"
for i, x in enumerate(l3misscoreavg):
    l3misshtml += "<p>Core " +\
                  str(appcores[i]) +\
                  " L3 Misses: " +\
                  str(x) +\
                  "</p>"

plt.figure(3)
for i, y in enumerate(l2misscore):
    plt.plot(socketx, y, label="Core "+str(appcores[i]))
if appmasterenabled is True:
    plt.plot(socketx, l2missmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
plt.xlabel("Time (Seconds)")
plt.ylabel("L2 Miss Count")
plt.title("L2 Cache Misses")
plt.legend()
plt.ylim(bottom=0)
plt.xlim(left=0)
plt.xlim(right=max(socketx))
plt.savefig("./tmp/l2miss.png", bbox_inches="tight")
l2misshtml = "<h2>L2 Cache</h2><img src='./tmp/l2miss.png'/>"
if appmasterenabled is True:
    l2misshtml += "<p>Master Core (" +\
                  str(appmaster) +\
                  ") L2 Misses: " +\
                  str(l3missmasteravg) +\
                  "</p>"
for i, x in enumerate(l2misscoreavg):
    l2misshtml += "<p>Core " +\
                  str(appcores[i]) +\
                  " L2 Misses: " +\
                  str(x) +\
                  "</p>"

plt.figure(4)
for i, y in enumerate(l3hitcore):
    plt.plot(socketx, y, label="Core " + str(appcores[i]))
if appmasterenabled is True:
    plt.plot(socketx, l3hitmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
plt.xlabel("Time (Seconds)")
plt.ylabel("L3 Hit (%)")
plt.title("L3 Cache Hits")
plt.legend()
plt.ylim(bottom=0)
plt.xlim(left=0)
plt.xlim(right=max(socketx))
plt.savefig("./tmp/l3hit.png", bbox_inches="tight")
l3hithtml = "<img src='./tmp/l3hit.png'/>"
if appmasterenabled is True:
    l3hithtml += "<p>Master Core (" +\
                 str(appmaster) +\
                 ") L3 Hits: " +\
                 str(l3hitmasteravg) +\
                 "%</p>"
for i, x in enumerate(l3hitcoreavg):
    l3hithtml += "<p>Core " +\
                 str(appcores[i]) +\
                 " L3 Hits: " +\
                 str(x) +\
                 "%</p>"

plt.figure(5)
for i, y in enumerate(l2hitcore):
    plt.plot(socketx, y, label="Core "+str(appcores[i]))
if appmasterenabled is True:
    plt.plot(socketx, l2hitmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
plt.xlabel("Time (Seconds)")
plt.ylabel("L2 Hit (%)")
plt.title("L2 Cache Hits")
plt.legend()
plt.ylim(bottom=0)
plt.xlim(left=0)
plt.xlim(right=max(socketx))
plt.savefig("./tmp/l2hit.png", bbox_inches="tight")
l2hithtml = "<img src='./tmp/l2hit.png'/>"
if appmasterenabled is True:
    l2hithtml += "<p>Master Core (" +\
                 str(appmaster) +\
                 ") L3 Hits: " +\
                 str(l2hitmasteravg) +\
                 "%</p>"
for i, x in enumerate(l2hitcoreavg):
    l2hithtml += "<p>Core " +\
                 str(appcores[i]) +\
                 " L2 Hits: " +\
                 str(x) +\
                 "%</p>"

telemhtml = ""
telemdatapoints = 0
if telemetryenabled is True:
    telemdata = pandas.read_csv('tmp/telemetry.csv', sep=',', low_memory=False)
    telemdatapoints = telemdata.shape[0]*telemdata.shape[1]
    telempkts = np.asarray(telemdata["tx_good_packets"].tolist()).astype(np.int)
    telembytes = np.asarray(telemdata["tx_good_bytes"].tolist()).astype(np.int)
    telemerrors = np.asarray(telemdata["tx_errors"].tolist()).astype(np.int)
    telemdropped = np.asarray(telemdata["tx_dropped"].tolist()).astype(np.int)
    telemtime = np.asarray(telemdata["time"].tolist()).astype(np.float)
    telempktdist = telemdata.loc[:,["tx_size_64_packets",
                                    "tx_size_65_to_127_packets",
                                    "tx_size_128_to_255_packets",
                                    "tx_size_256_to_511_packets",
                                    "tx_size_512_to_1023_packets",
                                    "tx_size_1024_to_1522_packets",
                                    "tx_size_1523_to_max_packets"]].tail(1).values[0]
    telempktsizes = ["64",
                     "65 to 127",
                     "128 to 255",
                     "256 to 511",
                     "512 to 1024",
                     "1024 to 1522",
                     "1523 to max"]
    telemrxerrors = telemdata.loc[:,"rx_errors"].tail(1).values[0]
    telemrxerrorsbool = False
    telemtxerrors = telemdata.loc[:,"tx_errors"].tail(1).values[0]
    telemtxerrorsbool = False
    telemrxdropped = telemdata.loc[:,"rx_dropped"].tail(1).values[0]
    telemrxdroppedbool = False
    telemtxdropped = telemdata.loc[:,"tx_dropped"].tail(1).values[0]
    telemtxdroppedbool = False

    if int(telemrxerrors) is not 0:
        print("ERROR: RX errors occured during this test (rx_errors: "+str(telemrxerrors)+")")
        telemrxerrorsbool = True
    if int(telemtxerrors) is not 0:
        print("ERROR: TX errors occured during this test (tx_errors: "+str(telemtxerrors)+")")
        telemtxerrorsbool = True

    if int(telemrxdropped) is not 0:
        print("ERROR: RX Packets were dropped during this test (rx_dropped: "+str(telemrxdropped)+")")
        telemrxdroppedbool = True
    if int(telemtxdropped) is not 0:
        print("ERROR: TX Packets were dropped during this test (tx_dropped: "+str(telemtxdropped)+")")
        telemtxdroppedbool = True

    plt.figure(6)
    x = np.arange(telempktdist.size)
    plt.bar(x, height=telempktdist)
    plt.xticks(x, telempktsizes, rotation=45)
    plt.xlabel("Packet Sizes (Bytes)")
    plt.ylabel("Packets")
    plt.title("Packet Size Distribution")
    plt.savefig("./tmp/pktdist.png", bbox_inches="tight")

    telembyteszero = telembytes[0]
    telembytesreset = []
    for y in telembytes:
        telembytesreset.append(y-telembyteszero)

    telemgbytes = [x / 1000000000 for x in telembytesreset]

    telemgbytesmax = np.round(max(telemgbytes),1)

    telempktszero = telempkts[0]
    telempktsreset = []
    for y in telempkts:
        telempktsreset.append(y-telempktszero)

    telempktsresetmax = max(telempktsreset)

    plt.figure(7)
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    ax1.plot(telemtime, telemgbytes, alpha=1, label="Data Transfered")
    ax2.plot(telemtime, telempktsreset, alpha=0.6, color='orange', label="Packets Transfered")
    ax1.set_xlabel('Time (Seconds)')
    ax1.set_ylabel('Data Transfered (GB)')
    ax2.set_ylabel('Packets Transfered (Packets)')
    ax1.set_ylim(bottom=0)
    ax2.set_ylim(bottom=0)
    ax1.legend(loc=2)
    ax2.legend(loc=1)
    plt.title("Data/Packets Transfered")
    plt.xlim(left=0)
    plt.xlim(right=max(telemtime))
    plt.savefig("./tmp/transfer.png", bbox_inches="tight")

    telempktssec = []
    for i, y in enumerate(telempktsreset):
        if i is not 0 and i is not 1:
            telempktssec.append((y-telempktsreset[i-1])/teststepsize)
        elif i is 1:
            val = (y-telempktsreset[i-1])/teststepsize
            telempktssec.append(val)
            telempktssec[0] = val
        else:
            telempktssec.append(0)

    telempktsecavg = np.round(np.mean(telempktssec),0)

    telemthroughput = []
    for i, y in enumerate(telembytesreset):
        if i is not 0 and i is not 1:
            telemthroughput.append((y-telembytesreset[i-1])/1000000000*8/teststepsize)
        elif i is 1:
            val = ((y-telembytesreset[i-1])/1000000000*8/teststepsize)
            telemthroughput.append(val)
            telemthroughput[0] = val
        else:
            telemthroughput.append(0)

    telemthroughputavg = np.round(np.mean(telemthroughput),2)

    plt.figure(8)
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    ax1.plot(telemtime, telemthroughput, alpha=1, label="Throughput")
    ax2.plot(telemtime, telempktssec, alpha=0.6, color='orange', label="Packets Per Second")
    ax1.set_xlabel('Time (Seconds)')
    ax1.set_ylabel('Throughput (Gbps)')
    ax2.set_ylabel('Packets Per Second (Packets)')
    ax1.set_ylim(bottom=0)
    ax2.set_ylim(bottom=0)
    ax2.set_ylim(top=max(telempktssec)+1000000)
    ax1.set_ylim(top=max(telemthroughput)+1)
    ax1.legend(loc=2)
    ax2.legend(loc=1)
    plt.title("Transfer Speeds")
    plt.xlim(left=0)
    plt.xlim(right=max(telemtime))
    plt.savefig("./tmp/speeds.png", bbox_inches="tight")

    telemhtml += "<h2>Telemetry</h2><img src='./tmp/pktdist.png'/><br/><img src='./tmp/transfer.png'/><p>Total Data Transfered: "+str(telemgbytesmax)+"GB</p><p>Total Packets Transfered: "+str(format(telempktsresetmax,","))+" packets</p><img src='./tmp/speeds.png'/><p>Average Throughput: "+str(telemthroughputavg)+" Gbps</p><p>Average Packets Per Second: "+str(format(telempktsecavg,","))+" pps</p>"

    telemhtml+="<p><a href='./tmp/telemetry.csv' class='btn btn-info' role='button'>Download Full Telemetry CSV</a></p><h2>Errors</h2>"

    if telemrxerrorsbool is False:
        telemhtml+="<h3 style='color:green;font-weight:bold;'>RX Errors: "+str(telemrxerrors)+"</h3>"
    else:
        telemhtml+="<h3 style='color:red;font-weight:bold;'>RX Errors: "+str(telemrxerrors)+"</h3>"
    if telemtxerrorsbool is False:
        telemhtml+="<h3 style='color:green;font-weight:bold;'>TX Errors: "+str(telemtxerrors)+"</h3>"
    else:
        telemhtml+="<h3 style='color:red;font-weight:bold;'>TX Errors: "+str(telemtxerrors)+"</h3>"

    if telemrxdroppedbool is False:
        telemhtml+="<h3 style='color:green;font-weight:bold;'>RX Dropped Packets: "+str(telemrxdropped)+"</h3>"
    else:
        telemhtml+="<h3 style='color:red;font-weight:bold;'>RX Dropped Packets: "+str(telemrxdropped)+"</h3>"
    if telemtxdroppedbool is False:
        telemhtml+="<h3 style='color:green;font-weight:bold;'>TX Dropped Packets: "+str(telemtxdropped)+"</h3>"
    else:
        telemhtml+="<h3 style='color:red;font-weight:bold;'>TX Dropped Packets: "+str(telemtxdropped)+"</h3>"
else:
    telemhtml += "<h2>Telemetry</h2><p style='color:red'>Telemetry is disabled</p>"

reporthtml=""
if generatepdf is True:
    reporthtml+="<p style='text-align:center'><a href='./tmp/doatreport.pdf' class='btn btn-success' role='button' style='font-size: 28px;'>Download PDF Report</a></p>"
if generatezip is True:
    reporthtml+="<p style='text-align:center'><a href='./tmp/doat_results.zip' class='btn btn-success' role='button' style='font-size: 28px;'>Download Results Zip</a></p>"

ophtml = ""
opdatapoints = 0
stepsenabled = False
if memop is True:
    stepsenabled = True

if openabled is True and stepsenabled is True:
    print("\nModifying DPDK Configuration")
    for  line in fileinput.FileInput(rtesdk+"/config/common_base", inplace=1): 
        if "CONFIG_RTE_MBUF_DEFAULT_MEMPOOL_OPS" in line and memop is True:
            sys.stdout.write('CONFIG_RTE_MBUF_DEFAULT_MEMPOOL_OPS="stack"\n')
        else:
            sys.stdout.write(line)
    
    subprocess.call("taskset -cp " +
                    cpuafforig + " " +
                    str(os.getpid()),
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
    print("DOAT unpinned from core to speed up build")
    
    print("Building DPDK and DPDK App with new configuration options (This can take several minutes)")
    dpdkbuild = subprocess.Popen("cd "+rtesdk+"; "+dpdkmakecmd+"; cd "+applocation+"; "+appmakecmd+";",
                                 shell=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)

    animation = "|/-\\"
    idx = 0
    buildtime = 0.0
    while dpdkbuild.poll() is None:
        m, s = divmod(int(buildtime), 60)
        print('Building . . .',f'{m:02d}:{s:02d}',animation[idx % len(animation)], end="\r")
        idx += 1
        buildtime += 0.1
        time.sleep(0.1)

    subprocess.call("taskset -cp " +
                    str(testcore) + " " +
                    str(os.getpid()),
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
    print("DOAT pinned to core",
          testcore,
          "PID:",
          os.getpid())

    print("\nAnalysing Modified DPDK App")
    print("Starting DPDK App")
    
    opproc = subprocess.Popen(applocation+appcmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT,
                            shell=True,
                            preexec_fn=os.setsid)
    optestpid = opproc.pid

    if check_pid(optestpid):
        print("DPDK App started successfully")
    else:
        sys.exit("DPDK App failed to start, ABORT!")

    print("Allow application to startup and settle . . .")
    progress_bar(startuptime)

    if opproc.poll() is not None:
        sys.exit("DPDK App died or failed to start, ABORT!")
    else:
        print("DPDK App ready for tests, PID: ",
              testpid)

    print('Starting Measurements . . .')

    oppcm = subprocess.Popen(pcmdir+'pcm.x '+str(teststepsize)+' -csv=tmp/pcm_op.csv',
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.STDOUT,
                             shell=True,
                             preexec_fn=os.setsid)

    opwallp = subprocess.Popen("echo 'power,time\n' > tmp/wallpower_op.csv; while true; do ipmitool sdr | grep 'PS1 Input Power' | cut -c 20- | cut -f1 -d 'W' | tr -d '\n' | sed 's/.$//' >> tmp/wallpower_op.csv; echo -n ',' >> tmp/wallpower_op.csv; date +%s >> tmp/wallpower_op.csv; sleep "+str(teststepsize)+"; done",
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.STDOUT,
                             shell=True,
                             preexec_fn=os.setsid)

    if telemetryenabled is True:
        optelem = subprocess.Popen('./tools/dpdk-telemetry-auto-csv.py '+socketpath+' tmp/telemetry_op.csv '+str(testruntime+2)+' '+str(teststepsize),
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.STDOUT,
                                   shell=True,
                                   preexec_fn=os.setsid)

    progress_bar(2)

    if opwallp.poll() is not None:
        kill_group_pid(oppcm.pid)
        kill_group_pid(opproc.pid)
        if telemetryenabled is True:
            kill_group_pid(optelem.pid)
        sys.exit("IPMItool died or failed to start, ABORT!")

    if oppcm.poll() is not None:
        kill_group_pid(opwallp.pid)
        kill_group_pid(opproc.pid)
        if telemetryenabled is True:
            kill_group_pid(optelem.pid)
        sys.exit("PCM died or failed to start, ABORT! (If problem persists, try to execute 'modprobe msr' as root user)")

    if telemetryenabled is True:
        if optelem.poll() is not None:
            kill_group_pid(oppcm.pid)
            kill_group_pid(opwallp.pid)
            kill_group_pid(opproc.pid)
            sys.exit("Telemetry died or failed to start, ABORT!")

    print("Running Test . . .")
    progress_bar(testruntime)

    opappdiedduringtest = False
    if opproc.poll() is None:
        print("SUCCESS: DPDK App is still alive after test")
    else:
        print("ERROR: DPDK App died during test")
        opappdiedduringtest = True

    print("Killing test processes")

    kill_group_pid(optestpid)

    kill_group_pid(oppcm.pid)

    kill_group_pid(opwallp.pid)

    if telemetryenabled is True:
        kill_group_pid(optelem.pid)

    if opappdiedduringtest is True:
        sys.exit("Test invalid due to DPDK App dying during test, ABORT!")

    f = open('tmp/pcm_op.csv', 'r')
    opfiledata = f.read()
    f.close()

    opnewdata = opfiledata.replace(";", ",")

    f = open('tmp/pcm_op.csv', 'w')
    f.write(opnewdata)
    f.close()

    oppcmdata = pandas.read_csv('tmp/pcm_op.csv', low_memory=False)

    oppcmdatapoints = oppcmdata.shape[0]*oppcmdata.shape[1]

    opsocketread = np.asarray((oppcmdata.iloc[:, oppcmdata.columns.get_loc("Socket"+str(appsocket))+13].tolist())[1:]).astype(np.float) * 1000
    opsocketwrite = np.asarray((oppcmdata.iloc[:, oppcmdata.columns.get_loc("Socket"+str(appsocket))+14].tolist())[1:]).astype(np.float) * 1000

    opsocketreadavg = round(sum(opsocketread)/len(opsocketread), 2)
    opsocketwriteavg = round(sum(opsocketwrite)/len(opsocketwrite), 2)
    opsocketwritereadratio = round(opsocketwriteavg/opsocketreadavg,2)

    opl3missmaster = 0
    opl2missmaster = 0
    opl3hitmaster = 0
    opl2hitmaster = 0
    opl3missmasteravg = 0.0
    opl2missmasteravg = 0.0
    opl3hitmasteravg = 0.0
    opl2hitmasteravg = 0.0
    if appmasterenabled is True:
        opl3missmaster = np.asarray((oppcmdata.iloc[:, oppcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+4].tolist())[1:]).astype(np.float)*1000*1000
        opl2missmaster = np.asarray((oppcmdata.iloc[:, oppcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+5].tolist())[1:]).astype(np.float)*1000*1000
        opl3hitmaster = np.asarray((oppcmdata.iloc[:, oppcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+6].tolist())[1:]).astype(np.float)*100
        opl2hitmaster = np.asarray((oppcmdata.iloc[:, oppcmdata.columns.get_loc("Core"+str(appmaster)+" (Socket "+str(appsocket)+")")+7].tolist())[1:]).astype(np.float)*100
        opl3missmasteravg = round(sum(opl3missmaster)/len(opl3missmaster), 1)
        opl2missmasteravg = round(sum(opl2missmaster)/len(opl2missmaster), 1)
        opl3hitmasteravg = round(sum(opl3hitmaster)/len(opl3hitmaster), 1)
        opl2hitmasteravg = round(sum(opl2hitmaster)/len(opl2hitmaster), 1)

    opl3misscore = []
    opl2misscore = []
    opl3hitcore = []
    opl2hitcore = []

    for x in appcores:
        opl3misscore.append(np.asarray((oppcmdata.iloc[:,oppcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+4].tolist())[1:]).astype(np.float)*1000*1000)
        opl2misscore.append(np.asarray((oppcmdata.iloc[:,oppcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+5].tolist())[1:]).astype(np.float)*1000*1000)
        opl3hitcore.append(np.asarray((oppcmdata.iloc[:,oppcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+6].tolist())[1:]).astype(np.float)*100)
        opl2hitcore.append(np.asarray((oppcmdata.iloc[:,oppcmdata.columns.get_loc("Core"+str(x)+" (Socket "+str(appsocket)+")")+7].tolist())[1:]).astype(np.float)*100)

    opl3misscoreavg = []
    opl2misscoreavg = []
    opl3hitcoreavg = []
    opl2hitcoreavg = []
    for x in opl3misscore:
        opl3misscoreavg.append(round(sum(x)/len(x), 1))
    for x in opl2misscore:
        opl2misscoreavg.append(round(sum(x)/len(x), 1))
    for x in opl3hitcore:
        opl3hitcoreavg.append(round(sum(x)/len(x), 1))
    for x in opl2hitcore:
        opl2hitcoreavg.append(round(sum(x)/len(x), 1))

    opsocketx = []
    optimex = 0
    for x in opsocketread:
        opsocketx.append(optimex)
        optimex += teststepsize

    plt.figure(10)
    plt.plot(opsocketx, opsocketread, label="Read")
    plt.plot(opsocketx, opsocketwrite, label="Write")
    plt.xlabel("Time (Seconds)")
    plt.ylabel("Bandwidth (MBps)")
    plt.title("Memory Bandwidth")
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.ylim(top=(max(opsocketwrite)+100))
    plt.xlim(right=max(opsocketx))
    plt.savefig("./tmp/membw_op.png", bbox_inches="tight")

    opmembwhtml = "<h2>Memory Bandwidth</h2><img src='./tmp/membw_op.png'/><p>Read Avg: " +\
                str(opsocketreadavg) +\
                "MBps</p><p>Write Avg: " +\
                str(opsocketwriteavg) +\
                "MBps</p><p>Write to Read Ratio: " +\
                str(opsocketwritereadratio) +\
                "</p><p><a href='./tmp/pcm_op.csv' class='btn btn-info' role='button'>Download Full PCM CSV</a>"

    opwallpdata = pandas.read_csv('tmp/wallpower_op.csv', sep=',', low_memory=False)
    opwallpdatapoints = opwallpdata.shape[0]*opwallpdata.shape[1]
    opwallpower = np.asarray(opwallpdata["power"].tolist()).astype(np.int)
    opwallpowertime = np.asarray(opwallpdata["time"].tolist()).astype(np.int)
    opwallpowertimezero = opwallpowertime[0]
    opwallpowerx = []
    for x in opwallpowertime:
        opwallpowerx.append(x-opwallpowertimezero)
    opwallpoweravg = round(sum(opwallpower)/len(opwallpower), 1)

    opwallpowerhtml = "<h2>Wall Power</h2><img src='./tmp/wallpower_op.png'/><p>Wall Power Avg: " +\
                    str(opwallpoweravg) +\
                    "Watts</p><p><a href='./tmp/wallpower_op.csv' class='btn btn-info' role='button'>Download Power CSV</a>"

    plt.figure(11)
    plt.plot(opwallpowerx, opwallpower, label="Wall Power")
    plt.xlabel("Time (Seconds)")
    plt.ylabel("Power (Watts)")
    plt.title("Wall Power")
    plt.legend()
    plt.ylim(bottom=0)
    plt.ylim(top=(max(opwallpower)+50))
    plt.xlim(left=0)
    plt.xlim(right=max(opwallpowerx))
    plt.savefig("./tmp/wallpower_op.png", bbox_inches="tight")

    plt.figure(12)
    for i, y in enumerate(opl3misscore):
        plt.plot(opsocketx, y, label="Core " + str(appcores[i]))
    if appmasterenabled is True:
        plt.plot(opsocketx, opl3missmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
    plt.xlabel("Time (Seconds)")
    plt.ylabel("L3 Miss Count")
    plt.title("L3 Cache Misses")
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(opsocketx))
    plt.savefig("./tmp/l3miss_op.png", bbox_inches="tight")
    opl3misshtml = "<h2>L3 Cache</h2><img src='./tmp/l3miss_op.png'/>"
    if appmasterenabled is True:
        opl3misshtml += "<p>Master Core (" +\
                      str(appmaster) +\
                      ") L3 Misses: " +\
                      str(opl3missmasteravg) +\
                      "</p>"
    for i, x in enumerate(opl3misscoreavg):
        opl3misshtml += "<p>Core " +\
                      str(appcores[i]) +\
                      " L3 Misses: " +\
                      str(x) +\
                      "</p>"

    plt.figure(13)
    for i, y in enumerate(opl2misscore):
        plt.plot(opsocketx, y, label="Core "+str(appcores[i]))
    if appmasterenabled is True:
        plt.plot(opsocketx, opl2missmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
    plt.xlabel("Time (Seconds)")
    plt.ylabel("L2 Miss Count")
    plt.title("L2 Cache Misses")
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(opsocketx))
    plt.savefig("./tmp/l2miss_op.png", bbox_inches="tight")
    opl2misshtml = "<h2>L2 Cache</h2><img src='./tmp/l2miss_op.png'/>"
    if appmasterenabled is True:
        opl2misshtml += "<p>Master Core (" +\
                      str(appmaster) +\
                      ") L2 Misses: " +\
                      str(opl3missmasteravg) +\
                      "</p>"
    for i, x in enumerate(opl2misscoreavg):
        opl2misshtml += "<p>Core " +\
                      str(appcores[i]) +\
                      " L2 Misses: " +\
                      str(x) +\
                      "</p>"

    plt.figure(14)
    for i, y in enumerate(opl3hitcore):
        plt.plot(opsocketx, y, label="Core " + str(appcores[i]))
    if appmasterenabled is True:
        plt.plot(opsocketx, opl3hitmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
    plt.xlabel("Time (Seconds)")
    plt.ylabel("L3 Hit (%)")
    plt.title("L3 Cache Hits")
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(opsocketx))
    plt.savefig("./tmp/l3hit_op.png", bbox_inches="tight")
    opl3hithtml = "<img src='./tmp/l3hit_op.png'/>"
    if appmasterenabled is True:
        opl3hithtml += "<p>Master Core (" +\
                     str(appmaster) +\
                     ") L3 Hits: " +\
                     str(opl3hitmasteravg) +\
                     "%</p>"
    for i, x in enumerate(opl3hitcoreavg):
        opl3hithtml += "<p>Core " +\
                     str(appcores[i]) +\
                     " L3 Hits: " +\
                     str(x) +\
                     "%</p>"

    plt.figure(15)
    for i, y in enumerate(opl2hitcore):
        plt.plot(opsocketx, y, label="Core "+str(appcores[i]))
    if appmasterenabled is True:
        plt.plot(opsocketx, opl2hitmaster, alpha=0.5, label="Master Core ("+str(appmaster)+")")
    plt.xlabel("Time (Seconds)")
    plt.ylabel("L2 Hit (%)")
    plt.title("L2 Cache Hits")
    plt.legend()
    plt.ylim(bottom=0)
    plt.xlim(left=0)
    plt.xlim(right=max(opsocketx))
    plt.savefig("./tmp/l2hit_op.png", bbox_inches="tight")
    opl2hithtml = "<img src='./tmp/l2hit_op.png'/>"
    if appmasterenabled is True:
        opl2hithtml += "<p>Master Core (" +\
                     str(appmaster) +\
                     ") L3 Hits: " +\
                     str(opl2hitmasteravg) +\
                     "%</p>"
    for i, x in enumerate(opl2hitcoreavg):
        opl2hithtml += "<p>Core " +\
                     str(appcores[i]) +\
                     " L2 Hits: " +\
                     str(x) +\
                     "%</p>"

    optelemhtml = ""
    optelemdatapoints = 0
    if telemetryenabled is True:
        optelemdata = pandas.read_csv('tmp/telemetry_op.csv', sep=',', low_memory=False)
        optelemdatapoints = optelemdata.shape[0]*optelemdata.shape[1]
        optelempkts = np.asarray(optelemdata["tx_good_packets"].tolist()).astype(np.int)
        optelembytes = np.asarray(optelemdata["tx_good_bytes"].tolist()).astype(np.int)
        optelemerrors = np.asarray(optelemdata["tx_errors"].tolist()).astype(np.int)
        optelemdropped = np.asarray(optelemdata["tx_dropped"].tolist()).astype(np.int)
        optelemtime = np.asarray(optelemdata["time"].tolist()).astype(np.float)
        optelempktdist = optelemdata.loc[:,["tx_size_64_packets",
                                        "tx_size_65_to_127_packets",
                                        "tx_size_128_to_255_packets",
                                        "tx_size_256_to_511_packets",
                                        "tx_size_512_to_1023_packets",
                                        "tx_size_1024_to_1522_packets",
                                        "tx_size_1523_to_max_packets"]].tail(1).values[0]
        optelempktsizes = ["64",
                           "65 to 127",
                           "128 to 255",
                           "256 to 511",
                           "512 to 1024",
                           "1024 to 1522",
                           "1523 to max"]
        optelemrxerrors = optelemdata.loc[:,"rx_errors"].tail(1).values[0]
        optelemrxerrorsbool = False
        optelemtxerrors = optelemdata.loc[:,"tx_errors"].tail(1).values[0]
        optelemtxerrorsbool = False
        optelemrxdropped = optelemdata.loc[:,"rx_dropped"].tail(1).values[0]
        optelemrxdroppedbool = False
        optelemtxdropped = optelemdata.loc[:,"tx_dropped"].tail(1).values[0]
        optelemtxdroppedbool = False

        if int(optelemrxerrors) is not 0:
            print("ERROR: RX errors occured during this test (rx_errors: "+str(optelemrxerrors)+")")
            optelemrxerrorsbool = True
        if int(optelemtxerrors) is not 0:
            print("ERROR: TX errors occured during this test (tx_errors: "+str(optelemtxerrors)+")")
            optelemtxerrorsbool = True

        if int(optelemrxdropped) is not 0:
            print("ERROR: RX Packets were dropped during this test (rx_dropped: "+str(optelemrxdropped)+")")
            optelemrxdroppedbool = True
        if int(optelemtxdropped) is not 0:
            print("ERROR: TX Packets were dropped during this test (tx_dropped: "+str(optelemtxdropped)+")")
            optelemtxdroppedbool = True

        plt.figure(16)
        x = np.arange(optelempktdist.size)
        plt.bar(x, height=optelempktdist)
        plt.xticks(x, optelempktsizes, rotation=45)
        plt.xlabel("Packet Sizes (Bytes)")
        plt.ylabel("Packets")
        plt.title("Packet Size Distribution")
        plt.savefig("./tmp/pktdist_op.png", bbox_inches="tight")

        optelembyteszero = optelembytes[0]
        optelembytesreset = []
        for y in optelembytes:
            optelembytesreset.append(y-optelembyteszero)

        optelemgbytes = [x / 1000000000 for x in optelembytesreset]

        optelemgbytesmax = np.round(max(optelemgbytes),1)

        optelempktszero = optelempkts[0]
        optelempktsreset = []
        for y in optelempkts:
            optelempktsreset.append(y-optelempktszero)

        optelempktsresetmax = max(optelempktsreset)

        plt.figure(17)
        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()
        ax1.plot(optelemtime, optelemgbytes, alpha=1, label="Data Transfered")
        ax2.plot(optelemtime, optelempktsreset, alpha=0.6, color='orange', label="Packets Transfered")
        ax1.set_xlabel('Time (Seconds)')
        ax1.set_ylabel('Data Transfered (GB)')
        ax2.set_ylabel('Packets Transfered (Packets)')
        ax1.set_ylim(bottom=0)
        ax2.set_ylim(bottom=0)
        ax1.legend(loc=2)
        ax2.legend(loc=1)
        plt.title("Data/Packets Transfered")
        plt.xlim(left=0)
        plt.xlim(right=max(optelemtime))
        plt.savefig("./tmp/transfer_op.png", bbox_inches="tight")

        optelempktssec = []
        for i, y in enumerate(optelempktsreset):
            if i is not 0 and i is not 1:
                optelempktssec.append((y-optelempktsreset[i-1])/teststepsize)
            elif i is 1:
                val = (y-optelempktsreset[i-1])/teststepsize
                optelempktssec.append(val)
                optelempktssec[0] = val
            else:
                optelempktssec.append(0)

        optelempktsecavg = np.round(np.mean(optelempktssec),0)

        optelemthroughput = []
        for i, y in enumerate(optelembytesreset):
            if i is not 0 and i is not 1:
                optelemthroughput.append((y-optelembytesreset[i-1])/1000000000*8/teststepsize)
            elif i is 1:
                val = ((y-optelembytesreset[i-1])/1000000000*8/teststepsize)
                optelemthroughput.append(val)
                optelemthroughput[0] = val
            else:
                optelemthroughput.append(0)

        optelemthroughputavg = np.round(np.mean(optelemthroughput),2)

        plt.figure(18)
        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()
        ax1.plot(optelemtime, optelemthroughput, alpha=1, label="Throughput")
        ax2.plot(optelemtime, optelempktssec, alpha=0.6, color='orange', label="Packets Per Second")
        ax1.set_xlabel('Time (Seconds)')
        ax1.set_ylabel('Throughput (Gbps)')
        ax2.set_ylabel('Packets Per Second (Packets)')
        ax1.set_ylim(bottom=0)
        ax2.set_ylim(bottom=0)
        ax2.set_ylim(top=max(optelempktssec)+1000000)
        ax1.set_ylim(top=max(optelemthroughput)+1)
        ax1.legend(loc=2)
        ax2.legend(loc=1)
        plt.title("Transfer Speeds")
        plt.xlim(left=0)
        plt.xlim(right=max(optelemtime))
        plt.savefig("./tmp/speeds_op.png", bbox_inches="tight")

        optelemhtml += "<h2>Telemetry</h2><img src='./tmp/pktdist_op.png'/><br/><img src='./tmp/transfer_op.png'/><p>Total Data Transfered: "+str(optelemgbytesmax)+"GB</p><p>Total Packets Transfered: "+str(format(optelempktsresetmax,","))+" packets</p><img src='./tmp/speeds.png'/><p>Average Throughput: "+str(optelemthroughputavg)+" Gbps</p><p>Average Packets Per Second: "+str(format(optelempktsecavg,","))+" pps</p>"

        optelemhtml+="<p><a href='./tmp/telemetry_op.csv' class='btn btn-info' role='button'>Download Full Telemetry CSV</a></p><h2>Errors</h2>"

        if optelemrxerrorsbool is False:
            optelemhtml+="<h3 style='color:green;font-weight:bold;'>RX Errors: "+str(optelemrxerrors)+"</h3>"
        else:
            optelemhtml+="<h3 style='color:red;font-weight:bold;'>RX Errors: "+str(optelemrxerrors)+"</h3>"
        if optelemtxerrorsbool is False:
            optelemhtml+="<h3 style='color:green;font-weight:bold;'>TX Errors: "+str(optelemtxerrors)+"</h3>"
        else:
            optelemhtml+="<h3 style='color:red;font-weight:bold;'>TX Errors: "+str(optelemtxerrors)+"</h3>"

        if optelemrxdroppedbool is False:
            optelemhtml+="<h3 style='color:green;font-weight:bold;'>RX Dropped Packets: "+str(optelemrxdropped)+"</h3>"
        else:
            optelemhtml+="<h3 style='color:red;font-weight:bold;'>RX Dropped Packets: "+str(optelemrxdropped)+"</h3>"
        if optelemtxdroppedbool is False:
            optelemhtml+="<h3 style='color:green;font-weight:bold;'>TX Dropped Packets: "+str(optelemtxdropped)+"</h3>"
        else:
            optelemhtml+="<h3 style='color:red;font-weight:bold;'>TX Dropped Packets: "+str(optelemtxdropped)+"</h3>"
    else:
        optelemhtml += "<h2>Telemetry</h2><p style='color:red'>Telemetry is disabled</p>"
        
    ophtml = "<div class='row' style='page-break-after: always;'>" + opmembwhtml + "</div>" +\
             "<div class='row' style='page-break-after: always;'>" + opwallpowerhtml + "</div>" +\
             "<div class='row' style='page-break-after: always;'>" + opl3misshtml + "</div>" +\
             "<div class='row' style='page-break-after: always;'>" + opl3hithtml + "</div>" +\
             "<div class='row' style='page-break-after: always;'>" + opl2misshtml + "</div>" +\
             "<div class='row' style='page-break-after: always;'>" + opl2hithtml + "</div>" +\
             "<div class='row'>" + optelemhtml + "</div>"

    opdatapoints = oppcmdatapoints + opwallpdatapoints + optelemdatapoints

    print("\nSetting DPDK Configuration back to original")
    for  line in fileinput.FileInput(rtesdk+"/config/common_base", inplace=1):
        if "CONFIG_RTE_MBUF_DEFAULT_MEMPOOL_OPS" in line and memop is True:
            sys.stdout.write('CONFIG_RTE_MBUF_DEFAULT_MEMPOOL_OPS="ring_mp_mc"\n')
        else:
            sys.stdout.write(line)
    
    subprocess.call("taskset -cp " +
                    cpuafforig + " " +
                    str(os.getpid()),
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
    print("DOAT unpinned from core to speed up build")

    print("Rebuilding DPDK and DPDK App with original configuration options (This can take several minutes)")
    dpdkrebuild = subprocess.Popen("cd "+rtesdk+"; "+dpdkmakecmd+"; cd "+applocation+"; "+appmakecmd+";",
                                   shell=True,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
    animation = "|/-\\"
    idx = 0
    buildtime = 0.0
    while dpdkrebuild.poll() is None:
        m, s = divmod(int(buildtime), 60)
        print('Building . . .',f'{m:02d}:{s:02d}',animation[idx % len(animation)], end="\r")
        idx += 1
        buildtime += 0.1
        time.sleep(0.1)



elif stepsenabled is False:
    print("\nNo Optimisation Steps are enabled skipping optimisation")

print("\nGenerating report")

datapoints = pcmdatapoints+wallpdatapoints+telemdatapoints+opdatapoints

reporttime1 = strftime("%I:%M%p on %d %B %Y", gmtime())
reporttime2 = strftime("%I:%M%p %d/%m/%Y", gmtime())

projectdetailshtml = ""
if projectname is not None and projectname is not "":
    projectdetailshtml += "<p style='font-size: 18px;'>Project: " + projectname + "</p>"
if testername is not None and testeremail is not None and testername is not "" and testeremail is not "":
    projectdetailshtml += "<p style='font-size: 18px;'>Tester: " + testername + " ("+testeremail+")</p>"

testheader1 = ""
testheader2 = ""
if openabled is True:
    testheader1 = "<div class='row'><h1 style='font-weight:bold;'>Original DPDK App</h1></div>"
    testheader2 = "<div class='row'><h1 style='font-weight:bold;'>Modified DPDK App</h1></div>"

indexfile = open("index.html", "w")
indexfile.write("<html><head><title>DOAT Report</title><link rel='stylesheet' href='./webcomponents/bootstrap.341.min.css'><script src='./webcomponents/jquery.341.min.js'></script><script src='./webcomponents/bootstrap.341.min.js'></script><style>@media print{a{display:none!important}img{width:100%!important}}</style></head><body><div class='jumbotron text-center'><h1>DOAT Report</h1><p style='font-size: 14px'>DPDK Optimisation & Analysis Tool</p><p>Report compiled at "+reporttime1+" using "+str(format(datapoints,","))+" data points</p>" + 
                projectdetailshtml +
                "</div><div class='container'>" +
                testheader1 +
                "<div class='row' style='page-break-after: always;'>" + membwhtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + wallpowerhtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l3misshtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l3hithtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l2misshtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l2hithtml + "</div>" +
                "<div class='row'>" + telemhtml + "</div>" +
                testheader2 +
                ophtml +
                "<div class='row'><h2>Test Configuration</h2>"+((json2html.convert(json = (str({section: dict(config[section]) for section in config.sections()})).replace("\'", "\""))).replace("border=\"1\"", "")).replace("table", "table class=\"table\"", 1) + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + reporthtml + "</div>" +
                "</div></body></html>")
indexfile.close()

if generatepdf is True:
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
    pdfconfig = pdfkit.configuration(wkhtmltopdf='/usr/local/bin/wkhtmltopdf')
    pdfkit.from_file('index.html', './tmp/doatreport.pdf', configuration=pdfconfig, options=pdfoptions)

if generatezip is True:
    subprocess.call("cp -r tmp archive; cp config.cfg ./archive; cd archive; mkdir raw_data; mkdir figures; mv *.png ./figures; mv *.csv ./raw_data;  zip -r ../doat_results.zip *; cd ..; mv doat_results.zip ./tmp/; rm -rf archive;",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    shell=True)

server_address = ('', serverport)
print("Serving results on port", serverport)
print("CTRL+c to kill server and exit")
httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
try:
    httpd.serve_forever()
except Exception:
    httpd.server_close()
