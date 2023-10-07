import os
import sys
import subprocess
import pathlib

from common_util import ROOT_DIR, ESP_SOCS_DIR, DEFAULT_SOC
from test_util import basic_test_util
from app_util import app_util


class fpga_util():
  def __init__(self, model_names, num_axons, num_neurons, altered=True, fpga_name=DEFAULT_SOC, folder_prefix=None):
    self.model_names = model_names
    self.num_axons = num_axons
    self.num_neurons = num_neurons
    self.altered = altered
    self.fpga_name = fpga_name
    self.folder_prefix = folder_prefix

  def run_cmd(self, cmd):
    print("running command: '{}'".format(cmd))
    subprocess.run(cmd, check=True, shell=True)

  @property
  def factory_path(self):
    return os.path.join(ESP_SOCS_DIR, self.fpga_name)

  @property
  def unprepared_path(self):
    return os.path.join(ESP_SOCS_DIR,
                        "{}-{}-{}-{}-{}".format(f"{self.fpga_name}-spikehard",
                                   "-".join(self.model_names) if self.folder_prefix is None else self.folder_prefix,
                                   self.altered, self.num_axons, self.num_neurons))
  
  @property
  def prepared_path(self):
    return os.path.join(ESP_SOCS_DIR, f"{self.fpga_name}-spikehard")

  def __gen_app(self):
    au = app_util(num_axons=self.num_axons, num_neurons=self.num_neurons, minimise_arch_dims=True, num_outputs=self.num_axons, minimise_num_outputs=(
      len(self.model_names) == 1), output_core_x_coordinate=(0 if self.altered else None), output_core_y_coordinate=(0 if self.altered else None))
    for model_name in self.model_names:
      au.add_model(model_name, basic_test_util.gen_test_params(model_name, altered=self.altered,
                   num_axons=self.num_axons, num_neurons=self.num_neurons), homogeneous=False)
    au.finalise()

  def synthesise(self):
    self.__gen_app()
    assert not os.path.exists(self.prepared_path), self.prepared_path
    self.run_cmd('cp -r "{}" "{}"'.format(self.factory_path, self.prepared_path))
    self.run_cmd('bash "{}/script/run_vivado_syn.sh" --config'.format(ROOT_DIR))
    self.unprepare()

  def prepare_to_run(self):
    self.run_cmd('mv "{}" "{}"'.format(self.unprepared_path, self.prepared_path))
    self.__gen_app()

  def unprepare(self):
    self.run_cmd('mv "{}" "{}"'.format(self.prepared_path, self.unprepared_path))


def main():
  cfgs = []
  
  idx = 1
  while sys.argv[idx] == '-c':
    idx += 1

    altered, num_axons, num_neurons = [int(arg) for arg in sys.argv[idx:idx+3]]
    assert altered in (0, 1), altered
    altered = bool(altered)
    idx += 3

    model_names = []
    while sys.argv[idx] == "-m":
      model_names.append(sys.argv[idx + 1])
      idx += 2
    
    cfgs.append((model_names, num_axons, num_neurons, altered))

  action = sys.argv[idx]

  for cfg in cfgs:
    fu = fpga_util(*cfg)
    if action == "-s":
      fu.synthesise()
    elif action == "-p":
      fu.prepare_to_run()
    elif action == "-u":
      fu.unprepare()
    else:
      raise ValueError(action)


if __name__ == "__main__":
  try:
    main()
  except:
    print("Usage:")
    print("python fpga_util.py -c <altered> <num-axons> <num-neurons> -m <model-name> [-m <model-name> ...] [ -c ...] <-s|-p|-u>")
    print("-s: synthesise")
    print("-p: prepare to run")
    print("-u: unprepare from running")
    raise
