#include "spikehard_architecture.h"

bool tb_run_single_model(const test_bench_t* tb, int batch_size) {
  if (batch_size < 1) {
    batch_size = 1;
  }

  struct spikehard_manager mng;
  {
    size_t tx_size = sizeof(uint64_t) * 262144;
    size_t rx_size = (256 + sizeof(uint64_t) * 2) * (tb->num_ticks_to_check + 1) * 3 * batch_size;
    if (!sm_init(&mng, ACC_COH_NONE, tx_size, rx_size)) {
      printf("[SW][test_bench] failed to initialise accelerator\n");
      printf("[SW][test_bench] FAILED\n");
      return true;
    }
  }

  sm_tx_reset(&mng, true, true, true);
  for (unsigned i = 0; i < tb->len_cores; ++i) {
    sm_tx_core_data(&mng, &tb->cores[i]);
  }

  int batch_idx;
  for (batch_idx = 0; batch_idx < batch_size; ++batch_idx) {
    if (tb->num_ticks_to_check > 0) {
      unsigned num_ticks = 0;
      {
        unsigned offset = 0;
        for (unsigned i = 0; i < tb->len_num_inputs; ++i) {
          sm_tx_packets(&mng, &tb->inputs[offset], tb->num_inputs[i]);
          offset += tb->num_inputs[i];

          num_ticks += 1;
          sm_tx_tick(&mng, 1, tb->clock_cycles_per_tick);
          if (num_ticks >= tb->num_ticks_to_check) {
            break;
          }
        }
      }
      for (; num_ticks < (tb->num_ticks_to_check + 1); ++num_ticks) {
        sm_tx_tick(&mng, 1, tb->clock_cycles_per_tick);
      }
    }
    if (batch_size > 1 && batch_idx != batch_size - 1) {
      sm_tx_reset(&mng, true, false, true);
    }
  }
  sm_tx_terminate(&mng);

  sm_run(&mng);

  bool done                          = false;
  batch_idx                          = 0;
  uint32_t prev_tick_idx             = 1;
  uint32_t cur_tick_base_idx         = 0;
  uint32_t cur_tick_packets_received = 0;
  uint32_t total_packets_received    = 0;
  uint32_t num_outputs_idx           = tb->tick_latency + 1;
  packet_t packets[NUM_OUTPUTS];
  bool packet_received[NUM_OUTPUTS];
  for (int i = 0; i < NUM_OUTPUTS; ++i) {
    packet_received[i] = false;
  }
  uint16_t length;
  uint16_t tick_idx;
  while (!mng.error && !done) {
    if (sm_rx_frame_type(&mng) == DMA_FRAME_TYPE_TERMINATE) {
      done = true;
      break;
    }

    sm_rx_peek_packets(&mng, &length, &tick_idx);
    if (mng.error) {
      break;
    }

    if (tick_idx == 0 && batch_idx < batch_size) { // start of new batch
      printf("[SW][test_bench] starting batch: %d\n", batch_idx);
      cur_tick_base_idx         = 0;
      cur_tick_packets_received = 0;
      total_packets_received    = 0;
      num_outputs_idx           = tb->tick_latency + 1;
      for (int i = 0; i < NUM_OUTPUTS; ++i) {
        packet_received[i] = false;
      }
      if (prev_tick_idx != 0) {
        batch_idx += 1;
      }
    }
    prev_tick_idx = tick_idx;

    if (tick_idx >= tb->num_ticks_to_check) {
      printf("[SW][test_bench] waiting for next batch...\n");
      done = (batch_size == batch_idx);
      continue;
    }

    sm_rx_packets(&mng, packets, NUM_OUTPUTS, &length, &tick_idx);
    if (mng.error) {
      break;
    }

    if (tick_idx <= tb->tick_latency) {
      printf("[SW][test_bench] discarding %u packets received at tick %u\n", (unsigned)length, (unsigned)tick_idx);
      continue;
    }

    if (tick_idx == num_outputs_idx) {
      cur_tick_packets_received += length;
      if (cur_tick_packets_received > tb->num_outputs[num_outputs_idx - (tb->tick_latency + 1)]) {
        printf("[SW][test_bench][error] tick %u, received at least %u packets, expected %u packets\n",
               (unsigned)num_outputs_idx, (unsigned)cur_tick_packets_received,
               (unsigned)tb->num_outputs[num_outputs_idx - (tb->tick_latency + 1)]);
        mng.error = true;
        break;
      }
    } else if (cur_tick_packets_received != tb->num_outputs[num_outputs_idx - (tb->tick_latency + 1)]) {
      printf("[SW][test_bench][error] tick %u, received %u packets, expected %u packets\n", (unsigned)num_outputs_idx,
             (unsigned)cur_tick_packets_received, (unsigned)tb->num_outputs[num_outputs_idx - (tb->tick_latency + 1)]);
      mng.error = true;
      break;
    } else {
      printf("[SW][test_bench] correctly received %u packets in total for tick %u\n",
             (unsigned)cur_tick_packets_received, (unsigned)num_outputs_idx);

      num_outputs_idx += 1;
      cur_tick_base_idx += cur_tick_packets_received;
      cur_tick_packets_received = length;
      for (int i = 0; i < NUM_OUTPUTS; ++i) {
        packet_received[i] = false;
      }

      if (num_outputs_idx != tick_idx) {
        printf("[SW][test_bench][error] expected tick %u, actually %u\n", (unsigned)num_outputs_idx,
               (unsigned)tick_idx);
        mng.error = true;
        break;
      } else if (((num_outputs_idx - (tb->tick_latency + 1)) >= tb->len_num_outputs)) {
        done = (batch_size == batch_idx);
        continue;
      }
    }

    for (uint16_t i = 0; i < length; ++i) {
      if (total_packets_received == tb->len_outputs) {
        done = (batch_size == batch_idx);
        break;
      }

      total_packets_received += 1;
      bool valid        = false;
      bool received_ooo = false;
      for (int j = 0; j < tb->num_outputs[num_outputs_idx - (tb->tick_latency + 1)]; ++j) {
        if (valid && packet_received[j]) {
          received_ooo = true;
          break;
        } else if (packets[i] == tb->outputs[j + cur_tick_base_idx] && !packet_received[j]) {
          packet_received[j] = true;
          valid              = true;
          if (received_ooo) {
            break;
          }
        } else if (!packet_received[j]) {
          received_ooo = true;
        }
      }
      if (valid) {
        if (received_ooo) {
          printf("[SW][test_bench] tick %u, packet %u: %u is correct but received out-of-order\n", (unsigned)tick_idx,
                 (unsigned)total_packets_received, (unsigned)packets[i]);
        } else {
          printf("[SW][test_bench] tick %u, packet %u: %u is correct\n", (unsigned)tick_idx,
                 (unsigned)total_packets_received, (unsigned)packets[i]);
        }
      } else {
        printf("[SW][test_bench][error] tick %u, packet %u: %u was not expected this tick\n", (unsigned)tick_idx,
               (unsigned)total_packets_received, (unsigned)packets[i]);
        mng.error = true;
        break;
      }

      if (total_packets_received == tb->len_outputs) {
        done = (batch_size == batch_idx);
        break;
      }
    }
  }

  if (total_packets_received == 0) {
    printf("[SW][test_bench][error] no packets were received\n");
    mng.error = true;
  }

  while (sm_rx_frame_type(&mng) != DMA_FRAME_TYPE_TERMINATE) {
    sm_rx_packets(&mng, packets, NUM_OUTPUTS, &length, &tick_idx);
  }

  const uint32_t error_flags = sm_rx_error_flags(&mng);
  if (error_flags) {
    printf("[SW][test_bench][failure] error_flags: %d\n", error_flags);
    mng.error = true;
  } else {
    printf("[SW][test_bench] error_flags: %d\n", error_flags);
  }

  printf("tx size: %d\n", mng.tx_offset);
  printf("rx size: %ld\n", mng.rx_offset - (mng.tx_size / sizeof(uint32_t)));

  sm_destroy(&mng);

  if (done && !mng.error) {
    printf("[SW][test_bench] PASSED\n");
  } else {
    printf("[SW][test_bench] FAILED\n");
  }

  return mng.error;
}