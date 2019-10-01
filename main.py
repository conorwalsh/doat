#!/usr/bin/env python3
import os
from doatFunctions import *
import subprocess
import configparser
import pandas
import numpy as np
import atexit
import matplotlib.pyplot as plt
from http.server import SimpleHTTPRequestHandler, HTTPServer

#Print startup message
doat_motd()

#Check system setup
sys_check()

config = configparser.ConfigParser()
config.read('config.cfg')
dpdkcmd=config['DOAT']['dpdkcmd']
if dpdkcmd is not None:
    print("DPDK app launch command:",dpdkcmd)
else:
    sys.exit("No DPDK command was specified (dpdkcmd in config.cfg), ABORT!")
startuptime=int(config['DOAT']['startuptime'])
if startuptime is not None:
    print("Startup time for DPDK App:",startuptime)
else:
    sys.exit("No startup time was specified (startuptime in config.cfg), ABORT!")
testruntime=int(config['DOAT']['testruntime'])
if testruntime is not None:
    print("Startup time for DPDK App:",testruntime)
else:
    sys.exit("No test run time was specified (testruntime in config.cfg), ABORT!")
testcore=int(config['CPU']['testcore'])
testsocket=int(subprocess.check_output("cat /proc/cpuinfo | grep -A 18 'processor\s\+: "+str(testcore)+"' | grep 'physical id' | head -1 | awk '{print substr($0,length,1)}'", shell=True))
if testcore is not None:
    print("Test software core:",testcore,"(Socket: "+str(testsocket)+")")
else:
    sys.exit("No test core was specified (testcore in config.cfg), ABORT!")
appmasterenabled=True
appmaster=int(config['CPU']['appmaster'])
appmastersocket=int(subprocess.check_output("cat /proc/cpuinfo | grep -A 18 'processor\s\+: "+str(appmaster)+"' | grep 'physical id' | head -1 | awk '{print substr($0,length,1)}'", shell=True))
if appmaster is not None:
    print("DPDK app master core:",appmaster,"(Socket: "+str(appmastersocket)+")")
else:
    appmasterenabled=False
    print("DPDK app has no master core")
appcores=[int(e) for e in (config['CPU']['appcores']).split(",")]
appcoresno=len(appcores)
if appcores is not None:
    print("DPDK app has",appcoresno,"cores:",appcores)
else:
    sys.exit("No DPDK app cores were specified (appcores in config.cfg), ABORT!")
appcoressockets=[]
appsocket=None
for x in appcores:
    appcoressockets.append(int(subprocess.check_output("cat /proc/cpuinfo | grep -A 18 'processor\s\+: "+str(x)+"' | grep 'physical id' | head -1 | awk '{print substr($0,length,1)}'", shell=True)))
if appmasterenabled:
    if all(x == appcoressockets[0] for x in appcoressockets) and appmastersocket == appcoressockets[0]:
        appsocket=appcoressockets[0]
        print("DPDK app running on socket",appsocket)
    else:
        sys.exit("DPDK app cores and master core must be on the same socket, ABORT!")
else:
    if all(x == appcoressockets[0] for x in appcoressockets):
        appsocket=appcoressockets[0]
        print("DPDK app running on socket",appsocket)
    else:
        sys.exit("DPDK app cores must be on the same socket, ABORT!")
pcmdir=config['TOOLS']['pcmdir']
if pcmdir is not None:
    print("PCM directory:",pcmdir)
else:
    sys.exit("No PCM directory was specified (pcmdir in config.cfg), ABORT!")

if not os.path.exists("tmp"):
    os.makedirs('tmp')

