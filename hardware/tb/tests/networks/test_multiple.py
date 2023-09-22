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
from common_util import set_spikehard_param  # noqa: E402

@pytest.mark.myhdl
class test_multiple(unittest.TestCase):
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.DEBUG)

  def run_test(self, num_axons=256, num_neurons=256, grid_dims=None, **kwargs):
    all_test_params = []
    for model_name in ("vmm_o", "mnist_o"):
      all_test_params.append(basic_test_util.gen_test_params(model_name=model_name, altered=True,
                             num_axons=num_axons, num_neurons=num_neurons, **kwargs))

    if grid_dims is None:
      arch_params = None
    else:
      arch_params = all_test_params[0]
      arch_params = set_spikehard_param(arch_params, "num_outputs", num_axons)
      arch_params = set_spikehard_param(arch_params, "grid_dimension_x", grid_dims[0])
      arch_params = set_spikehard_param(arch_params, "grid_dimension_y", grid_dims[1])

    spikehard.run_test(self, all_test_params, arch_params)

  def test(self):
    grid_dims = [None]
    num_ticks_to_check = [6]
    dma_bus_width = [32]
    dma_frame_header_word_width = [32]

    basic_test_util.run_subtests(self,
                                 grid_dims=grid_dims,
                                 num_ticks_to_check=num_ticks_to_check,
                                 dma_bus_width=dma_bus_width,
                                 dma_frame_header_word_width=dma_frame_header_word_width)


if __name__ == '__main__':
  unittest.main()
