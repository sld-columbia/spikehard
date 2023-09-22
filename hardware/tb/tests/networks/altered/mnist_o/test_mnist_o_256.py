import unittest
import pytest
import logging
import sys
import os

# add '/hardware/util' to system path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))), "util"))
from test_util import basic_test_util, expose_markers_option_fixture  # noqa: E402

# add '/hardware/tb/tests/networks' to system path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from spikehard import spikehard  # noqa: E402

@pytest.mark.myhdl
@pytest.mark.altered
class test_mnist_o_256(unittest.TestCase):
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.DEBUG)

  @staticmethod
  def gen_test_params(**kwargs):
      return basic_test_util.gen_test_params(model_name = "mnist_o", altered = True, num_axons = 256, num_neurons = 256, **kwargs)

  def test(self):
    test_params = test_mnist_o_256.gen_test_params(dma_bus_width = 32, dma_frame_header_word_width = 32, router_buffer_depth = 4)
    spikehard.run_test(self, test_params)

if __name__ == '__main__':
  unittest.main()
