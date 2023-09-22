#include "../spikehard_lib/spikehard_manager.h"
#include "../spikehard_lib/test_bench.h"
#include "../spikehard_model/vmm_o.h"

int main(int argc, char * argv[]) {
  return tb_run_single_model(&g_vmm_o_test_bench, 0);
}
