import sys
import os

from common_util import set_spikehard_param
from model_util import model_util
from test_util import basic_test_util


def change_arch(old_params, new_num_axons, new_num_neurons, new_model_name=None):
  if new_model_name is None:
    new_model_name = os.path.basename(os.path.dirname(old_params.memory_filepath))

  new_params = old_params
  new_params = set_spikehard_param(new_params, "relax_packet_ordering", True)
  new_params = set_spikehard_param(new_params, "grid_dimension_x", 10)
  new_params = set_spikehard_param(new_params, "grid_dimension_y", 10)
  new_params = set_spikehard_param(new_params, "output_core_x_coordinate", 0)
  new_params = set_spikehard_param(new_params, "output_core_y_coordinate", 0)
  new_params = set_spikehard_param(new_params, "num_ticks_to_check", 30)
  new_params = set_spikehard_param(new_params, "num_axons", new_num_axons)
  new_params = set_spikehard_param(new_params, "num_neurons", new_num_neurons)

  mu, results = model_util.compress_model(old_params, new_params)
  results += mu.minimise_tick_delay()
  mu.to_unit_tests(model_name=new_model_name)
  print("all results:", results)
  return results


def optimise_tick_delay(old_params, num_ticks_to_check=30):
  new_params = set_spikehard_param(old_params, "num_ticks_to_check", num_ticks_to_check)
  mu = model_util(new_params, new_params)
  mu.init()
  results = mu.minimise_tick_delay()
  new_params = set_spikehard_param(old_params, "clock_cycles_per_tick", mu.test_params.clock_cycles_per_tick)
  mu.arch_params = mu.test_params = new_params
  mu.dump_params(new_params.memory_filepath)
  print(results)
  return results


def main():
  model_name = sys.argv[1]
  old_altered, old_num_axons, old_num_neurons = [int(arg) for arg in sys.argv[2:5]]
  assert old_altered in (0, 1), old_altered
  old_altered = bool(old_altered)
  old_params = basic_test_util.gen_test_params(model_name, old_altered, old_num_axons, old_num_neurons)
  del old_altered, old_num_axons, old_num_neurons
  if len(sys.argv) == 5:
    optimise_tick_delay(old_params)
  else:
    new_num_axons, new_num_neurons = [int(arg) for arg in sys.argv[5:]]
    results = change_arch(old_params, new_num_axons, new_num_neurons)
    with open(f"results_{model_name}.py", 'a') as f:
      f.write(str(results) + ",\n")


if __name__ == "__main__":
  try:
    main()
  except:
    print("Usage:")
    print(
      "python to_unit_tests.py <model-name> <old-altered> <old-num-axons> <old-num-neurons> [<new-num-axons> <new-num-neurons>]")
    print("If new architecture specified, restructures old model to new architecture, otherwise optimises tick delay in-place.")
    raise
