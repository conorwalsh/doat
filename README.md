# <img src="/webcomponents/doat_logo.png" height="120" />
> DOAT: DPDK Optimisation &amp; Analysis Tool

[![Repo Tests](https://github.com/conorwalsh/doat/actions/workflows/test_repo.yaml/badge.svg)](https://github.com/conorwalsh/doat/actions/workflows/test_repo.yaml)
[![CodeQL](https://github.com/conorwalsh/doat/actions/workflows/codeql-analysis.yaml/badge.svg)](https://github.com/conorwalsh/doat/actions/workflows/codeql-analysis.yaml)
![Status](https://img.shields.io/badge/status-released-green.svg?style=flat-square)
[![Maintenance](https://img.shields.io/badge/maintained-yes-green.svg?style=flat-square)](https://GitHub.com/conorwalsh/doat/graphs/commit-activity)
[![GitHub tag](https://img.shields.io/badge/version-21.11-green.svg?style=flat-square)](https://GitHub.com/conorwalsh/doat/tags/)
![Code Size](https://img.shields.io/github/languages/code-size/conorwalsh/doat.svg?style=flat-square)
[![Lines of Code](https://tokei.rs/b1/github/conorwalsh/doat?style=flat-square)]()
[![GitHub license](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](https://github.com/conorwalsh/doat/blob/master/LICENSE)
[![made-with-python](https://img.shields.io/badge/Made%20with-Python3-1f425f.svg?style=flat-square)](https://www.python.org/)

[DPDK](https://dpdk.org) is a set of C libraries for fast packet processing. DOAT (_Pronunciation: d&omacr;t_) is a tool for analysing and assisting in the optimisation of applications built using DPDK. DOAT is an out of band analysis tool that does not require the DPDK app to be changed.

## Installation

### Linux:
* Install ZIP:
    ```sh
    apt-get install zip
    ```
* Install PCM:

    [github.com/opcm/pcm](https://github.com/opcm/pcm)
* Install IPMItool:
    ```sh 
    apt-get install ipmitool
    ```
* Install wkhtmltopdf (Used for PDF reports ignore if PDF reports not needed):
    ```sh
    apt-get install wkhtmltopdf
    ```
* Clone Project:
    ```sh
    git clone https://github.com/conorwalsh/doat.git
    ```
* Install Python3 dependencies:
    ```sh
    pip3 install -r requirements.txt
    ```
_DOAT has been tested on Ubuntu 18.04 and 20.04_

## Usage

* Update the configuration options in _config.cfg_
* Update the platform setup to reflect the _config.cfg_
* Start your Traffic Generator and set the traffic rate to your calculated Zero Packet Loss (ZPL) rate as DOAT does not control traffic flow
* Run DOAT
    ```sh
    ./main.py
    ```
Example DOAT run:
![](/examples/doatrun.png)

[Example DOAT Report](/examples/doatreport.pdf)

_Example DOAT Reports can be seen in the examples directory of this repo_

## Release History

* 21.11
    * Tested with latest DPDK LTS release 21.11
    * No major updates
* 21.08
    * Fixed telemetry items that were renamed
    * More robust way to find wkhtmltopdf
    * Other minor fixes 
* 20.11
    * DOAT now compatible with DPDK 20.11
    * Dependencies updated
    * Transitioned fully from make to meson as specified by DPDK
    * Updated from DPDK v1 telemetry to v2
    * CI and automated testing integrated
    * Version of DOAT will now track DPDK (DOAT version should match last DPDK version tested with it)
* 1.0
    * First full release of DOAT
    * Testing and validation complete
* 0.9
    * Release Candidate 1
    * Testing and validation almost complete
* 0.8
    * First beta release of DOAT (>95% code complete)
    * Likely to be few changes before release candidate (0.9)
    * Testing and validation still in progress
    * Beta Release
* <0.8
    * Un-versioned development of DOAT
    * Changes pre-beta can be seen in commit history
* minimumviableproduct
    * First version of DOAT that had the initial working main DOAT functions
    * Alpha Release
* proofofconcept
    * This was the initial PoC for DOAT to prove that the concept was possible

## Optimisation

DOAT is designed to be a platform that can be expanded on by others by adding extra analysis tools or optimisation steps.

Available Optimisation Steps:
* Memory Bandwidth Optimisation
    * This optimisation step is a process for optimising memory bandwidth usage of a dual threaded DPDK application.
    * This is based on [this paper](https://software.intel.com/en-us/articles/optimize-memory-usage-in-multi-threaded-data-plane-development-kit-dpdk-applications), which was published by Intel (written by the original DOAT author).

The optimisation steps work by manipulating the options in the DPDK configuration file (/config/rte_config.h), rebuilding DPDK with these new options and comparing the results. If the results are better, the changes are suggested to the user.

An application that works well for demonstarting the effects of the Memory Bandwidth Optimisation step is the qos_sched_custom app that the author developed and used to test the optimisation for DOAT. The app is available here: [qos_sched_custom](https://github.com/conorwalsh/qos_sched_custom). This app is based on the DPDK Qos Scheduler Sample Application which is designed to showcase what DPDK QoS can do. The app was built to profile the performance of DPDK QoS. The app expands the information that is printed to the user and now displays cycle costs. The app also uses MAC addresses for classifying packets which is easier to use.

_The DPDK rte_config.h file has many options and as more suitable optimisation steps are discovered, they can be added to DOAT_

## Website

More information about this project can be found on the projects website [doat.dev](https://doat.dev/).

## Meta

Conor Walsh – conor@conorwalsh.net

DOAT is distributed under the MIT license. See ``LICENSE`` for more information.

[https://github.com/conorwalsh/doat](https://github.com/conorwalsh/doat/)

## Why?

I completed 2 internships with Intel's Network Platforms Group (NPG) and while I was there I did a lot of work related to the optimisation and analysis of various DPDK projects. Some of the projects I worked on were released by Intel [01.org/access-network-dataplanes](https://01.org/access-network-dataplanes). I found the analysis process to be very time consuming and repetitive. I thought these processes would be rife for automation.

As part of the final year of my engineering degree, I had to complete a final year project. I collaborated with Intel to start the DOAT open-source project as part of my final year project.

## Contributing

1. Fork it (<https://github.com/conorwalsh/doat/fork>)
2. Create your feature branch (`git checkout -b feature/fooBar`)
3. Commit your changes (`git commit -am 'Add some fooBar'`)
4. Push to the branch (`git push origin feature/fooBar`)
5. Create a new Pull Request
