# DOAT
> DPDK Optimisation &amp; Analysis Tool

![Status](https://img.shields.io/badge/status-beta-yellow.svg?style=flat-square)
[![Maintenance](https://img.shields.io/badge/maintained-yes-green.svg?style=flat-square)](https://GitHub.com/conorwalsh/doat/graphs/commit-activity)
[![GitHub tag](https://img.shields.io/github/tag/conorwalsh/doat.svg?style=flat-square)](https://GitHub.com/conorwalsh/doat/tags/)
![Status](https://img.shields.io/github/languages/code-size/conorwalsh/doat.svg?style=flat-square)
[![GitHub license](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](https://github.com/conorwalsh/doat/blob/master/LICENSE)
[![made-with-python](https://img.shields.io/badge/Made%20with-Python3-1f425f.svg?style=flat-square)](https://www.python.org/)
[![HitCount](http://hits.dwyl.io/conorwalsh/doat.svg)](http://hits.dwyl.io/conorwalsh/doat)

[DPDK](https://dpdk.org) is a set of C libraries for fast packet processing. DOAT is a tool for analysing and assisting in the optimisation of applications built using DPDK. DOAT is an out of band analysis tool that doesnt require the DPDK app to be changed.

## Installation

### Linux:
* Install PCM:

    [github.com/opcm/pcm](https://github.com/opcm/pcm)
* Install IPMItool:
    ```sh 
    apt-get install ipmitool
    ```
* Install wkhtmltopdf (Used for PDF reports ignore if not needed):

    [wkhtmltopdf.org](https://wkhtmltopdf.org/)
* Clone Project:
    ```sh
    git clone https://github.com/conorwalsh/doat.git
    ```
* Install Python3 dependendancies:
    ```sh
    pip3 install -r requirements.txt
    ```
_Note: DOAT has only been tested on Ubuntu 18.04_

## Usage

* Update the configuration options in _config.cfg_
* Update the platform setup to reflect the _config.cfg_
* Run DOAT
    ```sh
    ./main.py
    ```
Example DOAT run:
![](https://conorwalsh.net/doat/doatrun.png)

_Example DOAT Reports can be seen in the examples directory of this repo_

## Release History

* 0.8
    * First beta release of DOAT, testing and validation still in progress (95% code coverage)
* <0.8
    * Unversioned development of DOAT (Changes can be seen in commit history)
* proofofconcept (see branch)
    * This was the initial PoC for DOAT to prove that the concept was possible

## Meta

Conor Walsh – [@conorwalsh_ire](https://twitter.com/conorwalsh_ire) – conor@conorwalsh.net

DOAT is distributed under the MIT license. See ``LICENSE`` for more information.

[https://github.com/conorwalsh/doat](https://github.com/conorwalsh/doat/)

## Why?

I completed 2 internships with Intel's Network Platforms Group (NPG) and while I was there I did a lot of work related to the optimisation and analysis of various DPDK projects. Some of the projects I worked on were released by Intel [01.org/access-network-dataplanes](https://01.org/access-network-dataplanes). I found the analysis process to be very time consuming and repetitive. I thought these processes would be rife for automation.

As part of the final year of my engineering degree I had to complete a final year project. I partnered with Intel to start the DOAT open-source project for my final year project.

## Contributing

1. Fork it (<https://github.com/conorwalsh/doat/fork>)
2. Create your feature branch (`git checkout -b feature/fooBar`)
3. Commit your changes (`git commit -am 'Add some fooBar'`)
4. Push to the branch (`git push origin feature/fooBar`)
5. Create a new Pull Request
