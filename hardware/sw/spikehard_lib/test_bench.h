#ifndef SPIKEHARD_SW_LIB_TEST_BENCH_H_INCLUDED
#define SPIKEHARD_SW_LIB_TEST_BENCH_H_INCLUDED

#include "spikehard_manager.h"

struct test_bench {
  core_data_t* cores;
  uint32_t* num_inputs;
  uint32_t* num_outputs;
  packet_t* inputs;
  packet_t* outputs;
  uint32_t len_cores;
  uint32_t len_num_inputs;
  uint32_t len_num_outputs;
  uint32_t len_inputs;
  uint32_t len_outputs;
  uint32_t num_ticks_to_check;
  uint32_t tick_latency;
  uint32_t clock_cycles_per_tick;
  bool relax_packet_ordering;
};

typedef struct test_bench test_bench_t;

bool tb_run_single_model(const test_bench_t* tb, int batch_size);

#include "test_bench_impl.h"

#endif // SPIKEHARD_SW_LIB_TEST_BENCH_H_INCLUDED