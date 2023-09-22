#!/bin/bash

root_dir=$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")")

source ${root_dir}/.python/bin/activate
