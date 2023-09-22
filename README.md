# SpikeHard: Efficiency-Driven Neuromorphic Hardware for Heterogeneous Systems-on-Chip

SpikeHard is an open-source, runtime-programmable neuromorphic hardware accelerator for [ESP](https://www.esp.cs.columbia.edu/) SoCs.

## Quick Start

Environment setup:
```bash
git clone --recursive --depth 1 --branch 87f0e1f1325b4e210bee358b898499b3e27fdf7f https://github.com/sld-columbia/esp.git
git clone https://github.com/sld-columbia/spikehard.git
cd spikehard
script/install_env.sh
source script/setup_env.sh
```
Be sure to clone ESP in the same directory as SpikeHard but **not** inside SpikeHard, and follow the [ESP documentation](https://www.esp.cs.columbia.edu/docs/setup/) to properly setup ESP including the necessary toolchains. SpikeHard has been tested with ESP version: `87f0e1f1325b4e210bee358b898499b3e27fdf7f`. Using later versions of ESP might require reconfiguring the SoC, which we have already done for you in `hardware/util/preconfigured_socs`.

To restructure the original 64x64 VMM-O model to 32x32 and tune the tick period as well, run the following:
```bash
python hardware/util/to_unit_tests.py vmm_o 0 64 64 32 32
```
This will output a test that can be run as follows:
```bash
pytest -o log_cli=True -s -v --log-cli-level=DEBUG hardware/tb/tests/networks/altered/vmm_o/test_vmm_o_32.py
```
Please note that these Python tests require the Icarus Verilog simulator to be installed (e.g. via `sudo apt install iverilog`). And it also requires `myhdl` bindings to be built, which is automically done by `script/install_env.sh`, but can also be done as follows:
```bash
cd hardware/tb/iverilog
make clean
make
```

To synthesise an implementation with 32x32 VMM-O and deploy it to FPGA, all necessary environment variables required by ESP, such as the path to your Xilinx Vivado installation, should first be specified. You will also want to change the values in `hardware/util/preconfigured_socs/xilinx-vcu128-xcvu37p/Makefile` so that ESP is able to access your FPGA. Please consult the ESP documentation for more information. Once this is all configured, run:
```bash
python hardware/util/fpga_util.py -c 1 32 32 -m vmm_o -s # generate code & synthesise
python hardware/util/fpga_util.py -c 1 32 32 -m vmm_o -p # prepare synthesised SoC to run
script/run_linux_fpga.sh
```
Once logged into the FPGA, you can run a Linux application that offloads VMM-O onto SpikeHard and verifies that it is being executed correctly. To this end, run:
```bash
/applications/test/spikehard_rtl.exe
```
By default, at the end this will output the overall latency from a single run. That being said, this Linux application has several optional arguments:
```
-m <n>   number of runs to determine average model loading overhead [default <n>=0]
-i <n>   number of runs to determine average invocation overhead [default <n>=0]
-l <n>   number of runs to determine average latency (excluding model and invocation overhead, which default to 0) [default <n>=1]
-t <n>   number of runs to determine average throughput (used by MNIST, not used by VMM) [default <n>=1]
-c <n>   number of clock cycles per tick (i.e. tick period) [default is model-specified]
```
Once you are done with running a particular SoC implementation, you should "unprepare" it so that a different implementation can be used instead. To unprepare 32x32 VMM-O for example, run:
```bash
python hardware/util/fpga_util.py -c 1 32 32 -m vmm_o -u
```
To re-prepare it:
```bash
python hardware/util/fpga_util.py -c 1 32 32 -m vmm_o -p
```
Notice that we don't have to re-synthesise the SoC, synthesis is only needed if we generate a new implementation.

SpikeHard should also work with the LEON3 CPU as well as in baremetal, however, this has not been tested in a long time so your mileage may vary.

## Citation

To refer to SpikeHard in a publication, please cite the following paper:
```
@article{10.1145/3609101,
  author = {Clair, Judicael and Eichler, Guy and Carloni, Luca P.},
  title = {{SpikeHard: Efficiency-Driven Neuromorphic Hardware for Heterogeneous Systems-on-Chip}},
  year = {2023},
  volume = {22},
  number = {5s},
  doi = {10.1145/3609101},
  journal = {ACM Trans. Embed. Comput. Syst.},
  articleno = {106},
  numpages = {22}
}
```

## License

SpikeHard is based on RANC, and so a significant portion of code was taken from the [RANC repository](https://github.com/UA-RCL/RANC/tree/master). Since RANC is released under the permissive MIT License, so is SpikeHard. This license does not apply to code from or generated by ESP, which retains its original license.
