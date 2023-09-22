import os
import sys

from common_util import HARDWARE_DIR, set_spikehard_param, file_util
from model_util import model_util
from test_util import basic_test_util


class app_util():
  def __init__(self,
               max_dimension_x=512,
               max_dimension_y=512,
               grid_dimension_x=5,
               grid_dimension_y=5,
               output_core_x_coordinate=0,
               output_core_y_coordinate=0,
               num_axons=256,
               num_neurons=256,
               num_outputs=None,
               num_ticks_to_check=20,
               relax_packet_ordering=True,
               minimise_arch_dims=True,
               minimise_num_outputs=True):
    self.max_dimension_x = max_dimension_x
    self.max_dimension_y = max_dimension_y
    self.grid_dimension_x = grid_dimension_x
    self.grid_dimension_y = grid_dimension_y
    self.output_core_x_coordinate = output_core_x_coordinate
    self.output_core_y_coordinate = output_core_y_coordinate
    self.num_axons = num_axons
    self.num_neurons = num_neurons
    self.num_outputs = num_axons if num_outputs is None else num_outputs
    self.num_ticks_to_check = num_ticks_to_check
    self.relax_packet_ordering = relax_packet_ordering
    self.minimise_arch_dims = minimise_arch_dims
    self.minimise_num_outputs = minimise_num_outputs
    self.min_grid_dimension_x = 0
    self.min_grid_dimension_y = 0
    self.min_num_outputs = 0
    self.model_names = []
    model_util.clean_model_headers()

  def convert_to_arch_params(self, params):
    params = set_spikehard_param(params, "relax_packet_ordering", self.relax_packet_ordering)
    params = set_spikehard_param(params, "max_dimension_x", self.max_dimension_x)
    params = set_spikehard_param(params, "max_dimension_y", self.max_dimension_y)
    params = set_spikehard_param(params, "grid_dimension_x", self.grid_dimension_x)
    params = set_spikehard_param(params, "grid_dimension_y", self.grid_dimension_y)
    params = set_spikehard_param(params, "output_core_x_coordinate", self.output_core_x_coordinate)
    params = set_spikehard_param(params, "output_core_y_coordinate", self.output_core_y_coordinate)
    params = set_spikehard_param(params, "num_ticks_to_check", self.num_ticks_to_check)
    params = set_spikehard_param(params, "num_axons", self.num_axons)
    params = set_spikehard_param(params, "num_neurons", self.num_neurons)
    params = set_spikehard_param(params, "num_outputs", self.num_outputs)
    return params

  def add_model(self, model_name, test_params, homogeneous=True, minimise_tick_delay=False):
    assert model_name not in self.model_names, "model already exists"
    self.model_names.append(model_name)

    if homogeneous:
      new_params = self.convert_to_arch_params(test_params)
      mu, _ = model_util.compress_model(
        test_params, new_params, minimise_arch_dims=self.minimise_arch_dims, minimise_num_outputs=self.minimise_num_outputs)
    else:
      if not self.minimise_arch_dims:
        assert self.grid_dimension_x >= test_params.grid_dimension_x
        assert self.grid_dimension_y >= test_params.grid_dimension_y
      if not self.minimise_num_outputs:
        assert self.num_outputs >= test_params.num_outputs

      assert self.max_dimension_x == test_params.max_dimension_x
      assert self.max_dimension_y == test_params.max_dimension_y
      assert self.output_core_x_coordinate in (None, test_params.output_core_x_coordinate)
      assert self.output_core_y_coordinate in (None, test_params.output_core_y_coordinate)
      assert self.num_axons == test_params.num_axons
      assert self.num_neurons == test_params.num_neurons

      mu = model_util(test_params, test_params)
      mu.init()

    if self.output_core_x_coordinate is None:
      self.output_core_x_coordinate = test_params.output_core_x_coordinate
    if self.output_core_y_coordinate is None:
      self.output_core_y_coordinate = test_params.output_core_y_coordinate

    if self.minimise_arch_dims:
      self.min_grid_dimension_x = max(self.min_grid_dimension_x, mu.arch_params.grid_dimension_x)
      self.min_grid_dimension_y = max(self.min_grid_dimension_y, mu.arch_params.grid_dimension_y)
    if self.minimise_num_outputs:
      self.min_num_outputs = max(self.min_num_outputs, mu.arch_params.num_outputs)
    if minimise_tick_delay:
      mu.minimise_tick_delay()
    mu.to_header(model_name)

  @staticmethod
  def gen_single_model_app(model_name, test_params):
    au = app_util()

    arch_params = set_spikehard_param(test_params, "max_dimension_x",
                                      256) if test_params.num_axons == 2048 else test_params

    au.model_names.append(model_name)
    au.max_dimension_x = arch_params.max_dimension_x
    au.max_dimension_y = arch_params.max_dimension_y
    au.grid_dimension_x = arch_params.grid_dimension_x
    au.grid_dimension_y = arch_params.grid_dimension_y
    au.output_core_x_coordinate = arch_params.output_core_x_coordinate
    au.output_core_y_coordinate = arch_params.output_core_y_coordinate
    au.num_axons = arch_params.num_axons
    au.num_neurons = arch_params.num_neurons
    au.num_outputs = arch_params.num_outputs
    au.num_ticks_to_check = arch_params.num_ticks_to_check
    au.relax_packet_ordering = arch_params.relax_packet_ordering
    au.minimise_arch_dims = False
    au.minimise_num_outputs = False

    mu = model_util(arch_params, test_params)
    mu.init()
    mu.to_header(model_name)

    au.finalise()

  def finalise(self):
    self.grid_dimension_x = self.min_grid_dimension_x if self.minimise_arch_dims else self.grid_dimension_x
    self.grid_dimension_y = self.min_grid_dimension_y if self.minimise_arch_dims else self.grid_dimension_y
    self.num_outputs = self.min_num_outputs if self.minimise_num_outputs else self.num_outputs

    # update 'spikehard_architecture.h' & 'spikehard.v' to current architecture.

    v_fn = os.path.join(HARDWARE_DIR, "hw", "src", "impl", "spikehard.v")
    c_fn = os.path.join(HARDWARE_DIR, "sw", "spikehard_lib", "spikehard_architecture.h")

    def v_max_dimension_x(with_value=False):
      return "    parameter MAX_DIMENSION_X = " + ("{},".format(self.max_dimension_x) if with_value else "")

    def v_max_dimension_y(with_value=False):
      return "    parameter MAX_DIMENSION_Y = " + ("{},".format(self.max_dimension_y) if with_value else "")

    def v_grid_dimension_x(with_value=False):
      return "    parameter GRID_DIMENSION_X = " + ("{},".format(self.grid_dimension_x) if with_value else "")

    def v_grid_dimension_y(with_value=False):
      return "    parameter GRID_DIMENSION_Y = " + ("{},".format(self.grid_dimension_y) if with_value else "")

    def v_output_core_x_coordinate(with_value=False):
      return "    parameter OUTPUT_CORE_X_COORDINATE = " + ("{},".format(self.output_core_x_coordinate) if with_value else "")

    def v_output_core_y_coordinate(with_value=False):
      return "    parameter OUTPUT_CORE_Y_COORDINATE = " + ("{},".format(self.output_core_y_coordinate) if with_value else "")

    def v_num_outputs(with_value=False):
      return "    parameter NUM_OUTPUTS = " + ("{},".format(self.num_outputs) if with_value else "")

    def v_num_neurons(with_value=False):
      return "    parameter NUM_NEURONS = " + ("{},".format(self.num_neurons) if with_value else "")

    def v_num_axons(with_value=False):
      return "    parameter NUM_AXONS = " + ("{},".format(self.num_axons) if with_value else "")

    def c_max_dimension_x(with_value=False):
      return "#define MAX_DIMENSION_X " + ("{}".format(self.max_dimension_x) if with_value else "")

    def c_max_dimension_y(with_value=False):
      return "#define MAX_DIMENSION_Y " + ("{}".format(self.max_dimension_y) if with_value else "")

    def c_grid_dimension_x(with_value=False):
      return "#define GRID_DIMENSION_X " + ("{}".format(self.grid_dimension_x) if with_value else "")

    def c_grid_dimension_y(with_value=False):
      return "#define GRID_DIMENSION_Y " + ("{}".format(self.grid_dimension_y) if with_value else "")

    def c_output_core_x_coordinate(with_value=False):
      return "#define OUTPUT_CORE_X_COORDINATE " + ("{}".format(self.output_core_x_coordinate) if with_value else "")

    def c_output_core_y_coordinate(with_value=False):
      return "#define OUTPUT_CORE_Y_COORDINATE " + ("{}".format(self.output_core_y_coordinate) if with_value else "")

    def c_num_outputs(with_value=False):
      return "#define NUM_OUTPUTS " + ("{}".format(self.num_outputs) if with_value else "")

    def c_num_neurons(with_value=False):
      return "#define NUM_NEURONS " + ("{}".format(self.num_neurons) if with_value else "")

    def c_num_axons(with_value=False):
      return "#define NUM_AXONS " + ("{}".format(self.num_axons) if with_value else "")

    file_util.replace_line(v_fn, v_max_dimension_x(), v_max_dimension_x(True))
    file_util.replace_line(c_fn, c_max_dimension_x(), c_max_dimension_x(True))

    file_util.replace_line(v_fn, v_max_dimension_y(), v_max_dimension_y(True))
    file_util.replace_line(c_fn, c_max_dimension_y(), c_max_dimension_y(True))

    file_util.replace_line(v_fn, v_grid_dimension_x(), v_grid_dimension_x(True))
    file_util.replace_line(c_fn, c_grid_dimension_x(), c_grid_dimension_x(True))

    file_util.replace_line(v_fn, v_grid_dimension_y(), v_grid_dimension_y(True))
    file_util.replace_line(c_fn, c_grid_dimension_y(), c_grid_dimension_y(True))

    file_util.replace_line(v_fn, v_output_core_x_coordinate(), v_output_core_x_coordinate(True))
    file_util.replace_line(c_fn, c_output_core_x_coordinate(), c_output_core_x_coordinate(True))

    file_util.replace_line(v_fn, v_output_core_y_coordinate(), v_output_core_y_coordinate(True))
    file_util.replace_line(c_fn, c_output_core_y_coordinate(), c_output_core_y_coordinate(True))

    file_util.replace_line(v_fn, v_num_outputs(), v_num_outputs(True))
    file_util.replace_line(c_fn, c_num_outputs(), c_num_outputs(True))

    file_util.replace_line(v_fn, v_num_neurons(), v_num_neurons(True))
    file_util.replace_line(c_fn, c_num_neurons(), c_num_neurons(True))

    file_util.replace_line(v_fn, v_num_axons(), v_num_axons(True))
    file_util.replace_line(c_fn, c_num_axons(), c_num_axons(True))

    ######################################################################
    # ** BAREMETAL ** update 'spikehard.c' to run testbenches for all models. #
    ######################################################################

    baremetal_main_code = ""
    baremetal_main_code += '#include "../spikehard_lib/spikehard_manager.h"\n'
    baremetal_main_code += '#include "../spikehard_lib/test_bench.h"\n'
    for model_name in self.model_names:
      baremetal_main_code += '#include "../spikehard_model/{}.h"\n'.format(model_name)
    baremetal_main_code += '\n'
    baremetal_main_code += 'int main(int argc, char * argv[]) {\n'
    baremetal_main_code += '  return {};'.format(" || ".join(
      ["tb_run_single_model(&g_{}_test_bench, 0)".format(model_name) for model_name in self.model_names]))
    baremetal_main_code += '\n}\n'

    with open(os.path.join(HARDWARE_DIR, "sw", "baremetal", "spikehard.c"), 'w') as f:
      f.write(baremetal_main_code)

    ########################################################################
    # ** LINUX ** update 'spikehard.c' to run performance tests for all models. #
    ########################################################################

    linux_main_code = ""

    linux_main_code += '#include "spikehard_lib/spikehard_manager.h"\n'
    linux_main_code += '#include "spikehard_lib/test_bench.h"\n'
    linux_main_code += '#include "spikehard_lib/util.h"\n'
    for model_name in self.model_names:
      linux_main_code += '#include "spikehard_model/{}.h"\n'.format(model_name)
    
    linux_main_code += """
static int get_optional_iarg_(int argc, char** argv, char const* flag, const int default_val) {
  for (int i = 1; i < argc; ++i) {
    if (!strcmp(argv[i - 1], flag)) {
      return atoi(argv[i]);
    }
  }
  return default_val;
}

int main(int argc, char** argv) {
  const unsigned latency_num_samples = get_optional_iarg_(argc, argv, "-l", 1);
  const unsigned throughput_num_samples = get_optional_iarg_(argc, argv, "-t", 1);
  const unsigned invocation_overhead_num_samples = get_optional_iarg_(argc, argv, "-i", 0);
  const unsigned model_loading_overhead_num_samples = get_optional_iarg_(argc, argv, "-m", 0);
"""

    for model_name in self.model_names:
      batched = "mnist" in model_name.lower()
      linux_main_code += f'  spikehard_stats_t stats_{model_name};\n'
      linux_main_code += f'  stats_{model_name}.batched = {str(batched).lower()};\n'
      linux_main_code += f'  g_{model_name}_test_bench.clock_cycles_per_tick = get_optional_iarg_(argc, argv, "-c", g_{model_name}_test_bench.clock_cycles_per_tick);\n'
      linux_main_code += f'  if (su_measure_perf(&stats_{model_name}, &g_{model_name}_test_bench, latency_num_samples, throughput_num_samples, invocation_overhead_num_samples, model_loading_overhead_num_samples))'
      linux_main_code += ' { return 1; }\n'

    for model_name in self.model_names:
      linux_main_code += '  printf("[SW] stats for {} model:\\n");\n'.format(model_name)
      linux_main_code += '  su_print_stats(&stats_{});\n'.format(model_name)

    linux_main_code += '  printf("[SW][util] latencies ({}): [{}, {}, {}]\\n", {});\n'.format(
      ", ".join(self.model_names),
      ", ".join(["%f"] * len(self.model_names)),
      self.num_axons,
      self.num_neurons,
      ", ".join([f"(stats_{model_name}.invocation_overhead+stats_{model_name}.model_loading_overhead+stats_{model_name}.latency_excl_overhead)" for model_name in self.model_names]))

    linux_main_code += '  return 0;\n}\n'

    with open(os.path.join(HARDWARE_DIR, "sw", "linux", "app", "spikehard.c"), 'w') as f:
      f.write(linux_main_code)


def main():
  altered, num_axons, num_neurons = [int(arg) for arg in sys.argv[1:4]]
  assert altered in (0, 1), altered
  altered = bool(altered)
  model_names = sys.argv[4:]

  bau = app_util(num_axons=num_axons, num_neurons=num_neurons, minimise_arch_dims=True, minimise_num_outputs=True)
  for model_name in model_names:
    test_params = basic_test_util.gen_test_params(
      model_name, altered=altered, num_axons=num_axons, num_neurons=num_neurons)
    bau.add_model(model_name, test_params, homogeneous=False)
  bau.finalise()


if __name__ == "__main__":
  try:
    main()
  except:
    print("Usage:")
    print("python app_util.py <altered> <num-axons> <num-neurons> <model-name> [<model-name> ...]")
    raise
