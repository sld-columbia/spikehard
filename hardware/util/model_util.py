import sys
import os
import math
import copy
import shutil
import json
import unittest
import logging
import pathlib

import numpy as np
from bitstring import BitArray
from ortools.linear_solver import pywraplp

from common_util import math_util, HARDWARE_DIR, TB_DIR, set_spikehard_param
from test_util import basic_test_util


class model_util():
  class core_data():
    def __init__(self, x, y, tc_words, csram_words):
      self.x = x
      self.y = y
      self.tc_words = tc_words
      self.csram_words = csram_words
      self.used_axons = None
      self.used_neurons = None
      self.unused_axons = None
      self.unused_neurons = None
      self.used_axon_to_neurons = None
      self.used_neuron_to_axons = None
      self.minimal_connected_components = None

    @property
    def pos(self):
      return (self.x, self.y)

  def __init__(self, arch_params, test_params, cores=None, input_packets=None, output_packets=None, num_input_packets=None, num_output_packets=None) -> None:
    self.arch_params = arch_params
    self.test_params = test_params
    self.cores = cores
    self.input_packets = input_packets
    self.output_packets = output_packets
    self.num_input_packets = num_input_packets
    self.num_output_packets = num_output_packets

  @staticmethod
  def compress_model(original_params, new_params=None, minimise_arch_dims: bool = True, minimise_num_outputs: bool = True) -> 'model_util':
    new_params = (original_params if new_params is None else new_params)
    new_params = set_spikehard_param(new_params, "memory_filepath", None)

    print("changing number of axons per core from {} to {}".format(original_params.num_axons, new_params.num_axons))
    print("changing number of neurons per core from {} to {}".format(
      original_params.num_neurons, new_params.num_neurons))

    mu = model_util(original_params, original_params)
    mu.init()
    results = mu.pack_cores(new_params=new_params, minimise_arch_dims=minimise_arch_dims,
                            minimise_num_outputs=minimise_num_outputs)

    return mu, results

  def output_packet_width(self, params=None) -> int:
    num_outputs = (self.arch_params if params is None else params).num_outputs
    num_outputs = round(2 ** math.ceil(math.log(num_outputs, 2)))
    return math_util.clog2(num_outputs)

  def dx_width(self, params=None) -> int:
    return math_util.clog2((self.arch_params if params is None else params).max_dimension_x)

  def dy_width(self, params=None) -> int:
    return math_util.clog2((self.arch_params if params is None else params).max_dimension_y)

  def tick_width(self, params=None) -> int:
    return math_util.clog2((self.arch_params if params is None else params).num_ticks)

  def dst_axon_width(self, params=None) -> int:
    return math_util.clog2((self.arch_params if params is None else params).num_axons)

  def packet_width(self, params=None) -> int:
    return self.dx_width(params) + self.dy_width(params) + self.dst_axon_width(params) + self.tick_width(params)

  def csram_read_width(self, params=None) -> int:
    clog2 = math_util.clog2
    p = (self.arch_params if params is None else params)
    return p.num_axons + p.potential_width + p.potential_width + p.weight_width * p.num_weights + p.leak_width + p.threshold_width + p.threshold_width + clog2(p.num_reset_modes) + self.packet_width(p)

  def unused_neuron_bit_str(self, params=None) -> str:
    p = (self.arch_params if params is None else params)
    return BitArray(uint=(1 << (self.csram_read_width(p) - (p.num_axons + 2 * p.potential_width + p.weight_width * p.num_weights + p.leak_width + p.threshold_width))),
                    length=self.csram_read_width(p)).bin

  def unused_axon_bit_str(self, params=None) -> str:
    p = (self.arch_params if params is None else params)
    return "".zfill(math_util.clog2(p.num_weights))

  def no_input_axons_bit_str_prefix(self, params=None) -> str:
    p = (self.arch_params if params is None else params)
    return "".zfill(p.num_axons)

  @property
  def core_data_payload_word_width(self) -> int:
    return 64

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
    return self.ceil_word_width(self.packet_width())

  def gen_core(self, tc_file, csram_file, cur_x, cur_y):
    def get_params(elem_width, num_elems):
      elem_padded_width = (1 << math_util.clog2(elem_width))
      num_words = ((((elem_padded_width * num_elems) - 1) | (self.core_data_payload_word_width - 1)) +
                   1) // self.core_data_payload_word_width
      return (elem_padded_width - elem_width, num_words)

    tc_elem_width = math_util.clog2(self.arch_params.num_weights)
    csram_elem_width = self.csram_read_width()

    tc_elem_padding, tc_num_words = get_params(tc_elem_width, self.arch_params.num_axons)
    csram_elem_padding, csram_num_words = get_params(csram_elem_width, self.arch_params.num_neurons)

    def reshape_csram_entry(bit_str):
      value = 0
      for idx, bit in enumerate(bit_str[self.test_params.num_axons:][::-1]):
        value |= int(bit) << idx

      start_idx = 0

      def read_field(length):
        nonlocal start_idx
        field_value = (value >> start_idx) & ((2 ** length) - 1)
        start_idx += length

        if field_value < 0:
          return BitArray(int=field_value, length=length).uint
        else:
          return field_value

      def adjust_core_offset(dx, dy):
        if dx == 0 and dy == 0:
          return (dx, dy)

        old_dx = BitArray(uint=dx, length=self.dx_width(self.test_params)).int
        old_dy = BitArray(uint=dy, length=self.dy_width(self.test_params)).int
        dst_x = old_dx + cur_x
        dst_y = old_dy + cur_y

        if cur_x == self.arch_params.output_core_x_coordinate and cur_y == self.arch_params.output_core_y_coordinate:
          # this core has been moved
          if dst_x == self.test_params.output_core_x_coordinate and dst_y == self.test_params.output_core_y_coordinate:
            # trying to send to output core
            new_dx = self.arch_params.output_core_x_coordinate - self.test_params.output_core_x_coordinate
            new_dy = self.arch_params.output_core_y_coordinate - self.test_params.output_core_y_coordinate
          else:
            # trying to send to an unmoved core
            new_dx = dst_x - self.test_params.output_core_x_coordinate
            new_dy = dst_y - self.test_params.output_core_y_coordinate
        elif dst_x == self.test_params.output_core_x_coordinate and dst_y == self.test_params.output_core_y_coordinate:
          # trying to send to output core from an unmoved core
          new_dx = self.arch_params.output_core_x_coordinate - cur_x
          new_dy = self.arch_params.output_core_y_coordinate - cur_y
        elif dst_x == self.arch_params.output_core_x_coordinate and dst_y == self.arch_params.output_core_y_coordinate:
          # trying to send to moved core from an unmoved core
          new_dx = self.test_params.output_core_x_coordinate - cur_x
          new_dy = self.test_params.output_core_y_coordinate - cur_y
        else:
          # trying to send to an unmoved core from an unmoved core
          new_dx = old_dx
          new_dy = old_dy

        assert cur_x != self.test_params.output_core_x_coordinate or cur_y != self.test_params.output_core_y_coordinate, (
          cur_x, cur_y, self.test_params, self.arch_params)

        return (new_dx, new_dy)

      destination_tick = read_field(self.tick_width(self.test_params))
      destination_axon = read_field(self.dst_axon_width(self.test_params))
      destination_core_offset_y = read_field(self.dy_width(self.test_params))
      destination_core_offset_x = read_field(self.dx_width(self.test_params))
      destination_core_offset = adjust_core_offset(destination_core_offset_x, destination_core_offset_y)
      reset_mode = read_field(self.test_params.num_reset_modes.bit_length() - 1)
      negative_threshold = read_field(self.test_params.threshold_width)
      positive_threshold = read_field(self.test_params.threshold_width)
      leak = read_field(self.test_params.leak_width)
      weights = [0 for _ in range(self.test_params.num_weights)]
      for i in range(self.test_params.num_weights):
        weights[self.test_params.num_weights - 1 - i] = read_field(self.test_params.weight_width)
      reset_potential = read_field(self.test_params.potential_width)
      current_potential = read_field(self.test_params.potential_width)
      assert start_idx == (len(bit_str) - self.test_params.num_axons)

      #######################
      # RECREATE BIT STRING #
      #######################

      weights = weights + [0] * (self.arch_params.num_weights - self.test_params.num_weights)

      def val_to_string(value, key, signed=False):
        if key.endswith("width"):
          old_length = getattr(self.test_params, key)
          new_length = getattr(self.arch_params, key)
        else:
          old_length = math_util.clog2(getattr(self.test_params, key))
          new_length = math_util.clog2(getattr(self.arch_params, key))

        if signed and (value & (1 << (old_length - 1))):
          if value < 0:
            return BitArray(int=value, length=new_length).bin

          for i in range(old_length, new_length):
            value |= (1 << i)

        return BitArray(uint=value, length=new_length).bin

      new_bit_str = bit_str[:self.test_params.num_axons].zfill(self.arch_params.num_axons) + "".join([
          val_to_string(current_potential, 'potential_width', signed=True),
          val_to_string(reset_potential, 'potential_width', signed=True),
          "".join([val_to_string(weight, 'weight_width', signed=True) for weight in weights]),
          val_to_string(leak, 'leak_width', signed=True),
          val_to_string(positive_threshold, 'threshold_width', signed=True),
          val_to_string(negative_threshold, 'threshold_width', signed=True),
          val_to_string(reset_mode, 'num_reset_modes'),
          val_to_string(destination_core_offset[0], 'max_dimension_x', signed=True),
          val_to_string(destination_core_offset[1], 'max_dimension_y', signed=True),
          val_to_string(destination_axon, 'num_axons'),
          val_to_string(destination_tick, 'num_ticks')
      ])

      same = True
      for key in self.arch_params._fields:
        if getattr(self.test_params, key) != getattr(self.arch_params, key):
          same = False
          break
      if same:
        assert bit_str == new_bit_str

      return new_bit_str

    def read_csram_mem_file():
      elem_idx = 0

      def csram_process_line(line):
        nonlocal elem_idx

        is_comment = False
        for char in line:
          if char not in ('0', '1') and not char.isspace():
            is_comment = True
            break
        if is_comment:
          return

        bit_str = ""
        for char in line:
          if char in ('0', '1'):
            bit_str += char

        elem_idx += 1
        bit_str = reshape_csram_entry(bit_str)
        yield bit_str

      if isinstance(csram_file, str):
        with open(csram_file, 'r') as file:
          for line in file:
            yield from csram_process_line(line)
      else:
        for line in csram_file:
          yield from csram_process_line(line)

      assert elem_idx == self.test_params.num_neurons

      # all zeros apart from positive_threshold
      bit_str = self.unused_neuron_bit_str()
      for _ in range(self.arch_params.num_neurons - self.test_params.num_neurons):
        yield bit_str

    def read_tc_mem_file():
      elem_idx = 0

      def tc_process_line(line):
        nonlocal elem_idx

        is_comment = False
        for char in line:
          if char not in ('0', '1') and not char.isspace():
            is_comment = True
            break
        if is_comment:
          return

        bit_str = ""
        for char in line:
          if char in ('0', '1'):
            bit_str += char

        elem_idx += 1
        bit_str = bit_str.zfill(tc_elem_width)
        yield bit_str

      if isinstance(tc_file, str):
        with open(tc_file, 'r') as file:
          for line in file:
            yield from tc_process_line(line)
      else:
        for line in tc_file:
          yield from tc_process_line(line)

      assert elem_idx == self.test_params.num_axons

      bit_str = self.unused_axon_bit_str()
      for _ in range(self.arch_params.num_neurons - self.test_params.num_neurons):
        yield bit_str

    def read_mem_file(reader, num_words, elem_width, elem_padding):
      bit_idx = 0
      words = [0 for _ in range(num_words)]
      for elem in reader():
        assert len(elem) == elem_width
        for char in elem[::-1]:
          assert char in ('0', '1')
          words[bit_idx //
                self.core_data_payload_word_width] |= int(char) << (bit_idx % self.core_data_payload_word_width)
          bit_idx += 1
        bit_idx += elem_padding
      return words

    tc_words = read_mem_file(read_tc_mem_file, tc_num_words, tc_elem_width, tc_elem_padding)
    csram_words = read_mem_file(read_csram_mem_file, csram_num_words, csram_elem_width, csram_elem_padding)

    if cur_x == self.arch_params.output_core_x_coordinate and cur_y == self.arch_params.output_core_y_coordinate:
      cur_x = self.test_params.output_core_x_coordinate
      cur_y = self.test_params.output_core_y_coordinate

    cd = model_util.core_data(cur_x, cur_y, tc_words, csram_words)
    self.update_core_usage_metadata(cd)
    return cd

  def parse_input_packets(self, old_packets=None):
    def adjust_core_offset(dx, dy):
      if self.test_params.output_core_x_coordinate == self.arch_params.output_core_x_coordinate and self.test_params.output_core_y_coordinate == self.arch_params.output_core_y_coordinate:
        return (dx, dy)

      if dx == self.test_params.output_core_x_coordinate and dy == self.test_params.output_core_y_coordinate:
        return (self.arch_params.output_core_x_coordinate, self.arch_params.output_core_y_coordinate)
      elif dx == self.arch_params.output_core_x_coordinate and dy == self.arch_params.output_core_y_coordinate:
        return (self.test_params.output_core_x_coordinate, self.test_params.output_core_y_coordinate)
      else:
        return (dx, dy)

    def update_packet(packet):
      start_idx = 0

      def read_field(length):
        nonlocal start_idx
        field_value = (packet >> start_idx) & ((2 ** length) - 1)
        start_idx += length

        if field_value < 0:
          return BitArray(int=field_value, length=length).uint
        else:
          return field_value

      destination_tick = read_field(self.tick_width(self.test_params))
      destination_axon = read_field(self.dst_axon_width(self.test_params))
      destination_core_offset_y = read_field(self.dy_width(self.test_params))
      destination_core_offset_x = read_field(self.dx_width(self.test_params))
      destination_core_offset = adjust_core_offset(destination_core_offset_x, destination_core_offset_y)
      destination_core_offset_x = BitArray(int=destination_core_offset[0], length=self.dx_width()).uint
      destination_core_offset_y = BitArray(int=destination_core_offset[1], length=self.dy_width()).uint

      width = 0
      new_packet = 0

      def add_field(v, l):
        nonlocal width, new_packet
        new_packet |= (v << width)
        width += l

      add_field(destination_tick, self.tick_width())
      add_field(destination_axon, self.dst_axon_width())
      add_field(destination_core_offset_y, self.dy_width())
      add_field(destination_core_offset_x, self.dx_width())
      new_packet |= ((packet >> width) << width)
      return new_packet

    packets = []
    if old_packets is None:
      with open(basic_test_util.input_filepath(self.test_params), 'r') as file:
        for line in file:
          if line.rstrip() == '':
            break
          packet = BitArray(bin=line.rstrip()).uint
          packets.append(update_packet(packet))
    else:
      for packet in old_packets:
        packets.append(update_packet(packet))
    return packets

  def update_input_packets(self, src_cd, src_axons, dst_cd, dst_axons, dst_model):
    def update_packet(packet):
      start_idx = 0

      def read_field(length):
        nonlocal start_idx
        field_value = (packet >> start_idx) & ((2 ** length) - 1)
        start_idx += length

        if field_value < 0:
          return BitArray(int=field_value, length=length).uint
        else:
          return field_value

      tick = read_field(self.tick_width())
      axon = read_field(self.dst_axon_width())
      dy = read_field(self.dy_width())
      dx = read_field(self.dx_width())

      if dx != src_cd.x or dy != src_cd.y or axon not in src_axons:
        return None

      axon = dst_axons[src_axons.index(axon)]
      dx = BitArray(int=dst_cd.x, length=dst_model.dx_width()).uint
      dy = BitArray(int=dst_cd.y, length=dst_model.dy_width()).uint

      width = 0
      new_packet = 0

      def add_field(v, l):
        nonlocal width, new_packet
        new_packet |= (v << width)
        width += l

      add_field(tick, dst_model.tick_width())
      add_field(axon, dst_model.dst_axon_width())
      add_field(dy, dst_model.dy_width())
      add_field(dx, dst_model.dx_width())
      assert width == dst_model.packet_width()
      return new_packet

    for i, packet in enumerate(self.input_packets):
      new_packet = update_packet(packet)
      if new_packet is not None:
        dst_model.input_packets[i] = new_packet

  def parse_output_packets(self, old_packets=None):
    if old_packets is None:
      packets = []
      with open(basic_test_util.correct_filepath(self.test_params), 'r') as file:
        for line in file:
          if line.rstrip() == '':
            break
          packet = BitArray(bin=line.rstrip()).uint
          assert packet < self.test_params.num_outputs
          packets.append(packet)
    else:
      packets = list(old_packets)
      for packet in packets:
        assert packet < self.arch_params.num_outputs

    return packets

  def parse_num_input_packets(self, old_values=None):
    if old_values is not None:
      return old_values

    values = []
    with open(basic_test_util.num_inputs_filepath(self.test_params), 'r') as file:
      for line in file:
        if line.rstrip() == '':
          break
        values.append(int(line.rstrip()))

    return values

  def parse_num_output_packets(self, old_values=None):
    if old_values is not None:
      return old_values

    values = []
    with open(basic_test_util.num_outputs_filepath(self.test_params), 'r') as file:
      for line in file:
        if line.rstrip() == '':
          break
        values.append(int(line.rstrip()))

    return values

  def init(self):
    output_core = self.test_params.output_core_x_coordinate + \
      self.test_params.output_core_y_coordinate * self.test_params.grid_dimension_x

    self.cores = []
    for y in range(self.test_params.grid_dimension_y):
      for x in range(self.test_params.grid_dimension_x):
        core_idx = x + y * self.test_params.grid_dimension_x
        if core_idx == output_core:
          continue

        core_idx = str(core_idx).zfill(
          len(str(self.test_params.grid_dimension_x * self.test_params.grid_dimension_y - 1)))

        def gen_path(s):
          return os.path.join(self.test_params.memory_filepath, "{}_{}.mem".format(s, core_idx))

        tc_path = gen_path("tc")
        csram_path = gen_path("csram")

        if not os.path.exists(tc_path) or not os.path.exists(csram_path):
          continue

        self.cores.append(self.gen_core(tc_path, csram_path, x, y))

    self.input_packets = self.parse_input_packets()
    self.output_packets = self.parse_output_packets()
    self.num_input_packets = self.parse_num_input_packets()
    self.num_output_packets = self.parse_num_output_packets()

  def update(self):
    for i in range(len(self.cores)):
      tc_lines, csram_lines = self.core_data_words_to_mem(self.cores[i], self.test_params)
      self.cores[i] = self.gen_core(tc_lines, csram_lines, self.cores[i].x, self.cores[i].y)

    self.input_packets = self.parse_input_packets(self.input_packets)
    self.output_packets = self.parse_output_packets(self.output_packets)
    self.num_input_packets = self.parse_num_input_packets(self.num_input_packets)
    self.num_output_packets = self.parse_num_output_packets(self.num_output_packets)

  def empty_core(self, x, y):
    def get_params(elem_width, num_elems):
      elem_padded_width = (1 << math_util.clog2(elem_width))
      num_words = ((((elem_padded_width * num_elems) - 1) | (self.core_data_payload_word_width - 1)) +
                   1) // self.core_data_payload_word_width
      return (elem_padded_width - elem_width, num_words)

    tc_elem_width = math_util.clog2(self.arch_params.num_weights)
    csram_elem_width = self.csram_read_width()

    tc_elem_padding, tc_num_words = get_params(tc_elem_width, self.arch_params.num_axons)
    csram_elem_padding, csram_num_words = get_params(csram_elem_width, self.arch_params.num_neurons)

    def read_csram_mem_file():
      # all zeros apart from positive_threshold
      bit_str = self.unused_neuron_bit_str()
      for _ in range(self.arch_params.num_neurons):
        yield bit_str

    def read_tc_mem_file():
      bit_str = self.unused_axon_bit_str()
      for _ in range(self.arch_params.num_axons):
        yield bit_str

    def read_mem_file(reader, num_words, elem_width, elem_padding):
      bit_idx = 0
      words = [0 for _ in range(num_words)]
      for elem in reader():
        assert len(elem) == elem_width
        for char in elem[::-1]:
          assert char in ('0', '1')
          words[bit_idx //
                self.core_data_payload_word_width] |= int(char) << (bit_idx % self.core_data_payload_word_width)
          bit_idx += 1
        bit_idx += elem_padding
      return words

    tc_words = read_mem_file(read_tc_mem_file, tc_num_words, tc_elem_width, tc_elem_padding)
    csram_words = read_mem_file(read_csram_mem_file, csram_num_words, csram_elem_width, csram_elem_padding)

    cd = model_util.core_data(x, y, tc_words, csram_words)
    self.update_core_usage_metadata(cd)
    return cd

  def core_data_words_to_mem(self, cd, params=None, verify_correctness=True):
    p = (self.arch_params if params is None else params)

    tc_lines = []
    csram_lines = []

    def get_params(elem_width, num_elems):
      elem_padded_width = (1 << math_util.clog2(elem_width))
      return elem_padded_width - elem_width

    tc_elem_width = math_util.clog2(p.num_weights)
    csram_elem_width = self.csram_read_width(p)

    tc_elem_padding = get_params(tc_elem_width, p.num_axons)
    csram_elem_padding = get_params(csram_elem_width, p.num_neurons)

    tc_elem_value = 0
    for i in range((tc_elem_width + tc_elem_padding) * p.num_axons):
      tc_elem_value |= ((cd.tc_words[i // self.core_data_payload_word_width] >> (i %
                        self.core_data_payload_word_width)) & 1) << (i % (tc_elem_width + tc_elem_padding))
      if (i % (tc_elem_width + tc_elem_padding)) == (tc_elem_width + tc_elem_padding - 1):
        tc_lines.append(BitArray(uint=tc_elem_value,
                                 length=tc_elem_width).bin)
        tc_elem_value = 0
    assert len(tc_lines) == p.num_axons

    csram_elem_value = 0
    for i in range((csram_elem_width + csram_elem_padding) * p.num_neurons):
      csram_elem_value |= ((cd.csram_words[i // self.core_data_payload_word_width] >> (i %
                           self.core_data_payload_word_width)) & 1) << (i % (csram_elem_width + csram_elem_padding))
      if (i % (csram_elem_width + csram_elem_padding)) == (csram_elem_width + csram_elem_padding - 1):
        csram_lines.append(BitArray(uint=csram_elem_value,
                                    length=csram_elem_width).bin)
        csram_elem_value = 0
    assert len(csram_lines) == p.num_neurons

    if verify_correctness:
      new_cd = model_util(p, p).gen_core(tc_lines, csram_lines, cd.x, cd.y)
      assert new_cd.tc_words == cd.tc_words
      assert new_cd.csram_words == cd.csram_words

    return tc_lines, csram_lines

  def update_core_usage_metadata(self, cd):
    tc_lines, csram_lines = self.core_data_words_to_mem(cd, verify_correctness=False)

    used_axons = []
    used_neurons = [n for n in range(self.arch_params.num_neurons)]
    unused_axons = [a for a in range(self.arch_params.num_axons)]
    unused_neurons = []
    used_axon_to_neurons = {}
    used_neuron_to_axons = {}
    minimal_connected_components = []

    no_input_axons = self.no_input_axons_bit_str_prefix()
    for n in range(self.arch_params.num_neurons):
      if csram_lines[n].startswith(no_input_axons):
        used_neurons.remove(n)
        unused_neurons.append(n)
      else:
        for a in range(self.arch_params.num_axons):
          bit = csram_lines[n][self.arch_params.num_axons - a - 1]
          if bit == '1':
            if a in unused_axons:
              unused_axons.remove(a)
              used_axons.append(a)

            if a in used_axon_to_neurons:
              used_axon_to_neurons[a].append(n)
            else:
              used_axon_to_neurons[a] = [n]

            if n in used_neuron_to_axons:
              used_neuron_to_axons[n].append(a)
            else:
              used_neuron_to_axons[n] = [a]
          elif bit != '0':
            raise ValueError("expected binary string")

    axons_to_process = list(used_axons)
    while len(axons_to_process) > 0:
      a1 = axons_to_process[-1]
      axons_to_add = [a1]
      connected_axons = []
      connected_neurons = []
      while len(axons_to_add) > 0:
        a2 = axons_to_add.pop()
        connected_axons.append(a2)
        axons_to_process.remove(a2)
        for n in used_axon_to_neurons[a2]:
          if n not in connected_neurons:
            connected_neurons.append(n)
            for a3 in used_neuron_to_axons[n]:
              if a3 not in axons_to_add and a3 not in connected_axons:
                axons_to_add.append(a3)
      connected_axons.sort()
      connected_neurons.sort()
      minimal_connected_components.append((connected_axons, connected_neurons))

    used_axons.sort()
    used_neurons.sort()
    unused_axons.sort()
    unused_neurons.sort()

    cd.used_axons = used_axons
    cd.used_neurons = used_neurons
    cd.unused_axons = unused_axons
    cd.unused_neurons = unused_neurons
    cd.used_axon_to_neurons = used_axon_to_neurons
    cd.used_neuron_to_axons = used_neuron_to_axons
    cd.minimal_connected_components = minimal_connected_components

  def from_csram_line_get_dst_axon(self, line, params=None):
    p = (self.arch_params if params is None else params)
    rev_line = line.rstrip()[::-1]
    base_offset = self.tick_width(p)
    return BitArray(bin=rev_line[base_offset:base_offset + self.dst_axon_width(p)][::-1]).uint

  def from_csram_line_get_dst_core(self, line, cd, params=None):
    p = (self.arch_params if params is None else params)
    rev_line = line.rstrip()[::-1]
    base_offset = self.tick_width(p) + self.dst_axon_width(p)
    dy = BitArray(bin=rev_line[base_offset:base_offset + self.dy_width(p)][::-1]).int
    base_offset += self.dy_width(p)
    dx = BitArray(bin=rev_line[base_offset:base_offset + self.dx_width(p)][::-1]).int
    return (cd.x + dx, cd.y + dy)

  def assert_no_packets_sent_to_axons(self, dst_cd, axons=None):
    if axons is None:
      axons = [i for i in range(self.arch_params.num_axons)]

    # check input packets
    for packet in self.input_packets:
      start_idx = 0

      def read_field(length):
        nonlocal start_idx
        field_value = (packet >> start_idx) & ((2 ** length) - 1)
        start_idx += length

        if field_value < 0:
          return BitArray(int=field_value, length=length).uint
        else:
          return field_value

      destination_tick = read_field(self.tick_width())
      destination_axon = read_field(self.dst_axon_width())
      destination_core_offset_y = read_field(self.dy_width())
      destination_core_offset_x = read_field(self.dx_width())
      if ((destination_core_offset_x, destination_core_offset_y) == dst_cd.pos) and (destination_axon in axons):
        raise Exception("packet being sent to axon {} of core {}".format(destination_axon, dst_cd.pos))

    # check all non-dummy neurons
    no_input_axons = self.no_input_axons_bit_str_prefix()
    for cd in self.cores:
      tc_lines, csram_lines = self.core_data_words_to_mem(cd)
      for line_idx, line in enumerate(csram_lines):
        if (not line.startswith(no_input_axons)) and \
           (self.from_csram_line_get_dst_core(line, cd) == dst_cd.pos) and \
           (self.from_csram_line_get_dst_axon(line) in axons):
          raise Exception("neuron {} of core {} connects to axon {} of core {}".format(
            line_idx, cd.pos, destination_axon, dst_cd.pos))

  def move_connected_component(self, mcc, dst_pos, dst_base_axon_idx, dst_model, src_to_dst):
    assert self != dst_model
    src_cd, src_axons, src_neurons = mcc
    dst_axons = [dst_base_axon_idx + i for i in range(len(src_axons))]
    print("moving axons ∈ [{}, {}] of core {} to axons ∈ [{}, {}] of core {} ... ".format(
      src_axons[0], src_axons[-1], src_cd.pos, dst_axons[0], dst_axons[-1], dst_pos), end="")

    dst_cd = None
    for cd in dst_model.cores:
      if cd.pos == dst_pos:
        dst_cd = cd
        break
    if dst_cd is None:
      dst_cd = dst_model.empty_core(*dst_pos)
      dst_model.cores.append(dst_cd)

    assert dst_cd.x != dst_model.arch_params.output_core_x_coordinate or dst_cd.y != dst_model.arch_params.output_core_y_coordinate, "cannot move neurons to output core"

    for a in dst_axons:
      if a not in dst_cd.unused_axons:
        raise Exception("trying to move axon to an occupied location")

    for a in src_axons:
      if a in src_cd.unused_axons:
        raise Exception("trying to move an unused axon")

    src_tc_lines, src_csram_lines = self.core_data_words_to_mem(src_cd)
    dst_tc_lines, dst_csram_lines = dst_model.core_data_words_to_mem(dst_cd)

    # update input packets - check destination core and axon, if match adjust core and axon
    self.update_input_packets(src_cd, src_axons, dst_cd, dst_axons, dst_model)

    # copy over axons to new core
    assert self.arch_params.num_weights == dst_model.arch_params.num_weights
    for i, src_axon in enumerate(src_axons):
      dst_tc_lines[dst_axons[i]] = src_tc_lines[src_axon]

    # copy over neurons to new core and adjust axon mapping
    assert self.arch_params.num_ticks == dst_model.arch_params.num_ticks
    dst_neurons = dst_cd.unused_neurons[:len(src_neurons)]
    for i, src_neuron in enumerate(src_neurons):
      axons_bit_str = "".join(['1' if a in dst_axons and src_axons[dst_axons.index(
        a)] in src_cd.used_neuron_to_axons[src_neuron] else '0' for a in range(dst_model.arch_params.num_axons)][::-1])
      dst_x, dst_y = self.from_csram_line_get_dst_core(src_csram_lines[src_neuron], src_cd)
      dst_axon = self.from_csram_line_get_dst_axon(src_csram_lines[src_neuron])

      dst_x, dst_y, dst_axon = src_to_dst[dst_x, dst_y, dst_axon]

      dx = dst_x - dst_cd.x
      dy = dst_y - dst_cd.y
      core_offset_x_bit_str = BitArray(int=dx, length=dst_model.dx_width()).bin
      core_offset_y_bit_str = BitArray(int=dy, length=dst_model.dy_width()).bin
      dst_axon_bit_str = BitArray(uint=dst_axon, length=dst_model.dst_axon_width()).bin
      bit_str = axons_bit_str + src_csram_lines[src_neuron][self.arch_params.num_axons:-self.packet_width(
      )] + core_offset_x_bit_str + core_offset_y_bit_str + dst_axon_bit_str + src_csram_lines[src_neuron][-self.tick_width():]
      dst_csram_lines[dst_neurons[i]] = bit_str
      assert len(bit_str) == dst_model.csram_read_width()

    # regenerate modified core (including usage metadata)
    dst_model.cores[dst_model.cores.index(dst_cd)] = model_util(
      dst_model.arch_params, dst_model.arch_params).gen_core(dst_tc_lines, dst_csram_lines, dst_cd.x, dst_cd.y)

    print("done")

  def remove_dud_neurons_and_input_packets(self, params=None):
    p = self.arch_params if params is None else params
    print("removing dud neurons and input packets...")
    num_neurons_removed = 0
    num_packets_removed = 0

    empty_neuron_prefix = self.no_input_axons_bit_str_prefix(p)
    removed_dud_neuron = True
    while removed_dud_neuron:
      removed_dud_neuron = False

      valid_axons = []
      for cd in self.cores:
        for connected_axons, connected_neurons in cd.minimal_connected_components:
          for i, a in enumerate(connected_axons):
            valid_axons.append((cd.x, cd.y, a))

      for a in range(p.num_axons):
        valid_axons.append((p.output_core_x_coordinate, p.output_core_y_coordinate, a))

      for cd_idx, cd in enumerate(self.cores):
        removed_dud_neuron_in_this_core = False
        tc_lines, csram_lines = self.core_data_words_to_mem(cd, p)
        for line_idx, line in enumerate(csram_lines):
          if line.startswith(empty_neuron_prefix):
            continue

          dst_x, dst_y = self.from_csram_line_get_dst_core(line, cd)
          dst_axon = self.from_csram_line_get_dst_axon(line)
          if (dst_x, dst_y, dst_axon) in valid_axons:
            continue

          csram_lines[line_idx] = self.unused_neuron_bit_str(p)

          num_neurons_removed += 1
          removed_dud_neuron_in_this_core = True
          print("removed dud neuron {} of core {}".format(line_idx, cd.pos))

        if removed_dud_neuron_in_this_core:
          self.cores[cd_idx] = model_util(p, p).gen_core(tc_lines, csram_lines, cd.x, cd.y)
          removed_dud_neuron = True

      packet_idx = 0
      num_packets_idx = 0
      rem_packets_this_tick = int(self.num_input_packets[num_packets_idx])
      while packet_idx < len(self.input_packets):
        packet = self.input_packets[packet_idx]
        while rem_packets_this_tick == 0:
          num_packets_idx += 1
          rem_packets_this_tick = int(self.num_input_packets[num_packets_idx])
        rem_packets_this_tick -= 1

        start_idx = 0

        def read_field(length):
          nonlocal start_idx
          field_value = (packet >> start_idx) & ((2 ** length) - 1)
          start_idx += length

          if field_value < 0:
            return BitArray(int=field_value, length=length).uint
          else:
            return field_value

        dst_tick = read_field(self.tick_width(p))
        dst_axon = read_field(self.dst_axon_width(p))
        dst_y = read_field(self.dy_width(p))
        dst_x = read_field(self.dx_width(p))
        if (dst_x, dst_y, dst_axon) in valid_axons:
          packet_idx += 1
          continue

        self.input_packets.pop(packet_idx)
        self.num_input_packets[num_packets_idx] -= 1
        num_packets_removed += 1
        print("removed dud input packet sent at tick {}".format(num_packets_idx))

    print("removed {} dud neurons and {} dud input packets".format(num_neurons_removed, num_packets_removed))
    return num_neurons_removed, num_packets_removed

  def remove_empty_cores(self):
    print("removing empty cores...")

    i = 0
    num_cores_removed = 0
    while i < len(self.cores):
      if len(self.cores[i].unused_axons) != self.arch_params.num_axons:
        i += 1
        continue

      self.assert_no_packets_sent_to_axons(self.cores[i])
      print("removed empty core {}".format(self.cores[i].pos))
      self.cores.pop(i)
      num_cores_removed += 1

    print("removed {} empty cores, {} cores remaining".format(num_cores_removed, len(self.cores)))

  def pack_output_axons(self, params=None):
    print("packing output axons...")
    p = self.arch_params if params is None else params

    # find all used axons
    used_axons = []
    for cd in self.cores:
      tc_lines, csram_lines = self.core_data_words_to_mem(cd, p)
      for n in cd.used_neurons:
        dst_x, dst_y = self.from_csram_line_get_dst_core(csram_lines[n], cd, p)
        dst_axon = self.from_csram_line_get_dst_axon(csram_lines[n], p)
        if dst_x == p.output_core_x_coordinate and dst_y == p.output_core_y_coordinate:
          used_axons.append(dst_axon)

    used_axons = list(set(used_axons))
    used_axons.sort()

    for new_a, old_a in enumerate(used_axons):
      if new_a != old_a:
        print("moving output axon {} to axon {}".format(old_a, new_a))

    # ensure that all unused axons are not expected in output, if they are then there is a bug in our implementation.
    for packet in self.output_packets:
      if packet not in used_axons:
        raise Exception("expecting dud output axon {} to fire".format(packet))

    # update output data
    for i, old_axon in enumerate(self.output_packets):
      self.output_packets[i] = used_axons.index(old_axon)

    # update core data
    empty_neuron_prefix = self.no_input_axons_bit_str_prefix(p)
    for cd_idx, cd in enumerate(self.cores):
      modified_core = False
      tc_lines, csram_lines = self.core_data_words_to_mem(cd, p)
      for line_idx, line in enumerate(csram_lines):
        if line.startswith(empty_neuron_prefix):
          continue

        dst_x, dst_y = self.from_csram_line_get_dst_core(line, cd, p)
        if dst_x != p.output_core_x_coordinate or dst_y != p.output_core_y_coordinate:
          continue

        old_dst_axon = self.from_csram_line_get_dst_axon(line, p)
        new_dst_axon = used_axons.index(old_dst_axon)
        if old_dst_axon == new_dst_axon:
          continue

        dx = dst_x - cd.x
        dy = dst_y - cd.y
        core_offset_x_bit_str = BitArray(int=dx, length=self.dx_width(p)).bin
        core_offset_y_bit_str = BitArray(int=dy, length=self.dy_width(p)).bin
        dst_axon_bit_str = BitArray(uint=new_dst_axon, length=self.dst_axon_width(p)).bin
        bit_str = line[:-self.packet_width(p)] + core_offset_x_bit_str + \
            core_offset_y_bit_str + dst_axon_bit_str + line[-self.tick_width(p):]
        csram_lines[line_idx] = bit_str
        assert len(bit_str) == self.csram_read_width(p)
        modified_core = True

      if modified_core:
        self.cores[cd_idx] = model_util(p, p).gen_core(tc_lines, csram_lines, cd.x, cd.y)

    old_num_outputs = round(2 ** math.ceil(math.log(p.num_outputs, 2)))
    new_num_outputs = round(2 ** math.ceil(math.log(len(used_axons), 2)))
    print("packed output axons thereby changing the number of outputs from {} to {}".format(old_num_outputs, new_num_outputs))
    return new_num_outputs

  def pack_cores(self, old_params=None, new_params=None, minimise_arch_dims=True, minimise_num_outputs=True):
    print("packing cores...")
    old_params = self.arch_params if old_params is None else old_params
    new_params = self.arch_params if new_params is None else new_params

    old_x_dim = old_params.output_core_x_coordinate
    old_y_dim = old_params.output_core_y_coordinate
    for cd in self.cores:
      old_x_dim = max(old_x_dim, cd.x + 1)
      old_y_dim = max(old_y_dim, cd.y + 1)

    self.remove_empty_cores()
    num_neurons_removed, num_packets_removed = self.remove_dud_neurons_and_input_packets(old_params)  # 0, 0 #
    self.remove_empty_cores()

    new_num_outputs = self.pack_output_axons(old_params)
    old_params = set_spikehard_param(old_params, "num_outputs", new_num_outputs)
    if minimise_num_outputs:
      new_params = set_spikehard_param(new_params, "num_outputs", new_num_outputs)
    assert new_params.num_outputs >= new_num_outputs, "target architecture has insufficient output axons"
    assert new_params.num_axons >= new_params.num_outputs, "target architecture has insufficient axons for output core"

    total_neurons = 0
    total_axons = 0
    total_mccs = 0
    mccs = []
    for cd in self.cores:
      for connected_axons, connected_neurons in cd.minimal_connected_components:
        mccs.append([cd, connected_axons, connected_neurons])
        total_mccs += 1
        total_neurons += len(connected_neurons)
        total_axons += len(connected_axons)

    print("total MCCs:", total_mccs)
    print("total axons:", total_axons)
    print("total neurons:", total_neurons)

    item_num_axons = [len(mcc[1]) for mcc in mccs]
    item_num_neurons = [len(mcc[2]) for mcc in mccs]
    items = list(range(len(mccs)))
    bins = list(range(new_params.grid_dimension_x * new_params.grid_dimension_y - 1))
    bin_axon_capacity = new_params.num_axons
    bin_neuron_capacity = new_params.num_neurons

    mcc_size = [len(mcc[1]) * len(mcc[2]) for mcc in mccs]
    print("MCC min axons: {}, max axons: {}".format(min(item_num_axons), max(item_num_axons)))
    print("MCC min neurons: {}, max neurons: {}".format(min(item_num_neurons), max(item_num_neurons)))
    print("MCC min size: {}, max size: {}".format(min(mcc_size), max(mcc_size)))
    results = [min(item_num_axons), max(item_num_axons), min(item_num_neurons),
               max(item_num_neurons), min(mcc_size), max(mcc_size)]
    print(results)

    # This implementation is inspired by: https://developers.google.com/optimization/bin/bin_packing

    solver = pywraplp.Solver.CreateSolver('SCIP')

    # variable: x[i, j] = 1 if item i is packed in bin j.
    x = {}
    for i in items:
      for j in bins:
        x[(i, j)] = solver.IntVar(0, 1, 'x_%i_%i' % (i, j))

    # variable: y[j] = 1 if bin j is used.
    y = {}
    for j in bins:
      y[j] = solver.IntVar(0, 1, 'y[%i]' % j)

    # constraint: each item must be in exactly one bin.
    for i in items:
      solver.Add(sum(x[i, j] for j in bins) == 1)

    # constraint: the amount packed in each bin cannot exceed its 2D capacity.
    for j in bins:
      solver.Add(sum(x[(i, j)] * item_num_axons[i] for i in items) <= y[j] * bin_axon_capacity)
      solver.Add(sum(x[(i, j)] * item_num_neurons[i] for i in items) <= y[j] * bin_neuron_capacity)

    print("performing resource allocation...")
    solver.Minimize(solver.Sum([y[j] for j in bins]))
    print("allocated resources in {} seconds".format(solver.WallTime() / 1000))

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
      raise Exception("no valid solution found for core packing")

    num_bins_used = 0
    for bin_idx in bins:
      if y[bin_idx].solution_value() == 1:
        num_bins_used += 1

    assert (num_bins_used + 1) < (new_params.grid_dimension_x * new_params.grid_dimension_y), "too many cores"

    new_x_dim = new_params.output_core_x_coordinate + 1
    new_y_dim = new_params.output_core_y_coordinate + 1
    possible_x_dim = list(range(new_x_dim + 1, new_params.grid_dimension_x + 1))[::-1]
    possible_y_dim = list(range(new_y_dim + 1, new_params.grid_dimension_y + 1))[::-1]
    while (num_bins_used + 1) > (new_x_dim * new_y_dim):
      if len(possible_x_dim) >= len(possible_y_dim):
        new_x_dim = possible_x_dim.pop()
      else:
        new_y_dim = possible_y_dim.pop()

    out_core_idx = new_params.output_core_x_coordinate + new_x_dim * new_params.output_core_y_coordinate

    actions = []
    all_num_utilised_axons = []
    all_num_utilised_neurons = []
    for bin_idx in bins:
      if y[bin_idx].solution_value() != 1:
        continue

      core_x = (len(actions) + int(out_core_idx <= len(actions))) % new_x_dim
      core_y = (len(actions) + int(out_core_idx <= len(actions))) // new_x_dim
      dst_pos = (core_x, core_y)

      num_utilised_axons = 0
      num_utilised_neurons = 0
      move_ops = []

      for item_idx in items:
        if x[item_idx, bin_idx].solution_value() <= 0:
          continue

        mcc = mccs[item_idx]
        dst_base_axon_idx = int(num_utilised_axons)
        dst_base_neuron_idx = int(num_utilised_neurons)
        move_ops.append([dst_base_axon_idx, dst_base_neuron_idx, mcc])

        num_utilised_axons += item_num_axons[item_idx]
        num_utilised_neurons += item_num_neurons[item_idx]
        assert len(mcc[1]) == item_num_axons[item_idx], (len(mcc[1]), item_num_axons[item_idx])
        assert len(mcc[2]) == item_num_neurons[item_idx], (len(mcc[2]), item_num_neurons[item_idx])

      actions.append([dst_pos, move_ops])
      all_num_utilised_axons.append(num_utilised_axons)
      all_num_utilised_neurons.append(num_utilised_neurons)
      print("core {} will contain {} minimal connected components with {}/{} utilised axons and {}/{} utilised neurons".format(
        dst_pos, len(move_ops), num_utilised_axons, new_params.num_axons, num_utilised_neurons, new_params.num_neurons))

    old_min_num_pad_cores = (old_x_dim * old_y_dim) - (len(self.cores) + 1)
    new_min_num_pad_cores = (new_x_dim * new_y_dim) - (num_bins_used + 1)
    old_axon_utilisation_unpadded = np.mean(
      np.array([len(cd.used_axons) for cd in self.cores], dtype=np.float32)) / old_params.num_axons * 100.0
    old_neuron_utilisation_unpadded = np.mean(
      np.array([len(cd.used_neurons) for cd in self.cores], dtype=np.float32)) / old_params.num_neurons * 100.0
    new_axon_utilisation_unpadded = np.mean(
      np.array(all_num_utilised_axons, dtype=np.float32)) / new_params.num_axons * 100.0
    new_neuron_utilisation_unpadded = np.mean(
      np.array(all_num_utilised_neurons, dtype=np.float32)) / new_params.num_neurons * 100.0
    old_axon_utilisation_padded = np.mean(np.array(
      [len(cd.used_axons) for cd in self.cores] + [0 for _ in range(old_min_num_pad_cores)], dtype=np.float32)) / old_params.num_axons * 100.0
    old_neuron_utilisation_padded = np.mean(np.array([len(cd.used_neurons) for cd in self.cores] + [
                                            0 for _ in range(old_min_num_pad_cores)], dtype=np.float32)) / old_params.num_neurons * 100.0
    new_axon_utilisation_padded = np.mean(np.array(
      all_num_utilised_axons + [0 for _ in range(new_min_num_pad_cores)], dtype=np.float32)) / new_params.num_axons * 100.0
    new_neuron_utilisation_padded = np.mean(np.array(
      all_num_utilised_neurons + [0 for _ in range(new_min_num_pad_cores)], dtype=np.float32)) / new_params.num_neurons * 100.0

    print("minimum grid_dimension_x will change from {} to {}".format(old_x_dim, new_x_dim))
    print("minimum grid_dimension_y will change from {} to {}".format(old_y_dim, new_y_dim))
    print("minimum empty padding cores will change from {} to {}".format(old_min_num_pad_cores, new_min_num_pad_cores))
    print("number of utilised cores will change from {} to {}".format(len(self.cores), num_bins_used))
    print("average axon utilisation (excl. minimum empty padding cores) will change from {:.4f}% to {:.4f}%".format(
      old_axon_utilisation_unpadded, new_axon_utilisation_unpadded))
    print("average neuron utilisation (excl. minimum empty padding cores) will change from {:.4f}% to {:.4f}%".format(
      old_neuron_utilisation_unpadded, new_neuron_utilisation_unpadded))
    print("average axon utilisation (incl. minimum empty padding cores) will change from {:.4f}% to {:.4f}%".format(
      old_axon_utilisation_padded, new_axon_utilisation_padded))
    print("average neuron utilisation (incl. minimum empty padding cores) will change from {:.4f}% to {:.4f}%".format(
      old_neuron_utilisation_padded, new_neuron_utilisation_padded))

    results += [old_params.num_axons, old_params.num_neurons,
                new_params.num_axons, new_params.num_neurons,
                old_x_dim, old_y_dim,
                new_x_dim, new_y_dim,
                old_min_num_pad_cores, new_min_num_pad_cores,
                len(self.cores), num_bins_used,
                old_axon_utilisation_unpadded, new_axon_utilisation_unpadded,
                old_neuron_utilisation_unpadded, new_neuron_utilisation_unpadded,
                old_axon_utilisation_padded, new_axon_utilisation_padded,
                old_neuron_utilisation_padded, new_neuron_utilisation_padded,
                num_neurons_removed, num_packets_removed]

    print("results:", results)

    src_to_dst = {}

    for dst_pos, move_ops in actions:
      for dst_base_axon_idx, dst_base_neuron_idx, mcc in move_ops:
        cd, connected_axons, connected_neurons = mcc
        for i, a in enumerate(connected_axons):
          src_to_dst[cd.x, cd.y, a] = (*dst_pos, dst_base_axon_idx + i)

    for a in range(old_params.num_outputs):
      src_to_dst[old_params.output_core_x_coordinate, old_params.output_core_y_coordinate, a] = (
        new_params.output_core_x_coordinate, new_params.output_core_y_coordinate, a)

    dst_model = model_util(new_params, new_params, cores=[], input_packets=[-1 for _ in range(len(self.input_packets))],
                           output_packets=self.output_packets, num_input_packets=self.num_input_packets, num_output_packets=self.num_output_packets)
    for dst_pos, move_ops in actions:
      for dst_base_axon_idx, dst_base_neuron_idx, mcc in move_ops:
        self.move_connected_component(mcc, dst_pos, dst_base_axon_idx, dst_model, src_to_dst)

    self.cores = dst_model.cores
    self.input_packets = dst_model.input_packets

    if minimise_arch_dims:
      new_params = set_spikehard_param(new_params, "grid_dimension_x", new_x_dim)
      new_params = set_spikehard_param(new_params, "grid_dimension_y", new_y_dim)

    new_params = set_spikehard_param(new_params, "memory_filepath", None)
    self.test_params = self.arch_params = new_params

    print("packed cores")
    return results

  def minimise_tick_delay(self, max_tick_delay=None, slack=None, num_ticks_to_check=None, initial_step_size=None, max_step_size=None, step_size_factor=None):
    print("tuning tick delay...")
    assert self.cores is not None, "model must be initialised"

    max_tick_delay = (1000000000 if max_tick_delay is None else max_tick_delay)
    slack = (0.1 if slack is None else slack)
    num_ticks_to_check = (self.test_params.num_ticks_to_check if num_ticks_to_check is None else num_ticks_to_check)
    initial_step_size = (20 if initial_step_size is None else initial_step_size)
    max_step_size = (50000 if max_step_size is None else max_step_size)
    step_size_factor = (10 if step_size_factor is None else step_size_factor)

    print(f"max_tick_delay: {max_tick_delay}, slack: {slack}, num_ticks_to_check: {num_ticks_to_check}, initial_step_size: {initial_step_size}, max_step_size: {max_step_size}, step_size_factor: {step_size_factor}")

    old_test_params = self.test_params
    old_arch_params = self.arch_params
    self.test_params = set_spikehard_param(self.test_params, "num_ticks_to_check", num_ticks_to_check)
    self.arch_params = set_spikehard_param(self.arch_params, "num_ticks_to_check", num_ticks_to_check)
    model_name = "__minimise_tick_delay_model_{}_{}__".format(self.arch_params.num_axons, self.arch_params.num_neurons)
    self.to_unit_tests(model_name)

    def cleanup():
      shutil.rmtree(os.path.join(TB_DIR, "memory_files", "altered", model_name), ignore_errors=True)
      shutil.rmtree(os.path.join(TB_DIR, "tests", "networks", "altered", model_name), ignore_errors=True)

    def cancel():
      cleanup()
      self.test_params = old_test_params
      self.arch_params = old_arch_params

    def run_test(params):
      class test(unittest.TestCase):
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)

        def test(test_self):
          # add '/hardware/tb/tests/networks' to system path for module imports
          sys.path.insert(0, os.path.join(TB_DIR, "tests", "networks"))
          from spikehard import spikehard  # noqa: E402

          spikehard.run_test(test_self, params)

      runner = unittest.TextTestRunner()
      result = runner.run(unittest.makeSuite(test))
      if result.errors or result.failures:
        raise Exception("tick delay not suitable")

    def try_tick_delay(tick_delay):
      print("attempting tick delay: {} clock cycles".format(tick_delay))
      try:
        run_test(set_spikehard_param(self.arch_params, "clock_cycles_per_tick", tick_delay))
      except KeyboardInterrupt:
        cancel()
        raise
      except:
        if tick_delay == max_tick_delay:
          cancel()
          raise Exception("failed to find suitable tick delay")
        else:
          return False
      return True

    # quickly find upper bound
    step_size = initial_step_size
    prev_tick_delay = 0
    tick_delay = step_size
    while not try_tick_delay(tick_delay):
      prev_tick_delay = tick_delay
      step_size = round(min(step_size * step_size_factor, max_step_size))
      tick_delay = round(min(((tick_delay + step_size) - 1) | (step_size - 1) + 1, max_tick_delay))

    # perform binary search
    low = prev_tick_delay
    high = tick_delay
    while low < high:
      tick_delay = round((high + low) / 2)
      if tick_delay == high:
        break

      should_stop = (high - tick_delay) < slack * tick_delay
      if try_tick_delay(tick_delay):
        high = tick_delay
      else:
        low = tick_delay
      if should_stop:
        break

    # add slack since it is not guaranteed to work for any input combination
    tick_delay = round(min(high + high * slack, max_tick_delay))

    cleanup()
    self.test_params = set_spikehard_param(old_test_params, "clock_cycles_per_tick", tick_delay)
    self.arch_params = set_spikehard_param(old_arch_params, "clock_cycles_per_tick", tick_delay)
    print("tuned tick delay (incl. {}% slack): {} clock cycles".format(slack * 100, tick_delay))
    return (tick_delay, slack)
  
  @staticmethod
  def default_model_header_dir():
    return os.path.join(HARDWARE_DIR, "sw", "spikehard_model")

  @staticmethod
  def clean_model_headers(dst_dir=None):
    if dst_dir is None:
      dst_dir = model_util.default_model_header_dir()
    shutil.rmtree(dst_dir, ignore_errors=True)

  def to_header(self, model_name, dst_dir=None):
    assert self.cores is not None, "model must be initialised"
    assert self.in_packets_payload_word_width == 32, "app library does not support packet width != 32"

    if dst_dir is None:
      dst_dir = model_util.default_model_header_dir()

    out = ""

    out += "#ifndef SPIKEHARD_MODEL_{}_H_INCLUDED\n".format(model_name.upper())
    out += "#define SPIKEHARD_MODEL_{}_H_INCLUDED\n\n".format(model_name.upper())

    tc_words_vars = []
    csram_words_vars = []
    tc_words_lengths = []
    csram_words_lengths = []

    for cd in self.cores:
      assert cd.x < self.arch_params.grid_dimension_x and cd.y < self.arch_params.grid_dimension_y, "core lies outside the grid"
      assert cd.x != self.arch_params.output_core_x_coordinate or cd.y != self.arch_params.output_core_y_coordinate, "regular core coincides with output core"

      tc_words_var = "g_{}_tc_words_{}_{}_".format(model_name.lower(), cd.x, cd.y)
      out += "static uint{}_t {}[{}u] = ".format(self.core_data_payload_word_width, tc_words_var, len(cd.tc_words))
      out += "{"
      out += ", ".join([str(w) + 'u' for w in cd.tc_words])
      out += "};\n"
      tc_words_vars.append(tc_words_var)
      tc_words_lengths.append(str(len(cd.tc_words)))

      csram_words_var = "g_{}_csram_words_{}_{}_".format(model_name.lower(), cd.x, cd.y)
      out += "static uint{}_t {}[{}u] = ".format(self.core_data_payload_word_width,
                                                 csram_words_var, len(cd.csram_words))
      out += "{"
      out += ", ".join([str(w) + 'u' for w in cd.csram_words])
      out += "};\n\n"
      csram_words_vars.append(csram_words_var)
      csram_words_lengths.append(str(len(cd.csram_words)))

    model_var = "g_{}_cores".format(model_name.lower())
    out += "static core_data_t {}[{}u] = ".format(model_var, len(self.cores))
    out += "{"
    for i in range(len(self.cores)):
      out += "{"
      out += "{}u, {}u, {}, {}, {}u, {}u".format(self.cores[i].x, self.cores[i].y,
                                                 tc_words_vars[i], csram_words_vars[i], tc_words_lengths[i], csram_words_lengths[i])
      out += "}"
      if i + 1 != len(self.cores):
        out += ", "
    out += "};\n\n"

    num_inputs_words = []
    for value in self.num_input_packets:
      num_inputs_words.append(str(value) + 'u')

    out += "static uint32_t g_{}_num_inputs[{}u] = ".format(model_name.lower(), len(num_inputs_words))
    out += "{"
    out += ", ".join(num_inputs_words)
    out += "};\n\n"

    num_outputs_words = []
    for value in self.num_output_packets:
      num_outputs_words.append(str(value) + 'u')

    out += "static uint32_t g_{}_num_outputs[{}u] = ".format(model_name.lower(), len(num_outputs_words))
    out += "{"
    out += ", ".join(num_outputs_words)
    out += "};\n\n"

    inputs_words = []
    for input_packet in self.input_packets:
      inputs_words.append(str(input_packet) + 'u')

    out += "static packet_t g_{}_inputs[{}u] = ".format(model_name.lower(), len(inputs_words))
    out += "{"
    out += ", ".join(inputs_words)
    out += "};\n\n"

    outputs_words = []
    for output_packet in self.output_packets:
      outputs_words.append(str(output_packet) + 'u')

    out += "static packet_t g_{}_outputs[{}u] = ".format(model_name.lower(), len(outputs_words))
    out += "{"
    out += ", ".join(outputs_words)
    out += "};\n\n"
    
    num_ticks_to_check = (len(num_outputs_words) + self.test_params.tick_latency + 2) if self.test_params.num_ticks_to_check is None else self.test_params.num_ticks_to_check

    out += "static test_bench_t g_{}_test_bench = ".format(model_name.lower())
    out += "{"
    out += "g_{}_cores, g_{}_num_inputs, g_{}_num_outputs, g_{}_inputs, g_{}_outputs, {}u, {}u, {}u, {}u, {}u, {}u, {}u, {}u, {}".format(*([model_name.lower()] * 5), len(self.cores), len(num_inputs_words), len(
      num_outputs_words), len(inputs_words), len(outputs_words), num_ticks_to_check, self.test_params.tick_latency, self.test_params.clock_cycles_per_tick, str(bool(self.test_params.relax_packet_ordering)).lower())
    out += "};\n\n"

    out += "#endif // SPIKEHARD_MODEL_{}_H_INCLUDED\n".format(model_name.upper())

    pathlib.Path(dst_dir).mkdir(parents=True, exist_ok=True)
    with open(os.path.join(dst_dir, "{}.h".format(model_name.lower())), "w") as f:
      f.write(out)

  def to_unit_tests(self, model_name):
    print("generating unit tests for model: {}".format(model_name))
    assert self.cores is not None, "model must be initialised"

    altered_tests_dir = os.path.join(HARDWARE_DIR, "tb", "tests", "networks", "altered", model_name.lower())
    os.makedirs(altered_tests_dir, exist_ok=True)

    subtest_name = str(self.arch_params.num_axons) if self.arch_params.num_axons == self.arch_params.num_neurons else '{}_{}'.format(
      self.arch_params.num_axons, self.arch_params.num_neurons)
    model_memory_files_dir = os.path.join(HARDWARE_DIR, "tb", "memory_files",
                                          "altered", model_name.lower(), subtest_name)
    if os.path.exists(model_memory_files_dir):
      shutil.rmtree(model_memory_files_dir)
    os.makedirs(model_memory_files_dir, exist_ok=False)

    self.dump_params(model_memory_files_dir)

    test_code = """\
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
class test_<<model_name>>_<<subtest_name>>(unittest.TestCase):
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.DEBUG)

  @staticmethod
  def gen_test_params(**kwargs):
      return basic_test_util.gen_test_params(model_name = "<<model_name>>", altered = True, num_axons = <<num_axons>>, num_neurons = <<num_neurons>>, **kwargs)

  def test(self):
    test_params = test_<<model_name>>_<<subtest_name>>.gen_test_params(dma_bus_width = <<dma_bus_width>>, dma_frame_header_word_width = <<dma_frame_header_word_width>>, router_buffer_depth = <<router_buffer_depth>>)
    spikehard.run_test(self, test_params)

if __name__ == '__main__':
  unittest.main()
    """

    test_code = test_code.replace("<<model_name>>", model_name.lower())
    test_code = test_code.replace("<<subtest_name>>", subtest_name)
    test_code = test_code.replace("<<num_axons>>", str(self.arch_params.num_axons))
    test_code = test_code.replace("<<num_neurons>>", str(self.arch_params.num_neurons))
    test_code = test_code.replace("<<dma_bus_width>>", str(self.arch_params.dma_bus_width))
    test_code = test_code.replace("<<dma_frame_header_word_width>>", str(self.arch_params.dma_frame_header_word_width))
    test_code = test_code.replace("<<router_buffer_depth>>", str(self.arch_params.router_buffer_depth))
    test_code = test_code.rstrip() + '\n'

    with open(os.path.join(altered_tests_dir, 'test_' + model_name.lower() + '_' + subtest_name + '.py'), 'w') as file:
      file.write(test_code)

    with open(os.path.join(model_memory_files_dir, 'tb_correct.txt'), 'w') as file:
      file.write("\n".join([BitArray(uint=x, length=self.output_packet_width()).bin for x in self.output_packets]))

    with open(os.path.join(model_memory_files_dir, 'tb_input.txt'), 'w') as file:
      file.write("\n".join([BitArray(uint=x, length=self.packet_width()).bin for x in self.input_packets]))

    with open(os.path.join(model_memory_files_dir, 'tb_num_inputs.txt'), 'w') as file:
      file.write("\n".join([str(x) for x in self.num_input_packets]))

    with open(os.path.join(model_memory_files_dir, 'tb_num_outputs.txt'), 'w') as file:
      file.write("\n".join([str(x) for x in self.num_output_packets]))

    for cd in self.cores:
      assert cd.x < self.arch_params.grid_dimension_x and cd.y < self.arch_params.grid_dimension_y, "core lies outside the grid"
      assert cd.x != self.arch_params.output_core_x_coordinate or cd.y != self.arch_params.output_core_y_coordinate, "regular core coincides with output core"

      idx = str(cd.x + cd.y * self.arch_params.grid_dimension_x).zfill(
        len(str(self.arch_params.grid_dimension_x * self.arch_params.grid_dimension_y - 1)))
      tc_lines, csram_lines = self.core_data_words_to_mem(cd)

      with open(os.path.join(model_memory_files_dir, 'tc_{}.mem'.format(idx)), 'w') as file:
        file.write("\n".join(tc_lines) + '\n')

      with open(os.path.join(model_memory_files_dir, 'csram_{}.mem'.format(idx)), 'w') as file:
        file.write("\n".join(csram_lines) + '\n')

    self.test_params = self.arch_params = set_spikehard_param(
      self.arch_params, "memory_filepath", model_memory_files_dir)
    print("generated unit tests for model: {}".format(model_name))

  def dump_params(self, model_memory_files_dir):
    params = copy.deepcopy(self.arch_params._asdict())
    params["num_ticks_to_check"] = self.test_params.num_ticks_to_check
    params["tick_latency"] = self.test_params.tick_latency
    params["relax_packet_ordering"] = bool(self.test_params.relax_packet_ordering)
    params.pop("memory_filepath", None)
    params.pop("dma_bus_width", None)
    params.pop("dma_frame_header_word_width", None)
    params.pop("router_buffer_depth", None)
    with open(basic_test_util.spikehard_test_params_filepath(model_memory_files_dir), 'w') as f:
      f.write(json.dumps(params, indent='\t'))
