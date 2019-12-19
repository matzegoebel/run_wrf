#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Nov 22 17:36:46 2019

Settings for submit_jobs.py
Test settings for automated tests.

Assert RuntimeError due to dx being in del_args

@author: matze

"""
import os
from collections import OrderedDict as odict
import misc_tools
from configs.test.config_test import *

# non-namelist parameters that will not be included in namelist file
del_args =   ["dx", "start_time", "end_time", "nz", "dz0","dz_method", "min_gridpoints_x", "min_gridpoints_y", "lx", "ly", "spec_hfx", "input_sounding",
              "n_rep", "isotropic_res", "pbl_res", "dt_f", "radt_min"]