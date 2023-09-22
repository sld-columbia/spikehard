import os
import itertools
import subprocess
import shutil
import json

from myhdl import Cosimulation, Signal, intbv
import pytest

from common_util import ROOT_DIR, IMPL_DIR, TB_DIR, spikehard_named_params


@pytest.fixture(autouse=True)
def expose_markers_option_fixture(request, pytestconfig):
  request.cls.markers_option = pytestconfig.getoption('-m')
  request.cls.fast_marker = "fast" in request.cls.markers_option
  request.cls.ci_marker = "ci" in request.cls.markers_option


class basic_test_util():
  @staticmethod
  def run_subtests(testcase, run_test=None, keys=None, all_args=None, **kwargs):
    if run_test is None:
      run_test = testcase.run_test

    if (keys is None) != (all_args is None):
      raise Exception("keys is specified if and only if all_args is specified")

    if keys is None:
      all_args = itertools.product(*kwargs.values())
      keys = list(kwargs.keys())
      test_count = 1
      for v in kwargs.values():
        test_count *= len(v)
    else:
      test_count = len(all_args)

    for test_idx, args in enumerate(all_args):
      subtest_kwargs = dict(zip(keys, args))
      with testcase.subTest(**subtest_kwargs):
        testcase.logger.debug("==>> running subtest ({}/{}) - args: ({}) <<==".format(test_idx + 1,
                              test_count, ", ".join(["{} = {}".format(k, v) for k, v in subtest_kwargs.items()])))
        run_test(**subtest_kwargs)

  @staticmethod
  def correct_filepath(test_params):
    return os.path.join(test_params.memory_filepath, 'tb_correct.txt')

  @staticmethod
  def input_filepath(test_params):
    return os.path.join(test_params.memory_filepath, 'tb_input.txt')

  @staticmethod
  def num_inputs_filepath(test_params):
    return os.path.join(test_params.memory_filepath, 'tb_num_inputs.txt')

  @staticmethod
  def num_outputs_filepath(test_params):
    return os.path.join(test_params.memory_filepath, 'tb_num_outputs.txt')

  @staticmethod
  def spikehard_test_params_filepath(memory_filepath):
    return os.path.join(memory_filepath, 'tb_spikehard_params.json')

  @staticmethod
  def gen_test_params(model_name, altered=False, num_axons=256, num_neurons=256, num_ticks_to_check=None, dma_bus_width=32, dma_frame_header_word_width=32, router_buffer_depth=4, clock_cycles_per_tick=None):
    if num_axons == num_neurons:
      test_name = str(num_axons)
    else:
      test_name = '{}_{}'.format(num_axons, num_neurons)

    memory_filepath = '{}/memory_files/{}{}/{}'.format(TB_DIR, "altered/" if altered else "", model_name, test_name)
    if not os.path.exists(memory_filepath):
      print('unrecognised axon/neuron combination')
      quit()

    with open(basic_test_util.spikehard_test_params_filepath(memory_filepath), 'r') as f:
      config_json_data = json.loads(f.read())

    if num_ticks_to_check is not None:
      config_json_data["num_ticks_to_check"] = num_ticks_to_check
    if clock_cycles_per_tick is not None:
      config_json_data["clock_cycles_per_tick"] = clock_cycles_per_tick

    test_params = spikehard_named_params(**config_json_data,
                                         dma_bus_width=dma_bus_width,
                                         dma_frame_header_word_width=dma_frame_header_word_width,
                                         router_buffer_depth=router_buffer_depth,
                                         memory_filepath=memory_filepath)

    return test_params


