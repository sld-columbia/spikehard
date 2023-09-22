#!/bin/bash

root_dir=$(dirname "$(dirname "$(readlink -f "$0")")")

if [ -d "${root_dir}/.python" ]; then
    rm -rf ${root_dir}/.python
fi

# setup virtual environment and install basic dependencies
python3 -m venv ${root_dir}/.python/
source ${root_dir}/.python/bin/activate
python -m pip install --upgrade pip
python -m pip install wheel
python -m pip install -r ${root_dir}/requirements.txt

# install dependencies for ESP
python -m pip install Pmw

# setup testing
cd ${root_dir}/hardware/tb/iverilog
make clean
make
