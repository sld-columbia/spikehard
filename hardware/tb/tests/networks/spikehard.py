from collections import namedtuple
import sys
import os
from bitstring import BitArray

from myhdl import Simulation, always, delay, StopSimulation

# add '/hardware/util' to system path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
  os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "util"))
from test_util import myhdl_util, basic_test_util  # noqa: E402
from common_util import file_util, spikehard_named_params  # noqa: E402
from model_util import model_util  # noqa: E402


class spikehard():
  InputPorts = namedtuple('input_ports',
                          'clk, rst, conf_info_tx_size, conf_info_rx_size, conf_done,'
                          'dma_read_ctrl_ready, dma_read_chnl_valid, dma_read_chnl_data,'
                          'dma_write_ctrl_ready, dma_write_chnl_ready')

  OutputPorts = namedtuple('output_ports',
                           'dma_read_ctrl_valid, dma_read_ctrl_data_index,'
                           'dma_read_ctrl_data_length,dma_read_ctrl_data_size,'
                           'dma_read_chnl_ready, dma_write_ctrl_valid,'
                           'dma_write_ctrl_data_index, dma_write_ctrl_data_length,'
                           'dma_write_ctrl_data_size, dma_write_chnl_valid,'
                           'dma_write_chnl_data, acc_done, debug')

  @staticmethod
  def gen_cosimulation(input_ports, output_ports, params):
    dut = "test_spikehard"
    work_dir = os.path.dirname(os.path.abspath(__file__))
    return myhdl_util.gen_cosimulation(dut, work_dir, params, input_ports, output_ports)

  @staticmethod
  def run_test(testcase, all_test_params, arch_params=None, delay_ns=10, co_test=None, generate=False):
    if isinstance(all_test_params, spikehard_named_params):
      return spikehard.run_test(testcase, [all_test_params], arch_params, delay_ns, co_test, generate)

    if co_test is None:
      if generate:
        co_test = spikehard.co_gen()
      else:
        co_test = spikehard.co_test()
    elif generate:
      raise ValueError("should not be generating")

    eq_params = ('dma_bus_width', 'dma_frame_header_word_width')
    any_params = ('output_core_x_coordinate', 'output_core_y_coordinate')
    geq_params = ('grid_dimension_x', 'grid_dimension_y', 'num_outputs',
                  'num_neurons', 'num_axons', 'num_ticks', 'num_weights',
                  'num_reset_modes', 'potential_width', 'weight_width',
                  'leak_width', 'threshold_width', 'max_dimension_x',
                  'max_dimension_y', 'router_buffer_depth',
                  'clock_cycles_per_tick')

    nullify_test_params = ('clock_cycles_per_tick',)

    if arch_params is None:
      def get_first_param(key):
        value = getattr(all_test_params[0], key)
        return value

      def get_greatest_param(key):
        value = getattr(all_test_params[0], key)
        for test_params in all_test_params:
          value = max(value, getattr(test_params, key))
        return value

      params_dict = {}
      for key in eq_params:
        params_dict[key] = get_first_param(key)
      for key in any_params:
        params_dict[key] = get_first_param(key)
      for key in geq_params:
        params_dict[key] = get_greatest_param(key)
      arch_params = spikehard_named_params(**params_dict)

    def check_param_eq(key):
      value = getattr(arch_params, key)
      for test_params in all_test_params:
        if getattr(test_params, key) != value:
          raise ValueError("{} must be the same for all tests".format(key))

    def check_param_geq(key):
      value = getattr(arch_params, key)
      for test_params in all_test_params:
        if value < getattr(test_params, key):
          raise ValueError("{} too small".format(key))

    for key in arch_params._fields:
      if key in geq_params:
        check_param_geq(key)
      elif key in eq_params:
        check_param_eq(key)
      elif key not in any_params:
        params_dict = arch_params._asdict()
        params_dict[key] = None
        arch_params = spikehard_named_params(**params_dict)

    for i in range(len(all_test_params)):
      params_dict = all_test_params[i]._asdict()
      for key in nullify_test_params:
        params_dict[key] = None
      all_test_params[i] = spikehard_named_params(**params_dict)

    # Initialising registers
    clk, rst, conf_done, dma_read_ctrl_ready, dma_read_chnl_valid, dma_write_ctrl_ready, dma_write_chnl_ready = myhdl_util.gen_signal(
      1, num_signals=7)
    conf_info_tx_size, conf_info_rx_size = myhdl_util.gen_signal(32, num_signals=2)
    dma_read_chnl_data = myhdl_util.gen_signal(arch_params.dma_bus_width)

    # Initialising wires
    dma_read_ctrl_valid, dma_read_chnl_ready, dma_write_ctrl_valid, dma_write_chnl_valid, acc_done = myhdl_util.gen_signal(
      1, num_signals=5)
    dma_read_ctrl_data_index, dma_read_ctrl_data_length, dma_write_ctrl_data_index, dma_write_ctrl_data_length, debug = myhdl_util.gen_signal(
      32, num_signals=5)
    dma_read_ctrl_data_size, dma_write_ctrl_data_size = myhdl_util.gen_signal(3, num_signals=2)
    dma_write_chnl_data = myhdl_util.gen_signal(arch_params.dma_bus_width)

    input_ports = spikehard.InputPorts(clk, rst, conf_info_tx_size, conf_info_rx_size, conf_done, dma_read_ctrl_ready,
                                       dma_read_chnl_valid, dma_read_chnl_data, dma_write_ctrl_ready, dma_write_chnl_ready)
    output_ports = spikehard.OutputPorts(dma_read_ctrl_valid, dma_read_ctrl_data_index, dma_read_ctrl_data_length, dma_read_ctrl_data_size, dma_read_chnl_ready,
                                         dma_write_ctrl_valid, dma_write_ctrl_data_index, dma_write_ctrl_data_length, dma_write_ctrl_data_size, dma_write_chnl_valid, dma_write_chnl_data, acc_done, debug)

    # Obtaining the cosimulation object
    dut = spikehard.gen_cosimulation(input_ports, output_ports, arch_params)

    @always(delay(delay_ns))
    def clock_gen():
      clk.next = not clk

    @always(clk.posedge)
    def check_errors():
      testcase.assertEqual(myhdl_util.to_int(output_ports.debug), 0,
                           "debug signal is non-zero, which most likely means the tick delay is too short")

    check = co_test(testcase, input_ports, output_ports, arch_params, all_test_params)

    sim = Simulation(dut, clock_gen, check_errors, check)
    sim.run()

  @staticmethod
  def timeout(params):
    return 2 * params.clock_cycles_per_tick

  @staticmethod
  def co_test():
    def test(testcase, input_ports, output_ports, arch_params, test_params, dfm, is_last_test):
      num_inputs_file = open(basic_test_util.num_inputs_filepath(test_params), 'r')
      num_outputs_file = open(basic_test_util.num_outputs_filepath(test_params), 'r')
      correct_file = open(basic_test_util.correct_filepath(test_params), 'r')

      ticks_sent = 0
      packet_count = 0
      all_packets_checked = False
      num_outputs_idx = test_params.tick_latency + 1
      expected_num_packets_received_this_tick = int(num_outputs_file.readline().rstrip())
      cur_tick_expected_packets = []
      for _ in range(expected_num_packets_received_this_tick):
        cur_tick_expected_packets.append(BitArray(bin=correct_file.readline().rstrip()).uint)

      def check_packet(tick_idx, actual_packet):
        nonlocal packet_count, all_packets_checked, num_outputs_idx, cur_tick_expected_packets, expected_num_packets_received_this_tick

        if tick_idx <= test_params.tick_latency or all_packets_checked:
          return

        if tick_idx != num_outputs_idx:
          testcase.assertTrue(len(cur_tick_expected_packets) == 0)
          testcase.logger.debug("correctly received {} packets in total for tick {}".format(
            expected_num_packets_received_this_tick, num_outputs_idx))
          while len(cur_tick_expected_packets) == 0:
            num_outputs_idx += 1
            expected_num_packets_received_this_tick = num_outputs_file.readline().rstrip()
            if expected_num_packets_received_this_tick == "":
              all_packets_checked = True
              return
            else:
              expected_num_packets_received_this_tick = int(expected_num_packets_received_this_tick)
              cur_tick_expected_packets = []
              for _ in range(expected_num_packets_received_this_tick):
                cur_tick_expected_packets.append(BitArray(bin=correct_file.readline().rstrip()).uint)

        testcase.assertEqual(num_outputs_idx, tick_idx)
        if test_params.relax_packet_ordering:
          if actual_packet in cur_tick_expected_packets:
            idx = cur_tick_expected_packets.index(actual_packet)
            if idx == 0:
              testcase.logger.debug('tick {}, packet {}: {} is correct'.format(
                tick_idx, packet_count, bin(actual_packet)))
            else:
              testcase.logger.debug(
                'tick {}, packet {}: {} is correct but received out-of-order'.format(tick_idx, packet_count, bin(actual_packet)))
            cur_tick_expected_packets.pop(idx)
          else:
            testcase.logger.error('tick {}, packet {}: actual is {}, but was not expected during this tick'.format(
              tick_idx, packet_count, bin(actual_packet)))
            testcase.assertTrue(False, 'tick {}, packet {}: actual is {}, but was not expected during this tick'.format(
              tick_idx, packet_count, bin(actual_packet)))
        else:
          correct_packet = cur_tick_expected_packets.pop(0)
          if actual_packet == correct_packet:
            testcase.logger.debug('tick {}, packet {}: {} is correct'.format(
              tick_idx, packet_count, bin(actual_packet)))
          else:
            testcase.logger.error('tick {}, packet {}: actual is {}, correct is {}'.format(
              tick_idx, packet_count, bin(actual_packet), bin(correct_packet)))
            testcase.assertTrue(False, 'tick {}, packet {}: actual is {}, correct is {}'.format(
              tick_idx, packet_count, bin(actual_packet), bin(correct_packet)))

        # Checking if there are more packets to process
        next_correct_packet = file_util.peek_line(correct_file)
        if next_correct_packet == '':
          testcase.logger.debug('test succeeded: all packets correct')
          all_packets_checked = True

        packet_count = packet_count + 1

      def read_dma(fun, args):
        if fun is None:
          return

        while True:
          if myhdl_util.to_int(output_ports.dma_read_ctrl_valid):
            yield from fun(*args)
            break
          elif myhdl_util.to_int(output_ports.dma_write_ctrl_valid):
            yield from dfm.out_frame(check_packet=check_packet)
          else:
            yield input_ports.clk.posedge

      def read_dma_frame(header, payload=None, header_args=[], payload_args=[], tick_delay=1):
        nonlocal ticks_sent, all_packets_checked
        if tick_delay:
          yield from read_dma(dfm.tick, (tick_delay,))
          ticks_sent += tick_delay
          if (test_params.num_ticks_to_check is not None) and (ticks_sent >= test_params.num_ticks_to_check):
            all_packets_checked = True
          if header == dfm.noop:
            return

        yield from read_dma(header, header_args)
        yield from read_dma(payload, payload_args)

      def send_model_data():
        output_core = test_params.output_core_x_coordinate + test_params.output_core_y_coordinate * test_params.grid_dimension_x

        yield from read_dma_frame(header=dfm.reset, tick_delay=0)

        for y in range(test_params.grid_dimension_y):
          for x in range(test_params.grid_dimension_x):
            core_idx = x + y * test_params.grid_dimension_x
            if core_idx == output_core:
              continue

            core_idx = str(core_idx).zfill(len(str(test_params.grid_dimension_x * test_params.grid_dimension_y - 1)))

            def gen_path(s):
              return os.path.join(test_params.memory_filepath, "{}_{}.mem".format(s, core_idx))

            tc_path = gen_path("tc")
            csram_path = gen_path("csram")

            if not os.path.exists(tc_path) or not os.path.exists(csram_path):
              continue

            yield from dfm.core_data(tc_path, csram_path, x, y)

      # Sending the input data
      first_in_packets = True
      has_input_data = True

      all_packets = model_util(arch_params, test_params).parse_input_packets()
      all_packets_idx = 0

      def send_packets_for_current_tick():
        nonlocal has_input_data, first_in_packets, all_packets_idx

        if not has_input_data:
          yield from read_dma_frame(header=dfm.noop)
          return

        num_inputs = num_inputs_file.readline().rstrip()
        if num_inputs == '':
          testcase.logger.debug("done sending inputs")
          has_input_data = False
          yield from read_dma_frame(header=dfm.noop)
          return

        packets = []
        for _ in range(int(num_inputs)):
          packets.append(all_packets[all_packets_idx])
          all_packets_idx += 1

        yield from read_dma_frame(header=dfm.in_packets_header,
                                  payload=dfm.in_packets_payload,
                                  header_args=[len(packets)],
                                  payload_args=[packets],
                                  tick_delay=int((not first_in_packets)))

        first_in_packets = False

      yield from send_model_data()

      while not all_packets_checked:
        yield from send_packets_for_current_tick()

      # Ensure that we have actually received some kind of output.
      testcase.assertTrue(packet_count > 0)

      # Send terminate signal.
      yield from read_dma_frame(header=dfm.terminate, tick_delay=0)

      # Wait for accelerator to terminate.
      timer = 0
      done = False
      while not done or not dfm.accelerator_terminated:
        if myhdl_util.to_int(output_ports.acc_done):
          done = True

        if myhdl_util.to_int(output_ports.dma_write_ctrl_valid):
          yield from dfm.out_frame(check_packet=check_packet)
        else:
          yield input_ports.clk.posedge

        if dfm.timeout is not None:
          timer += 1
          testcase.assertTrue(timer < dfm.timeout)

      if is_last_test:
        raise StopSimulation
      else:
        yield input_ports.clk.posedge
        input_ports.rst.next = 0
        yield input_ports.clk.posedge
        input_ports.rst.next = 1
        for _ in range(10000):
          yield input_ports.clk.posedge

    def tests(testcase, input_ports, output_ports, arch_params, all_test_params):
      from dma_frame_manager import dma_frame_manager
      dfm = dma_frame_manager(testcase, input_ports, output_ports, arch_params)

      # Initialise accelerator
      tx_size = 2 ** 31
      rx_size = 2 ** 31
      yield from myhdl_util.initialise_accelerator(testcase, input_ports, output_ports, tx_size, rx_size)

      for idx, test_params in enumerate(all_test_params):
        dfm.test_params = test_params
        if idx > 0:
          dfm.read_offset = 0
          dfm.write_offset = (2 ** 31) / (dfm.dma_bus_width >> 3)
          yield input_ports.clk.posedge
          input_ports.conf_info_tx_size.next = tx_size
          input_ports.conf_info_rx_size.next = rx_size
          input_ports.conf_done.next = 1
          yield input_ports.clk.posedge
          input_ports.conf_done.next = 0
          yield input_ports.clk.posedge

        yield from test(testcase,
                        input_ports, output_ports,
                        arch_params, test_params,
                        dfm,
                        is_last_test=((idx + 1) == len(all_test_params)))

    return tests

  @staticmethod
  def co_gen():
    def test(testcase, input_ports, output_ports, arch_params, test_params, dfm, is_last_test):
      num_inputs_file = open(basic_test_util.num_inputs_filepath(test_params), 'r')
      num_outputs_file = open(basic_test_util.num_outputs_filepath(test_params), 'w')
      correct_file = open(basic_test_util.correct_filepath(test_params), 'w')

      ticks_sent = 0
      packet_count = 0
      all_packets_checked = False
      num_outputs_idx = test_params.tick_latency + 1
      last_tick_generated_packet = test_params.tick_latency
      this_tick_packets = []

      def check_packet(tick_idx, actual_packet):
        nonlocal packet_count, all_packets_checked, num_outputs_idx, this_tick_packets, last_tick_generated_packet

        if tick_idx <= test_params.tick_latency or all_packets_checked:
          return

        if tick_idx != num_outputs_idx:
          if not len(this_tick_packets) or (tick_idx > (num_outputs_idx + 1)):
            print('no more packets to receive [1]')
            all_packets_checked = True
            return

          num_outputs_idx += 1
          num_outputs_file.write(f"{len(this_tick_packets)}\n")
          this_tick_packets = sorted(this_tick_packets)
          for p in this_tick_packets:
            correct_file.write(f"{BitArray(uint=p, length=test_params.num_outputs.bit_length()-1).bin}\n")
          this_tick_packets.clear()
          num_outputs_file.flush()
          correct_file.flush()

        print('tick {}, packet {}: {}'.format(tick_idx, packet_count, BitArray(
          uint=actual_packet, length=test_params.num_outputs.bit_length() - 1).bin))
        this_tick_packets.append(actual_packet)
        packet_count = packet_count + 1
        last_tick_generated_packet = tick_idx

      def read_dma(fun, args):
        if fun is None:
          return

        while True:
          if myhdl_util.to_int(output_ports.dma_read_ctrl_valid):
            yield from fun(*args)
            break
          elif myhdl_util.to_int(output_ports.dma_write_ctrl_valid):
            yield from dfm.out_frame(check_packet=check_packet)
          else:
            yield input_ports.clk.posedge

      def read_dma_frame(header, payload=None, header_args=[], payload_args=[], tick_delay=1):
        nonlocal ticks_sent, all_packets_checked
        if tick_delay:
          print(f"tick: {ticks_sent}")
          yield from read_dma(dfm.tick, (tick_delay,))
          ticks_sent += tick_delay
          if (last_tick_generated_packet + 3) < ticks_sent:
            print('no more packets to receive [2]')
            all_packets_checked = True
          if header == dfm.noop:
            return

        yield from read_dma(header, header_args)
        yield from read_dma(payload, payload_args)

      def send_model_data():
        output_core = test_params.output_core_x_coordinate + test_params.output_core_y_coordinate * test_params.grid_dimension_x

        yield from read_dma_frame(header=dfm.reset, tick_delay=0)

        for y in range(test_params.grid_dimension_y):
          for x in range(test_params.grid_dimension_x):
            core_idx = x + y * test_params.grid_dimension_x
            if core_idx == output_core:
              continue

            core_idx = str(core_idx).zfill(len(str(test_params.grid_dimension_x * test_params.grid_dimension_y - 1)))

            def gen_path(s):
              return os.path.join(test_params.memory_filepath, "{}_{}.mem".format(s, core_idx))

            tc_path = gen_path("tc")
            csram_path = gen_path("csram")

            if not os.path.exists(tc_path) or not os.path.exists(csram_path):
              continue

            yield from dfm.core_data(tc_path, csram_path, x, y)

      # Sending the input data
      first_in_packets = True
      has_input_data = True

      all_packets = model_util(arch_params, test_params).parse_input_packets()
      all_packets_idx = 0

      def send_packets_for_current_tick():
        nonlocal has_input_data, first_in_packets, all_packets_idx

        if not has_input_data:
          yield from read_dma_frame(header=dfm.noop)
          return

        num_inputs = num_inputs_file.readline().rstrip()
        if num_inputs == '':
          print("done sending inputs")
          has_input_data = False
          yield from read_dma_frame(header=dfm.noop)
          return

        packets = []
        for _ in range(int(num_inputs)):
          packets.append(all_packets[all_packets_idx])
          all_packets_idx += 1

        yield from read_dma_frame(header=dfm.in_packets_header,
                                  payload=dfm.in_packets_payload,
                                  header_args=[len(packets)],
                                  payload_args=[packets],
                                  tick_delay=int((not first_in_packets)))

        first_in_packets = False

      yield from send_model_data()

      while not all_packets_checked:
        yield from send_packets_for_current_tick()

      # Ensure that we have actually received some kind of output.
      testcase.assertTrue(packet_count > 0)

      # Send terminate signal.
      yield from read_dma_frame(header=dfm.terminate, tick_delay=0)

      # Wait for accelerator to terminate.
      timer = 0
      done = False
      while not done or not dfm.accelerator_terminated:
        if myhdl_util.to_int(output_ports.acc_done):
          done = True

        if myhdl_util.to_int(output_ports.dma_write_ctrl_valid):
          yield from dfm.out_frame(check_packet=check_packet)
        else:
          yield input_ports.clk.posedge

        if dfm.timeout is not None:
          timer += 1
          testcase.assertTrue(timer < dfm.timeout)

      correct_file.close()
      num_outputs_file.close()
      num_inputs_file.close()

      if is_last_test:
        raise StopSimulation
      else:
        yield input_ports.clk.posedge
        input_ports.rst.next = 0
        yield input_ports.clk.posedge
        input_ports.rst.next = 1
        for _ in range(10000):
          yield input_ports.clk.posedge

    def tests(testcase, input_ports, output_ports, arch_params, all_test_params):
      from dma_frame_manager import dma_frame_manager
      dfm = dma_frame_manager(testcase, input_ports, output_ports, arch_params)

      # Initialise accelerator
      tx_size = 2 ** 31
      rx_size = 2 ** 31
      yield from myhdl_util.initialise_accelerator(testcase, input_ports, output_ports, tx_size, rx_size)

      for idx, test_params in enumerate(all_test_params):
        dfm.test_params = test_params
        if idx > 0:
          dfm.read_offset = 0
          dfm.write_offset = (2 ** 31) / (dfm.dma_bus_width >> 3)
          yield input_ports.clk.posedge
          input_ports.conf_info_tx_size.next = tx_size
          input_ports.conf_info_rx_size.next = rx_size
          input_ports.conf_done.next = 1
          yield input_ports.clk.posedge
          input_ports.conf_done.next = 0
          yield input_ports.clk.posedge

        yield from test(testcase,
                        input_ports, output_ports,
                        arch_params, test_params,
                        dfm,
                        is_last_test=((idx + 1) == len(all_test_params)))

    return tests
