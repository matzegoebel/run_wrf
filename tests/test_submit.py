#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 26 12:26:51 2019

Test submit_jobs function

@author: c7071088
"""

import os
from submit_jobs import submit_jobs
import pytest
from misc_tools import Capturing
from collections import Counter
import configs.test.config_test as conf
import shutil
import time
from netCDF4 import Dataset
import misc_tools
import wrf
import pandas as pd

success = {True : 'wrf: SUCCESS COMPLETE IDEAL INIT', False : 'd01 2018-06-20_08:00:00 wrf: SUCCESS COMPLETE WRF'}
outd = os.path.join(conf.outpath, conf.outdir)

test_dir = os.getcwd()
code_dir = "/".join(test_dir.split("/")[:-1])

#%%

def test_basic():
    os.chdir(code_dir)
    for d in [os.environ["wrf_res"] + "/test/pytest", os.environ["wrf_runs"] + "/pytest"]:
        if os.path.isdir(d):
            shutil.rmtree(d)

    for add in ["_mpi", ""]:
        target_dir = "{}/{}{}/test/{}/".format(conf.build_path, conf.wrf_dir_pre, add, conf.ideal_case)
        shutil.copy("{}/test_data/IO_test.txt".format(test_dir), target_dir)
        shutil.copy("{}/test_data/namelists/namelist.input".format(test_dir), target_dir)

    with pytest.raises(RuntimeError, match="Parameter dx used in submit_jobs.py already defined in namelist.input! Rename this parameter!"):
        submit_jobs(config_file="test.config_test_del_args", init=True)

    #check skipping non-initialized runs
    with Capturing() as output:
        submit_jobs(init=False, config_file="test.config_test")
    print(output)
    assert Counter(output)["Run not initialized yet! Skipping..."] == 2


    #initialize and run wrf
    submit_jobs(init=True, exist="s", config_file="test.config_test")
    submit_jobs(init=False, wait=True, exist="s", config_file="test.config_test")

    #check output data
    outfiles = ['fastout_pytest_lin_0','wrfout_pytest_lin_0', 'fastout_pytest_kessler_0', 'wrfout_pytest_kessler_0']
    assert sorted(os.listdir(outd)) == sorted(outfiles)
    file = Dataset(outd + "/fastout_pytest_lin_0")
    t = wrf.extract_times(file, timeidx=None)
    t_corr = pd.date_range(start="2018-06-20T06:00:00", end='2018-06-20T08:00:00', freq="10min")
    assert (t == t_corr).all()

def test_output_exist():
    os.chdir(code_dir)
    for run in os.listdir(conf.run_path):
        file = "{}/{}/wrfinput_d01".format(conf.run_path, run)
        if os.path.isfile(file):
            os.remove(file)
    exist_message = (("s", "Redoing initialization..."), ("s", "Skipping..."), ("o", "Overwriting..."), ("b", "Creating backup..."))
    for init in [True, False]:
        for i, (exist, message) in enumerate(exist_message):
            if init or i > 0:
                print(exist, message)
                with Capturing() as output:
                    combs = submit_jobs(init=init, exist=exist, wait=True, config_file="test.config_test")
                print(output)
                count = Counter(output)
                assert count[message] == combs["n_rep"].sum()
                if "Skipping..." not in message:
                    assert count[success[init]] == combs["n_rep"].sum()

def test_bak_creation():
    os.chdir(code_dir)
    submit_jobs(init=False, exist="b", wait=True, config_file="test.config_test")
    bak = ['fastout_pytest_lin_0_bak_0',
           'wrfout_pytest_lin_0_bak_0',
           'fastout_pytest_lin_0_bak_1',
           'wrfout_pytest_lin_0_bak_1',
           'fastout_pytest_kessler_0_bak_0',
           'wrfout_pytest_kessler_0_bak_0',
           'fastout_pytest_kessler_0_bak_1',
           'wrfout_pytest_kessler_0_bak_1']
    assert sorted(os.listdir(outd + "/bak")) == sorted(bak)

    with pytest.raises(ValueError, match="Value 'a' for -e option not defined!"):
        submit_jobs(init=True, exist="a", config_file="test.config_test")

def test_restart():
    os.chdir(code_dir)
    with Capturing() as output:
        combs = submit_jobs(init=False, restart=True, wait=True, config_file="test.config_test_rst")
    count = Counter(output)
    print(output)
    for m in ["Restart run from 2018-06-20 08:00:00", 'd01 2018-06-20_10:00:00 wrf: SUCCESS COMPLETE WRF']:
        assert count[m] == combs["n_rep"].sum()
    #check output data
    outd = os.path.join(conf.outpath, conf.outdir)
    outfiles = ['rst', 'bak', 'fastout_pytest_lin_0','wrfout_pytest_lin_0', 'fastout_pytest_kessler_0', 'wrfout_pytest_kessler_0']
    assert sorted(os.listdir(outd)) == sorted(outfiles)
    file = Dataset(outd + "/fastout_pytest_lin_0")
    t = wrf.extract_times(file, timeidx=None)
    t_corr = pd.date_range(start="2018-06-20T06:00:00", end='2018-06-20T10:00:00', freq="10min")
    assert (t == t_corr).all()

def test_repeats():
    os.chdir(code_dir)
    combs = submit_jobs(init=True, exist="o", config_file="test.config_test_reps")
    with Capturing() as output:
        submit_jobs(init=False, wait=True, exist="o", config_file="test.config_test_reps")
    print(output)
    count = Counter(output)
    assert count[success[False]] == combs["n_rep"].sum()


def test_mpi():
    os.chdir(code_dir)
    combs = submit_jobs(init=True, wait=True, exist="o", config_file="test.config_test_mpi")

    with Capturing() as output:
        submit_jobs(init=False, pool_jobs=True, wait=True, exist="o", config_file="test.config_test_mpi")
    print(output)
    count = Counter(output)
    m = "Submit IDs: ['pytest_kessler_0', 'pytest_lin_0']"
    assert count[m] == 1
    m = "d01 2018-06-20_07:00:00 wrf: SUCCESS COMPLETE WRF"
    assert count[m] == combs["n_rep"].sum()

def test_get_rt_vmem():
    os.chdir(code_dir)
    for run in os.listdir(conf.run_path):
        rundir ="{}/{}/".format(conf.run_path, run)
        shutil.copy("tests/test_data/resources.info", rundir)

    with Capturing() as output:
        combs = submit_jobs(init=False, check_args=True, use_job_scheduler=True, exist="o", config_file="test.config_test_mpi")
    print(output)
    count = Counter(output)
    messages = ['Get runtime from previous runs', 'Get vmem from previous runs', 'Use vmem per slot: 148.3M']
    for m in messages:
        assert count[m] == combs["n_rep"].sum()
    rundirs = [rd + "_0" for rd in combs["run_dir"].values]
    timing = misc_tools.get_runtime_all(rundirs, all_times=False)["timing"].values
    messages = ["Runtime per time step: {0:.5f} s".format(t) for t in timing]
    for m in messages:
        assert count[m] == 1

    for d in [os.environ["wrf_res"] + "/test/pytest", os.environ["wrf_runs"] + "/pytest"]:
        shutil.rmtree(d)



#TODO
#Domain size must be multiple of lx
#check name list changes
# test history streams
