#!/bin/bash
set -e

app="spikehard_rtl"
manual="false"
gui="false"
config="false"
clean="false"
spikehard_root_dir=$(dirname "$(dirname "$(readlink -f "$0")")")
esp_root_dir="${spikehard_root_dir}/../esp"
app_root_dir="${spikehard_root_dir}/hardware"
soc="xilinx-vcu128-xcvu37p"
param_ptr=""
for arg in "$@"
do
    if [[ ${param_ptr} != "" ]]; then
        eval "${param_ptr}=${arg}"
        param_ptr=""
    elif [ ${arg} == "-g" ] || [ ${arg} == "--gui" ]; then
        gui="true"
    elif [ ${arg} == "-c" ] || [ ${arg} == "--config" ]; then
        config="true"
    elif [ ${arg} == "-C" ] || [ ${arg} == "--clean" ]; then
        clean="true"
    elif [ ${arg} == "-s" ] || [ ${arg} == "--soc" ]; then
        param_ptr="soc"
    elif [ ${arg} == "-m" ] || [ ${arg} == "--manual" ]; then
        manual="true"
    elif [ ${arg} == "-a" ] || [ ${arg} == "--app" ]; then
        param_ptr="app"
    elif [ ${arg} == "-p" ] || [ ${arg} == "--app-root-dir" ]; then
        param_ptr="app_root_dir"
    fi
done

app_root_dir=$(readlink -f "${app_root_dir}")

# clear args so can source other bash files
set --

echo "Parameters:"
echo "  App Root Path: ${app_root_dir}"
echo "  SpikeHard Root Path: ${spikehard_root_dir}"
echo "  ESP Root Path: ${esp_root_dir}"
echo "  SoC: ${soc}"

if [ ${clean} == "true" ]; then
    cd ${esp_root_dir}
    git reset --hard HEAD
    git clean -dxf
fi

rm -f ${esp_root_dir}/accelerators/rtl/${app}
ln -s ${app_root_dir} ${esp_root_dir}/accelerators/rtl/${app}

cd ${esp_root_dir}/socs/${soc}
make ${app}-hls

# run config if first time building or if desired.
if [[ ! -d "soft-build" || ${config} == "true" ]]; then
    make esp-xconfig
fi

cpu=$(grep 'CPU_ARCH = ' ${esp_root_dir}/socs/${soc}/socgen/esp/.esp_config | cut -d" "  -f3)

if [[ ${cpu} == "" ]]; then
    echo "Invalid configuration."
    exit 1
fi

make ${app}-baremetal

# Automatically run simulator if !manual.
rm -f ${esp_root_dir}/socs/${soc}/vsim.tcl
if [ ${manual} == "false" ]; then
cat > ${esp_root_dir}/socs/${soc}/vsim.tcl <<EOF
run -a
exit
EOF
fi

TEST_PROGRAM=./soft-build/${cpu}/baremetal/${app}.exe make sim

rm -f ${esp_root_dir}/socs/${soc}/vsim.tcl
rm -f ${esp_root_dir}/accelerators/rtl/${app}
