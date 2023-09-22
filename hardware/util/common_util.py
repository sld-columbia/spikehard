from collections import namedtuple
import subprocess
import math
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HARDWARE_DIR = os.path.join(ROOT_DIR, "hardware")
IMPL_DIR = os.path.join(HARDWARE_DIR, "hw", "src", "impl")
TB_DIR = os.path.join(ROOT_DIR, "hardware", "tb")
PRECONFIGURED_SOCS_DIR = os.path.join(HARDWARE_DIR, "util", "preconfigured_socs")
SYNTHESISED_SOCS_DIR = os.path.join(HARDWARE_DIR, "util", "synthesised_socs")
ESP_SOCS_DIR = os.path.join(os.path.dirname(ROOT_DIR), "esp", "socs")
DEFAULT_SOC = "xilinx-vcu128-xcvu37p"


class file_util():
  @staticmethod
  def replace_line(fn, original_line, new_line, silent=False):
    try:
      subprocess.run("sed -i '/^{}/c\\{}' {}".format(original_line, new_line, fn), check=True, shell=True)
    except subprocess.CalledProcessError:
      if silent:
        return
      else:
        raise

  @staticmethod
  def peek_line(f):
    pos = f.tell()
    line = f.readline()
    f.seek(pos)
    return line


class math_util():
  @staticmethod
  def clog2(value):
    return int(math.ceil(math.log(value, 2)))


def create_spikehard_named_params_cls_():
  name = 'spikehard_params'
  keys = ['grid_dimension_x', 'grid_dimension_y',
          'output_core_x_coordinate', 'output_core_y_coordinate',
          'num_outputs', 'num_neurons', 'num_axons', 'num_ticks', 'num_weights',
          'num_reset_modes', 'potential_width', 'weight_width',
          'leak_width', 'threshold_width', 'max_dimension_x',
          'max_dimension_y', 'router_buffer_depth',
          'dma_bus_width', 'dma_frame_header_word_width',
          'clock_cycles_per_tick', 'memory_filepath',
          'num_ticks_to_check', 'tick_latency',
          'relax_packet_ordering']

  try:
    tuple_cls = namedtuple(name, ", ".join(keys), defaults=(None,) * len(keys))
  except:
    tuple_cls = namedtuple(name, ", ".join(keys))
    tuple_cls.__new__.__defaults__ = (None,) * len(keys)

  return tuple_cls


spikehard_named_params = create_spikehard_named_params_cls_()


def set_spikehard_param(params, key, value):
  params_dict = params._asdict()
  params_dict[key] = value
  return spikehard_named_params(**params_dict)
