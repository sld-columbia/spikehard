#ifndef SPIKEHARD_SW_LIB_UTIL_H_INCLUDED
#define SPIKEHARD_SW_LIB_UTIL_H_INCLUDED

#if defined(__unix__)

#include "test_bench.h"
#include "cfg.h"

struct spikehard_stats {
  float invocation_overhead;
  float model_loading_overhead;
  float latency_excl_overhead;
  unsigned throughput_batch_size;
  float throughput_total_time;
  float throughput;
  bool batched;
};

typedef struct spikehard_stats spikehard_stats_t;

void su_print_stats(spikehard_stats_t* stats);
unsigned long long su_exec_time_ns_for_cfg(int cfg);
float su_exec_time_ms_for_cfg(int cfg);
unsigned long long su_exec_time_ns();
float su_exec_time_ms();
int su_measure_perf(spikehard_stats_t* const stats,
                    test_bench_t const* const tb,
                    const unsigned latency_num_samples,
                    const unsigned throughput_num_samples,
                    const unsigned invocation_overhead_num_samples,
                    const unsigned model_loading_overhead_num_samples);

#endif // defined(__unix__)

#include "util_impl.h"

#endif // SPIKEHARD_SW_LIB_UTIL_H_INCLUDED