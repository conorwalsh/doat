#!/usr/bin/env python3

from doatFunctions import *
import subprocess
import configparser
import pandas
import numpy as np
import atexit
import matplotlib.pyplot as plt
from http.server import SimpleHTTPRequestHandler, HTTPServer
from time import gmtime, strftime
import pdfkit

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

dpdkcmd = config['APPPARAM']['dpdkcmd']
if dpdkcmd is not None:
    print("DPDK app launch command:", dpdkcmd)
else:
    sys.exit("No DPDK command was specified (dpdkcmd in config.cfg), ABORT!")

telemetryenabled = False
if config['APPPARAM'].getboolean('telemetry') is True:
    telemetryenabled = True
    print("DPDK telemetry is enabled")
else:
    print("DPDK telemetry is disabled")

socketpath = config['APPPARAM']['socketpath']
if socketpath is not None and telemetryenabled is True:
    print("DPDK app telemetry socket path:", socketpath)
elif telemetryenabled is True:
    sys.exit("Telemetry is enabled but socketpath in config.cfg has not been set, ABORT!")

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

subprocess.call("taskset -cp " +
                str(testcore) + " " +
                str(os.getpid()),
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)

print("Test pinned to core",
      testcore,
      "PID:",
      os.getpid())

print("Starting Process")
proc = subprocess.Popen(dpdkcmd,
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
    print("Test process starting")
else:
    sys.exit("Test process failed to start, ABORT!")

print("Allow application to startup . . .")
progress_bar(startuptime)

if proc.poll() is not None:
    sys.exit("Application died or failed to start, ABORT!")
else:
    print("Test process started successfully, , PID: ",
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
    print("SUCCESS: Test process is still alive after test")
else:
    print("ERROR: Test process died during test")
    appdiedduringtest = True

print("Killing test processes")

kill_group_pid(testpid)

kill_group_pid(pcm.pid)

kill_group_pid(wallp.pid)

kill_group_pid(telem.pid)

if appdiedduringtest is True:
    sys.exit("Test invalid due to DPDK App dying during test, ABORT!")

print("Generating report")

f = open('tmp/pcm.csv', 'r')
filedata = f.read()
f.close()

newdata = filedata.replace(";", ",")

f = open('tmp/pcm.csv', 'w')
f.write(newdata)
f.close()

pcmdata = pandas.read_csv('tmp/pcm.csv')

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

wallpdata = pandas.read_csv('tmp/wallpower.csv', sep=',',)
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
    plt.plot(socketx, l3missmaster, label="Master Core ("+str(appmaster)+")")
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
    plt.plot(socketx, l2missmaster, label="Master Core ("+str(appmaster)+")")
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
    plt.plot(socketx, l3hitmaster, label="Master Core ("+str(appmaster)+")")
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
    plt.plot(socketx, l2hitmaster, label="Master Core ("+str(appmaster)+")")
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

telemdata = pandas.read_csv('tmp/telemetry.csv', sep=',',)
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
ax1.legend(loc=0)
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
ax1.legend(loc=0)
ax2.legend(loc=0)
plt.title("Transfer Speeds")
plt.xlim(left=0)
plt.xlim(right=max(telemtime))
plt.savefig("./tmp/speeds.png", bbox_inches="tight")


telemhtml = "<h2>Telemetry</h2><img src='./tmp/pktdist.png'/><br/><img src='./tmp/transfer.png'/><p>Total Data Transfered: "+str(telemgbytesmax)+"GB</p><p>Total Packets Transfered: "+str(telempktsresetmax)+" packets</p><img src='./tmp/speeds.png'/><p>Average Throughput: "+str(telemthroughputavg)+" Gbps</p><p>Average Packets Per Second: "+str(telempktsecavg)+" pps</p>"

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

#telemhtml+="<p><a href='./tmp/telemetry.csv' class='btn btn-info' role='button'>Download Full Telemetry CSV</a></p>"

reporthtml="<p style='text-align:center'><a href='./tmp/doatreport.pdf' class='btn btn-success' role='button' style='font-size: 28px;'>Download PDF Report</a></p>"

datapoints = pcmdatapoints+wallpdatapoints+telemdatapoints

#telemhtml+="<h2>Data Points</h2><p>This report was compiled using "+str(datapoints)+" data points</p>"

reporttime1 = strftime("%I:%M%p on %d %B %Y", gmtime())
reporttime2 = strftime("%I:%M%p %d/%m/%Y", gmtime())

indexfile = open("index.html", "w")
indexfile.write("<html><head><title>DOAT Report</title><link rel='stylesheet' href='./webcomponents/bootstrap.341.min.css'><script src='./webcomponents/jquery.341.min.js'></script><script src='./webcomponents/bootstrap.341.min.js'></script><style>@media print{a{display:none!important}}</style></head><body><div class='jumbotron text-center'><h1>DOAT Report</h1><p style='font-size: 14px'>DPDK Optimisation & Analysis Tool</p><p>Report compiled at "+reporttime1+" using "+str(format(datapoints,","))+" data points</p></div><div class='container'>" +
                "<div class='row' style='page-break-after: always;'>" + membwhtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + wallpowerhtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l3misshtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l3hithtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l2misshtml + "</div>" +
                "<div class='row' style='page-break-after: always;'>" + l2hithtml + "</div>" +
                "<div class='row'>" + telemhtml + "</div>" +
                "<div class='row'>" + reporthtml + "</div>" +
                "</div></body></html>")
indexfile.close()

pdfoptions = {'page-size': 'A4',
           'quiet': '',
           'margin-top': '25.4',
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

# print("Read Avg:",socketreadavg,"MBps")
# print("Write Avg:",socketwriteavg,"MBps")
# print("Write to Read Ratio:",socketwritereadratio)
# print("Wall Power Avg:",wallpoweravg,"Watts")

server_address = ('', serverport)
print("Serving results on port", serverport)
print("CTRL+c to kill server and exit")
httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
try:
    httpd.serve_forever()
except Exception:
    httpd.server_close()