subprocess.call("taskset -cp "+str(testcore)+" "+str(os.getpid()), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("Test pinned to core",testcore,"PID:",os.getpid())

print("Starting Process")
proc = subprocess.Popen(dpdkcmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setsid)
testpid = proc.pid

#TODO Deal with measurement  
#Once Test Process is spawned add catch to kill test process if test abandoned
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
    print("Test process started successfully, , PID: ",testpid)

print('Starting Measurements . . .')
membw = subprocess.Popen(pcmdir+'pcm-memory.x 0.25 -csv=tmp/membw.csv', stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setsid)
wallp = subprocess.Popen("echo 'power,time\n' > tmp/wallpower.csv; while true; do ipmitool sdr | grep 'PS1 Input Power' | cut -c 20- | cut -f1 -d 'W' | tr -d '\n' | sed 's/.$//' >> tmp/wallpower.csv; echo -n ',' >> tmp/wallpower.csv; date +%s >> tmp/wallpower.csv; sleep 0.5; done", stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setsid)
progress_bar(2)
if membw.poll() is not None:
    kill_group_pid(membw.pid)
    sys.exit("PCM died or failed to start, ABORT!")
if wallp.poll() is not None:
    kill_group_pid(wallp.pid)
    sys.exit("IPMItool died or failed to start, ABORT!")

print("Running Test . . .")
progress_bar(testruntime)

if proc.poll() is None:
    print("SUCCESS: Test process is still alive after test")
else:
    print("ERROR: Test process died during test")

print("Killing test process")
kill_group_pid(testpid)
kill_group_pid(membw.pid)
kill_group_pid(wallp.pid)

membwdata = pandas.read_csv('tmp/membw.csv',sep=';',)

socketread = np.asarray((membwdata["SKT"+str(appsocket)+".8"].tolist())[1:]).astype(np.float)
socketwrite = np.asarray((membwdata["SKT"+str(appsocket)+".9"].tolist())[1:]).astype(np.float)

socketreadavg = round(sum(socketread)/len(socketread), 2)
socketwriteavg = round(sum(socketwrite)/len(socketwrite), 2)
socketwritereadratio = round(socketwriteavg/socketreadavg,2)

socketx = []
timex = 0;
for x in socketread:
    socketx.append(timex)
    timex += 0.25

plt.figure(0)
plt.plot(socketx, socketread, label = "Read")
plt.plot(socketx, socketwrite, label = "Write")
plt.xlabel("Time (Seconds)")
plt.ylabel("Bandwidth (MBps)")
plt.title("Memory Bandwidth")
plt.legend()
plt.ylim(bottom=0)
plt.ylim(top=(max(socketwrite)+100))
plt.savefig("./tmp/membw.png", bbox_inches="tight")

wallpdata = pandas.read_csv('tmp/wallpower.csv',sep=',',)
wallpower = np.asarray(wallpdata["power"].tolist()).astype(np.int)
wallpowertime = np.asarray(wallpdata["time"].tolist()).astype(np.int)
wallpowertimezero = wallpowertime[0]
wallpowerx = []
for x in wallpowertime:
    wallpowerx.append(x-wallpowertimezero)
wallpoweravg = round(sum(wallpower)/len(wallpower),1)

plt.figure(1)
plt.plot(wallpowerx, wallpower, label = "Wall Power")
plt.xlabel("Time (Seconds)")
plt.ylabel("Power (Watts)")
plt.title("Wall Power")
plt.legend()
plt.ylim(bottom=0)
plt.ylim(top=(max(wallpower)+50))
plt.savefig("./tmp/wallpower.png", bbox_inches="tight")

indexfile=open("index.html","w")
indexfile.write("<html><body><h1>DOAT Report</h1><h2>Memory Bandwidth</h2><img src='./tmp/membw.png'/><p>Read Avg: "+str(socketreadavg)+"MBps</p><p>Write Avg: "+str(socketwriteavg)+"MBps</p><p>Write to Read Ratio: "+str(socketwritereadratio)+"</p><p><a href='./tmp/membw.csv'>Download Memory BW CSV</a><h2>Wall Power</h2><img src='./tmp/wallpower.png'/><p>Wall Power Avg: "+str(wallpoweravg)+"Watts</p><p><a href='./tmp/wallpower.csv'>Download Power CSV</a></body></html>")
indexfile.close()

print("Read Avg:",socketreadavg,"MBps")
print("Write Avg:",socketwriteavg,"MBps")
print("Write to Read Ratio:",socketwritereadratio)
print("Wall Power Avg:",wallpoweravg)

server_address = ('', 80)   
print("Serving results on port 80")
print("CTRL+c to kill server and exit")
httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
try:                                                                                                                                  
    httpd.serve_forever()
except Exception:
    httpd.server_close()
