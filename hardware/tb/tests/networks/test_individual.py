import unittest
import pytest
import logging
import sys
import os

from spikehard import spikehard

# add '/hardware/util' to system path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
  os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "util"))
from test_util import basic_test_util, expose_markers_option_fixture  # noqa: E402
from common_util import spikehard_named_params  # noqa: E402


@pytest.mark.myhdl
class test_vmm(unittest.TestCase):
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.DEBUG)

  def run_test(self, model, independent_arch, num_ticks_to_check, dma_bus_width, dma_frame_header_word_width):
    model_name, altered, num_axons, num_neurons = model

    test_params = basic_test_util.gen_test_params(model_name=model_name,
                                                  altered=altered,
                                                  num_axons=num_axons,
                                                  num_neurons=num_neurons,
                                                  num_ticks_to_check=num_ticks_to_check,
                                                  dma_bus_width=dma_bus_width,
                                                  dma_frame_header_word_width=dma_frame_header_word_width)

    arch_params = None
    if independent_arch:
      arch_params = spikehard_named_params(test_params.grid_dimension_x + 1, test_params.grid_dimension_y,
                                           test_params.output_core_x_coordinate, test_params.output_core_y_coordinate,
                                           test_params.num_outputs * 2, test_params.num_neurons * 2, test_params.num_axons * 2, test_params.num_ticks * 2,
                                           test_params.num_weights * 2, test_params.num_reset_modes * 2, test_params.potential_width + 2,
                                           test_params.weight_width + 2, test_params.leak_width + 2, test_params.threshold_width + 2,
                                           test_params.max_dimension_x * 2, test_params.max_dimension_y * 2,
                                           test_params.router_buffer_depth * 2,
                                           dma_bus_width, dma_frame_header_word_width,
                                           clock_cycles_per_tick=test_params.clock_cycles_per_tick * 4)

    spikehard.run_test(self, test_params, arch_params)

  def test(self):
    mnist_unaltered = ("mnist_o", False, 256, 256)
    mnist_altered = ("mnist_o", True, 256, 256)
    vmm_unaltered = ("vmm_o", False, 64, 64)
    vmm_altered = ("vmm_o", True, 256, 256)

    model = [mnist_unaltered, mnist_altered, vmm_unaltered, vmm_altered]
    independent_arch = [False]
    num_ticks_to_check = [None]
    dma_bus_width = [32, 64]
    dma_frame_header_word_width = [32, 64]

    basic_test_util.run_subtests(self,
                                 model=model,
                                 independent_arch=independent_arch,
                                 num_ticks_to_check=num_ticks_to_check,
                                 dma_bus_width=dma_bus_width,
                                 dma_frame_header_word_width=dma_frame_header_word_width)


if __name__ == '__main__':
  unittest.main()
