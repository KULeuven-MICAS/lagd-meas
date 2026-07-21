#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Date: 2026/07/21
# Description: This script is to download the lagd bitstream on ZCU102

# If you want to run this script in terminal, please do the following:
# 1: convert the notebook into pure python script (you can also manually copy the code into the script):
#    jupyter nbconvert --to script lagd_v1_notebook.ipynb
# 2: run the command below in terminal (you need to enter the sudo password for the first time):
#    sudo -E /usr/local/share/pynq-venv/bin/python lagd_v1_notebook.py


# In[66]:


import os
import pwd
import logging
import platform
from pynq import Bitstream

logger = logging.getLogger(__name__)

# Initialize the logger
logging_level = logging.INFO
logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging_level, format=logging_format)
# Load the bitstream
bitfile = "lagd.zcu102.bit"
logger.info(f"Current host: {platform.node()}, username: {pwd.getpwuid(os.geteuid()).pw_name}")
logger.info(f"Start loading the bitstream {bitfile}, CWD: {os.getcwd()}")
bit = Bitstream(bitfile)
bit.download()
logger.info("Bitstream loaded")


# In[ ]: