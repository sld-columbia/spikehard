import sys
import os
import math
import functools

from spikehard import spikehard

# add '/hardware/util' to system path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
  os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "util"))
from common_util import math_util  # noqa: E402
from test_util import myhdl_util  # noqa: E402
from model_util import model_util  # noqa: E402


class dma_frame_manager():
  HEADER_LENGTH_IN_BITS = 128

  DMA_FRAME_TYPE_NOOP = 0
  DMA_FRAME_TYPE_NOOP_CONF = 1
  DMA_FRAME_TYPE_TERMINATE = 2
  DMA_FRAME_TYPE_IN_PACKETS = 3
  DMA_FRAME_TYPE_OUT_PACKETS = 4
  DMA_FRAME_TYPE_TICK = 5
  DMA_FRAME_TYPE_CORE_DATA = 6
  DMA_FRAME_TYPE_RESET = 7

  def __init__(self, testcase, input_ports, output_ports, arch_params, test_params=None) -> None:
    self.testcase = testcase
    self.input_ports = input_ports
    self.output_ports = output_ports
    self.arch_params = arch_params
    self.test_params = test_params

    self.logger = testcase.logger
    self.read_offset = 0
    self.write_offset = (2 ** 31) / (self.dma_bus_width >> 3)
    self.accelerator_terminated = False

  def __read_dma_frame_header(self, dma_frame_type, make_32bit_word=lambda word_idx: 0, update_read_offset=True):
    word_width = self.header_word_width
    read_length = self.header_length_in_beats

    metadata = int(dma_frame_type)

    def make_read_word(word_idx):
      if self.header_word_width == 64:
        value = make_32bit_word(2 * word_idx) if word_idx != 0 else metadata
        value |= make_32bit_word(2 * word_idx + 1) << 32
        return value
      elif self.header_word_width == 32:
        return make_32bit_word(word_idx) if word_idx != 0 else metadata

    yield from myhdl_util.service_read_request(self.testcase,
                                               self.input_ports, self.output_ports,
                                               self.read_offset, read_length,
                                               self.dma_bus_width, word_width,
                                               make_read_word,
                                               timeout=self.timeout)

    if update_read_offset:
      self.read_offset += read_length

  def noop(self):
    yield from self.__read_dma_frame_header(self.DMA_FRAME_TYPE_NOOP, update_read_offset=False)

  def configure_noop(self, amount):
    def make_32bit_word(word_idx):
      if word_idx == 1:
        return 0
      elif word_idx == 2:
        return amount & self.mask(32)
      elif word_idx == 3:
        return (amount >> 32) & self.mask(32)

    yield from self.__read_dma_frame_header(self.DMA_FRAME_TYPE_NOOP_CONF, make_32bit_word)

  def terminate(self):
    yield from self.__read_dma_frame_header(self.DMA_FRAME_TYPE_TERMINATE)

  def tick(self, amount=1, delay=None):
    assert amount > 0, "invalid tick amount"

    if delay is None:
      delay = self.arch_params.clock_cycles_per_tick

    def make_32bit_word(word_idx):
      if word_idx == 1:
        assert amount <= self.mask(15), "amount too large"
        return amount & self.mask(15)
      elif word_idx == 2:
        return delay & self.mask(32)
      elif word_idx == 3:
        return (delay >> 32) & self.mask(32)

    yield from self.__read_dma_frame_header(self.DMA_FRAME_TYPE_TICK, make_32bit_word)

  def in_packets_header(self, num_packets):
    payload_address = (self.read_offset + self.header_length_in_beats) * \
        (self.dma_bus_width >> 3)  # convert beat offset to byte offset

    def make_32bit_word(word_idx):
      if word_idx == 1:
        return num_packets
      elif word_idx == 2:
        return payload_address & self.mask(32)
      elif word_idx == 3:
        return (payload_address >> 32) & self.mask(32)

    yield from self.__read_dma_frame_header(self.DMA_FRAME_TYPE_IN_PACKETS, make_32bit_word)

  def in_packets_payload(self, packets):
    if len(packets) == 0:
      return

    word_width = self.in_packets_payload_word_width
    read_length = math.ceil(len(packets) * (word_width / self.dma_bus_width))

    def make_read_word(word_idx):
      if word_idx < len(packets):
        return packets[word_idx]
      else:
        return 0

    yield from myhdl_util.service_read_request(self.testcase,
                                               self.input_ports, self.output_ports,
                                               self.read_offset, read_length,
                                               self.dma_bus_width, word_width,
                                               make_read_word,
                                               timeout=self.timeout)

    self.read_offset += read_length

  def in_packets(self, packets):
    yield from self.in_packets_header(len(packets))
    yield from self.in_packets_payload(packets)

  def core_data_header(self, tc_path, csram_path, cur_x, cur_y):
    payload_address = (self.read_offset + self.header_length_in_beats) * \
        (self.dma_bus_width >> 3)  # convert beat offset to byte offset

    if cur_x == self.arch_params.output_core_x_coordinate and cur_y == self.arch_params.output_core_y_coordinate:
      core_idx = self.test_params.output_core_x_coordinate + \
        self.test_params.output_core_y_coordinate * self.arch_params.grid_dimension_x
    else:
      core_idx = cur_x + cur_y * self.arch_params.grid_dimension_x

    def make_32bit_word(word_idx):
      if word_idx == 1:
        return core_idx
      elif word_idx == 2:
        return payload_address & self.mask(32)
      elif word_idx == 3:
        return (payload_address >> 32) & self.mask(32)

    yield from self.__read_dma_frame_header(self.DMA_FRAME_TYPE_CORE_DATA, make_32bit_word)

  def core_data_payload(self, tc_path, csram_path, cur_x, cur_y):
    cd = model_util(self.arch_params, self.test_params).gen_core(tc_path, csram_path, cur_x, cur_y)
    tc_words = cd.tc_words
    csram_words = cd.csram_words

    words = tc_words + csram_words
    word_width = self.core_data_payload_word_width
    read_length = math.ceil(len(words) * (word_width / self.dma_bus_width))

    def make_read_word(word_idx):
      return words[word_idx]

    yield from myhdl_util.service_read_request(self.testcase,
                                               self.input_ports, self.output_ports,
                                               self.read_offset, read_length,
                                               self.dma_bus_width, word_width,
                                               make_read_word,
                                               timeout=self.timeout)

    self.read_offset += read_length

  def core_data(self, tc_path, csram_path, cur_x, cur_y):
    yield from self.core_data_header(tc_path, csram_path, cur_x, cur_y)
    yield from self.core_data_payload(tc_path, csram_path, cur_x, cur_y)

  def reset(self, reset_network=True, reset_model=True, reset_tick_idx=True):
    def make_32bit_word(word_idx):
      if word_idx == 1:
        return (int(reset_tick_idx) & 1) | ((int(reset_network) & 1) << 1) | ((int(reset_model) & 1) << 2)
      else:
        return 0

    yield from self.__read_dma_frame_header(self.DMA_FRAME_TYPE_RESET, make_32bit_word)

  def __out_packets_header_check_write_word(self, header_data, word_idx, value):
    if self.header_word_width == 64:
      if word_idx == 0:
        metadata = value & self.mask(32)
        header_data.num_packets = (value >> 32) & self.mask(16)
        header_data.tick_idx = ((value >> 32) >> 16) & self.mask(16)
        self.testcase.assertEqual(metadata, self.DMA_FRAME_TYPE_OUT_PACKETS)
      elif word_idx == 1:
        header_data.payload_address = value
    elif self.header_word_width == 32:
      if word_idx == 0:
        metadata = value
        self.testcase.assertEqual(metadata, self.DMA_FRAME_TYPE_OUT_PACKETS)
      elif word_idx == 1:
        header_data.num_packets = value & self.mask(16)
        header_data.tick_idx = (value >> 16) & self.mask(16)
      elif word_idx == 2:
        header_data.payload_address = value
      elif word_idx == 3:
        header_data.payload_address |= value << 32

  class __out_packets_header_data():
    def __init__(self):
      self.tick_idx = None
      self.num_packets = None
      self.payload_address = None

    def __str__(self):
      return "header_data(tick_idx = {}, num_packets = {}, payload_address = {})".format(self.tick_idx, self.num_packets, self.payload_address)

  def __out_packets_header(self, header_data):
    word_width = self.header_word_width
    write_length = self.header_length_in_beats

    check_write_word = functools.partial(self.__out_packets_header_check_write_word, header_data)

    yield from myhdl_util.service_write_request(self.testcase,
                                                self.input_ports, self.output_ports,
                                                self.write_offset, write_length,
                                                self.dma_bus_width, word_width,
                                                check_write_word,
                                                timeout=self.timeout)

    self.write_offset += write_length

  def __out_packets_payload(self, header_data, check_packet):
    self.logger.debug(header_data)

    if header_data.num_packets == 0:
      return

    word_width = self.out_packets_payload_word_width
    write_length = math.ceil(header_data.num_packets * (word_width / self.dma_bus_width))

    def check_write_word(word_idx, value):
      if word_idx < header_data.num_packets:
        check_packet(header_data.tick_idx, value)

    yield from myhdl_util.service_write_request(self.testcase,
                                                self.input_ports, self.output_ports,
                                                self.write_offset, write_length,
                                                self.dma_bus_width, word_width,
                                                check_write_word,
                                                timeout=self.timeout)

    self.write_offset += write_length

  def out_packets(self, check_packet):
    hd = self.__out_packets_header_data()
    yield from self.__out_packets_header(hd)
    yield from self.__out_packets_payload(hd, check_packet)

  def out_frame(self, valid_frame_types=[DMA_FRAME_TYPE_OUT_PACKETS, DMA_FRAME_TYPE_TERMINATE], check_packet=None):
    word_width = self.header_word_width
    write_length = self.header_length_in_beats
    frame_type = None
    hd = None

    def check_write_word(word_idx, value):
      nonlocal frame_type, hd

      if word_idx == 0:
        frame_type = value & self.mask(32)
        self.testcase.assertTrue((frame_type in valid_frame_types))

      if frame_type == self.DMA_FRAME_TYPE_OUT_PACKETS:
        if hd is None:
          hd = self.__out_packets_header_data()
        self.__out_packets_header_check_write_word(hd, word_idx, value)
      elif frame_type == self.DMA_FRAME_TYPE_TERMINATE:
        self.accelerator_terminated = True

    yield from myhdl_util.service_write_request(self.testcase,
                                                self.input_ports, self.output_ports,
                                                self.write_offset, write_length,
                                                self.dma_bus_width, word_width,
                                                check_write_word,
                                                timeout=self.timeout)

    self.write_offset += write_length

    if frame_type == self.DMA_FRAME_TYPE_OUT_PACKETS:
      yield from self.__out_packets_payload(hd, check_packet)

  @property
  def dma_bus_width(self) -> int:
    return self.arch_params.dma_bus_width

  @property
  def timeout(self) -> int:
    return spikehard.timeout(self.arch_params)

  @property
  def header_word_width(self) -> int:
    return self.arch_params.dma_frame_header_word_width

  @property
  def header_length_in_beats(self) -> int:
    assert (self.HEADER_LENGTH_IN_BITS % self.dma_bus_width) == 0, self.dma_bus_width
    return self.HEADER_LENGTH_IN_BITS // self.dma_bus_width

  @staticmethod
  def mask(num_bits) -> int:
    return (2 ** num_bits) - 1

  @staticmethod
  def ceil_word_width(word_width):
    if word_width <= 8:
      return 8
    elif word_width <= 16:
      return 16
    elif word_width <= 32:
      return 32
    elif word_width <= 64:
      return 64
    else:
      raise Exception("word width is too large")

  @property
  def in_packets_payload_word_width(self) -> int:
    clog2 = math_util.clog2
    p = self.arch_params

    dx_msb = clog2(p.max_dimension_x) + clog2(p.max_dimension_y) + clog2(p.num_axons) + clog2(p.num_ticks) - 1
    dx_lsb = clog2(p.max_dimension_y) + clog2(p.num_axons) + clog2(p.num_ticks)
    dy_msb = clog2(p.max_dimension_y) + clog2(p.num_axons) + clog2(p.num_ticks) - 1
    dy_lsb = clog2(p.num_axons) + clog2(p.num_ticks)
    dx_width = dx_msb - dx_lsb + 1
    dy_width = dy_msb - dy_lsb + 1
    packet_width = dx_width + dy_width + clog2(p.num_axons) + clog2(p.num_ticks)

    return self.ceil_word_width(packet_width)

  @property
  def out_packets_payload_word_width(self) -> int:
    out_packet_width = math_util.clog2(self.arch_params.num_outputs)
    return self.ceil_word_width(out_packet_width)

  @property
  def core_data_payload_word_width(self) -> int:
    return 64

  @property
  def csram_read_width(self) -> int:
    clog2 = math_util.clog2
    p = self.arch_params

    dx_msb = clog2(p.max_dimension_x) + clog2(p.max_dimension_y) + clog2(p.num_axons) + clog2(p.num_ticks) - 1
    dx_lsb = clog2(p.max_dimension_y) + clog2(p.num_axons) + clog2(p.num_ticks)
    dy_msb = clog2(p.max_dimension_y) + clog2(p.num_axons) + clog2(p.num_ticks) - 1
    dy_lsb = clog2(p.num_axons) + clog2(p.num_ticks)
    dx_width = dx_msb - dx_lsb + 1
    dy_width = dy_msb - dy_lsb + 1

    return p.num_axons + p.potential_width + p.potential_width + p.weight_width * p.num_weights + p.leak_width + p.threshold_width + p.threshold_width + clog2(p.num_reset_modes) + dx_width + dy_width + clog2(p.num_axons) + clog2(p.num_ticks)
