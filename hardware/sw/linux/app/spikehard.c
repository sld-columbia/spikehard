#include "spikehard_lib/spikehard_manager.h"
#include "spikehard_lib/test_bench.h"
#include "spikehard_lib/util.h"
#include "spikehard_model/vmm_o.h"

static int get_optional_iarg_(int argc, char** argv, char const* flag, const int default_val) {
  for (int i = 1; i < argc; ++i) {
    if (!strcmp(argv[i - 1], flag)) {
      return atoi(argv[i]);
    }
  }
  return default_val;
}

int main(int argc, char** argv) {
  const unsigned latency_num_samples = get_optional_iarg_(argc, argv, "-l", 1);
  const unsigned throughput_num_samples = get_optional_iarg_(argc, argv, "-t", 1);
  const unsigned invocation_overhead_num_samples = get_optional_iarg_(argc, argv, "-i", 0);
  const unsigned model_loading_overhead_num_samples = get_optional_iarg_(argc, argv, "-m", 0);
  spikehard_stats_t stats_vmm_o;
  stats_vmm_o.batched = false;
  g_vmm_o_test_bench.clock_cycles_per_tick = get_optional_iarg_(argc, argv, "-c", g_vmm_o_test_bench.clock_cycles_per_tick);
  if (su_measure_perf(&stats_vmm_o, &g_vmm_o_test_bench, latency_num_samples, throughput_num_samples, invocation_overhead_num_samples, model_loading_overhead_num_samples)) { return 1; }
  printf("[SW] stats for vmm_o model:\n");
  su_print_stats(&stats_vmm_o);
  printf("[SW][util] latencies (vmm_o): [%f, 32, 32]\n", (stats_vmm_o.invocation_overhead+stats_vmm_o.model_loading_overhead+stats_vmm_o.latency_excl_overhead));
  return 0;
}