class myhdl_util():
  @staticmethod
  def gen_cosimulation(dut, work_dir, params, *ports, src_dirs=None):
    if src_dirs is None:
      src_dirs = [IMPL_DIR]

    cmd = "iverilog -o {}.o".format(dut)

    for d in src_dirs:
      cmd += " -I {}".format(d)

    for field in params._fields:
      value = getattr(params, field)
      try:
        v = int(value)
      except:
        if isinstance(value, str):
          cmd += " -D{}=\\\"{}\\\"".format(field.upper(), value)
        continue
      cmd += " -D{}={}".format(field.upper(), value)

    cmd += " -s {}".format(dut)

    for d in src_dirs:
      cmd += " {}/*.v".format(d)
    cmd += " {}/{}.v".format(work_dir, dut)

    cmd += " -g2005-sv"

    subprocess.run(cmd, check=True, shell=True)

    ports_dict = {}
    for ps in ports:
      ports_dict.update(ps._asdict())

    return Cosimulation("vvp -m {}/iverilog/myhdl.vpi {}.o".format(TB_DIR, dut), **ports_dict)

  @staticmethod
  def gen_signal(num_bits, num_signals=1):
    if num_signals == 1:
      if num_bits == 1:
        return Signal(bool(0))
      else:
        return Signal(intbv(0, min=0, max=(2**num_bits) - 1)[num_bits:0])
    else:
      return [myhdl_util.gen_signal(num_bits) for _ in range(num_signals)]

  @staticmethod
  def to_int(signal) -> int:
    if hasattr(signal, 'val'):
      return int(bin(signal.val), 2)
    else:
      return int(bin(signal), 2)

  @staticmethod
  def to_intbv(value, num_bits):
    v = intbv(value, min=0, max=(2**num_bits) - 1)
    assert len(v) == num_bits
    return v

  @staticmethod
  def wait_for(clk, signal, value=1, timeout=100000):
    if timeout is None:
      while myhdl_util.to_int(signal) != value:
        yield clk.posedge
      return
    else:
      for _ in range(timeout):
        if myhdl_util.to_int(signal) == value:
          return
        yield clk.posedge
      raise TimeoutError("timed out whilst waiting for signal")

  @staticmethod
  def initialise_accelerator(testcase, input_ports, output_ports, tx_size=2 ** 31, rx_size=2 ** 31):
    # Initialise inputs
    input_ports.conf_done.next = 0
    input_ports.dma_read_ctrl_ready.next = 0
    input_ports.dma_read_chnl_valid.next = 0
    input_ports.dma_write_ctrl_ready.next = 0
    input_ports.dma_write_chnl_ready.next = 0

    # Waiting for nothing
    yield input_ports.clk.posedge
    yield input_ports.clk.posedge

    # Initialise accelerator
    yield input_ports.clk.posedge
    input_ports.rst.next = 0
    for _ in range(15):
      yield input_ports.clk.posedge
    yield input_ports.clk.posedge
    input_ports.rst.next = 1
    for _ in range(5):
      yield input_ports.clk.posedge
    yield input_ports.clk.posedge
    if hasattr(input_ports, "conf_info_tx_size"):
      input_ports.conf_info_tx_size.next = tx_size
    if hasattr(input_ports, "conf_info_rx_size"):
      input_ports.conf_info_rx_size.next = rx_size
    input_ports.conf_done.next = 1
    yield input_ports.clk.posedge
    input_ports.conf_done.next = 0
    yield input_ports.clk.posedge

  @staticmethod
  def __dma_word_size(word_width) -> int:
    return {8: 0, 16: 1, 32: 2, 64: 3}[word_width]

  @staticmethod
  def service_read_request(testcase,
                           input_ports,
                           output_ports,
                           read_offset,
                           read_length,
                           dma_bus_width,
                           word_width,
                           make_read_word,
                           noc_delay=None,
                           timeout=100000):
    if noc_delay is None:
      def zero() -> int:
        return 0

      noc_delay = zero

    dma_bus_mask = (2 ** dma_bus_width) - 1
    wait_for = lambda *args: myhdl_util.wait_for(input_ports.clk, *args, timeout=timeout)

    def make_read_data(beat_idx):
      if dma_bus_width >= word_width:
        v = 0
        words_per_beat = dma_bus_width // word_width
        for i in range(words_per_beat):
          v |= make_read_word(beat_idx * words_per_beat + i) << (i * word_width)
      else:
        beats_per_word = word_width // dma_bus_width
        v = (make_read_word(beat_idx // beats_per_word) >> ((beat_idx % beats_per_word) * dma_bus_width)) & dma_bus_mask

      return myhdl_util.to_intbv(v, dma_bus_width)

    for _ in range(noc_delay()):
      yield input_ports.clk.posedge

    # Wait for (dma_read_ctrl_valid && have dma_read_ctrl_ready).
    input_ports.dma_read_ctrl_ready.next = 1
    yield input_ports.clk.posedge
    yield from wait_for(output_ports.dma_read_ctrl_valid)
    input_ports.dma_read_ctrl_ready.next = 0

    # Check that length, word size, etc are as expected.
    testcase.assertEqual(myhdl_util.to_int(output_ports.dma_read_ctrl_data_index), read_offset)
    testcase.assertEqual(myhdl_util.to_int(output_ports.dma_read_ctrl_data_length), read_length)
    testcase.assertEqual(myhdl_util.to_int(output_ports.dma_read_ctrl_data_size),
                         myhdl_util.__dma_word_size(word_width))

    # Start sending data immediately afterwards with random delay between packets.
    for beat_idx in range(read_length):
      # Wait a predetermined or random number of clock ticks before sending data.
      for _ in range(noc_delay()):
        yield input_ports.clk.posedge

      # Send next beat of data
      input_ports.dma_read_chnl_data.next = make_read_data(beat_idx)
      input_ports.dma_read_chnl_valid.next = 1
      yield input_ports.clk.posedge

      # Wait for (dma_read_chnl_valid && have dma_read_chnl_ready).
      yield from wait_for(output_ports.dma_read_chnl_ready)
      input_ports.dma_read_chnl_valid.next = 0

  @staticmethod
  def service_write_request(testcase,
                            input_ports,
                            output_ports,
                            write_offset,
                            write_length,
                            dma_bus_width,
                            word_width,
                            check_write_word,
                            noc_delay=None,
                            timeout=100000):
    if noc_delay is None:
      def zero() -> int:
        return 0

      noc_delay = zero

    word_mask = (2 ** word_width) - 1
    wait_for = lambda *args: myhdl_util.wait_for(input_ports.clk, *args, timeout=timeout)

    write_word = 0

    def check_write_data(beat_idx, value):
      nonlocal write_word

      value = myhdl_util.to_int(value)
      if dma_bus_width >= word_width:
        words_per_beat = dma_bus_width // word_width
        for i in range(words_per_beat):
          word_idx = beat_idx * words_per_beat + i
          word_value = (value >> (i * word_width)) & word_mask
          check_write_word(word_idx, word_value)
      else:
        beats_per_word = word_width // dma_bus_width
        if (beat_idx % beats_per_word) == 0:
          write_word = 0
        write_word |= (value << (dma_bus_width * (beat_idx % beats_per_word)))
        if ((beat_idx + 1) % beats_per_word) == 0:
          check_write_word(beat_idx // beats_per_word, write_word)

    for _ in range(noc_delay()):
      yield input_ports.clk.posedge

    # Wait for (dma_write_ctrl_valid && have dma_write_ctrl_ready).
    input_ports.dma_write_ctrl_ready.next = 1
    yield input_ports.clk.posedge
    yield from wait_for(output_ports.dma_write_ctrl_valid)
    input_ports.dma_write_ctrl_ready.next = 0

    # Check that length, word size, etc are as expected.
    testcase.assertEqual(myhdl_util.to_int(output_ports.dma_write_ctrl_data_index), write_offset)
    testcase.assertEqual(myhdl_util.to_int(output_ports.dma_write_ctrl_data_length), write_length)
    testcase.assertEqual(myhdl_util.to_int(output_ports.dma_write_ctrl_data_size),
                         myhdl_util.__dma_word_size(word_width))

    # Start reading data immediately afterwards with random delay between when ready.
    for beat_idx in range(write_length):
      # Wait a predetermined or random number of clock ticks before ready to receive data.
      for _ in range(noc_delay()):
        yield input_ports.clk.posedge
      input_ports.dma_write_chnl_ready.next = 1
      yield input_ports.clk.posedge

      # Wait for (dma_write_chnl_ready && have dma_write_chnl_valid).
      yield from wait_for(output_ports.dma_write_chnl_valid)
      input_ports.dma_write_chnl_ready.next = 0

      # Validate.
      check_write_data(beat_idx, output_ports.dma_write_chnl_data)
