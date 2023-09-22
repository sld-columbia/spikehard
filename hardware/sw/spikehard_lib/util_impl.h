#if defined(__unix__)

unsigned long long su_exec_time_ns_for_cfg(int cfg) {
  return cfg_000[cfg].hw_ns;
}

float su_exec_time_ms_for_cfg(int cfg) {
  return ((float)su_exec_time_ns_for_cfg(cfg)) / 1000000.0f;
}

unsigned long long su_exec_time_ns() {
  return su_exec_time_ns_for_cfg(0);
}

float su_exec_time_ms() {
  return su_exec_time_ms_for_cfg(0);
}

static int su_perf_run_(const test_bench_t* tb, const bool load_model,
                        const bool computing_latency, const unsigned batch_size, const bool batched) {
  if (computing_latency) {
    test_bench_t tmp_tb = *tb;
    if (batched) {
      tmp_tb.len_num_inputs     = 1;
      tmp_tb.num_ticks_to_check = tmp_tb.tick_latency + 2;
    } else {
      tmp_tb.num_ticks_to_check = tmp_tb.len_num_outputs + tmp_tb.tick_latency + 2;
    }
    return tb_run_single_model(&tmp_tb, 0);
  } else if (batch_size) {
    if (!batched) {
      printf("[SW][util][error] batch_size can only be specified if using batched model\n");
      return 1;
    }
    if ((batch_size % tb->len_num_inputs) != 0) {
      printf("[SW][util][error] batch_size must be a multiple of len_num_inputs\n");
      return 1;
    }
    if (tb->len_num_inputs != tb->len_num_outputs) {
      printf("[SW][util][error] len_num_inputs must be equal to len_num_outputs\n");
      return 1;
    }

    int duplication_factor = (batch_size / tb->len_num_inputs);
    test_bench_t tmp_tb    = *tb;

    tmp_tb.len_num_inputs = batch_size;
    tmp_tb.num_inputs     = (uint32_t*)malloc(sizeof(uint32_t) * tmp_tb.len_num_inputs);
    for (int i = 0; i < duplication_factor; ++i) {
      for (int j = 0; j < tb->len_num_inputs; ++j) {
        tmp_tb.num_inputs[i * tb->len_num_inputs + j] = tb->num_inputs[j];
      }
    }

    tmp_tb.len_inputs = tb->len_inputs * duplication_factor;
    tmp_tb.inputs     = (packet_t*)malloc(sizeof(packet_t) * tmp_tb.len_inputs);
    for (int i = 0; i < duplication_factor; ++i) {
      for (int j = 0; j < tb->len_inputs; ++j) {
        tmp_tb.inputs[i * tb->len_inputs + j] = tb->inputs[j];
      }
    }

    tmp_tb.len_num_outputs = batch_size;
    tmp_tb.num_outputs     = (uint32_t*)malloc(sizeof(uint32_t) * tmp_tb.len_num_outputs);
    for (int i = 0; i < duplication_factor; ++i) {
      for (int j = 0; j < tb->len_num_outputs; ++j) {
        tmp_tb.num_outputs[i * tb->len_num_outputs + j] = tb->num_outputs[j];
      }
    }

    tmp_tb.len_outputs = tb->len_outputs * duplication_factor;
    tmp_tb.outputs     = (packet_t*)malloc(sizeof(packet_t) * tmp_tb.len_outputs);
    for (int i = 0; i < duplication_factor; ++i) {
      for (int j = 0; j < tb->len_outputs; ++j) {
        tmp_tb.outputs[i * tb->len_outputs + j] = tb->outputs[j];
      }
    }

    tmp_tb.num_ticks_to_check = batch_size + tmp_tb.tick_latency + 1;
    int retval                = tb_run_single_model(&tmp_tb, 0);
    free(tmp_tb.num_inputs);
    free(tmp_tb.num_outputs);
    free(tmp_tb.inputs);
    free(tmp_tb.outputs);
    return retval;
  }

  struct spikehard_manager mng;
  {
    uint32_t tx_size = sizeof(uint64_t) * 131072;
    uint32_t rx_size = (256 + sizeof(uint64_t) * 2) * (tb->num_ticks_to_check + 1) * 3;
    if (!sm_init(&mng, ACC_COH_NONE, tx_size, rx_size)) {
      printf("[SW][util] failed to initialise accelerator for invocation overhead run\n");
      return 1;
    }
  }

  if (load_model) {
    sm_tx_reset(&mng, true, true, true);
    for (unsigned i = 0; i < tb->len_cores; ++i) {
      sm_tx_core_data(&mng, &tb->cores[i]);
    }
  }

  sm_tx_terminate(&mng);
  sm_run(&mng);
  sm_destroy(&mng);
  return 0;
}

int su_measure_perf(spikehard_stats_t* const stats, test_bench_t const* const tb, const unsigned latency_num_samples,
                    const unsigned throughput_num_samples, const unsigned invocation_overhead_num_samples,
                    const unsigned model_loading_overhead_num_samples) {
  // invocation overhead: run accelerator with a simple terminate frame
  stats->invocation_overhead = 0;
  if (invocation_overhead_num_samples) {
    for (int i = 0; i < invocation_overhead_num_samples; ++i) {
      if (su_perf_run_(tb, false, false, 0, stats->batched)) {
        return 1;
      }
      float total_time          = su_exec_time_ms();
      float invocation_overhead = total_time;
      stats->invocation_overhead += invocation_overhead;
      printf("[SW][util] (%u/%u) invocation overhead is: %f ms\n", i + 1, invocation_overhead_num_samples,
             invocation_overhead);
    }
    stats->invocation_overhead /= invocation_overhead_num_samples;
  }
  printf("[SW][util] average invocation overhead over %u runs is: %f ms\n", invocation_overhead_num_samples,
         stats->invocation_overhead);

  // model loading overhead: terminate immediately after loading and get difference from invocation overhead.
  stats->model_loading_overhead = 0;
  if (model_loading_overhead_num_samples) {
    for (int i = 0; i < model_loading_overhead_num_samples; ++i) {
      if (su_perf_run_(tb, true, false, 0, stats->batched)) {
        return 1;
      }
      float total_time             = su_exec_time_ms();
      float model_loading_overhead = total_time - stats->invocation_overhead;
      stats->model_loading_overhead += model_loading_overhead;
      printf("[SW][util] (%u/%u) model loading overhead is: %f ms\n", i + 1, model_loading_overhead_num_samples,
             model_loading_overhead);
    }
    stats->model_loading_overhead /= model_loading_overhead_num_samples;
  }
  printf("[SW][util] average model loading overhead over %u runs is: %f ms\n", model_loading_overhead_num_samples,
         stats->model_loading_overhead);

  // latency: send first batch of inputs, if MNIST should wait until receive all
  // packets on tick idx 2. If VMM should wait until entire testbench processed.
  stats->latency_excl_overhead = 0;
  for (int i = 0; i < latency_num_samples; ++i) {
    if (su_perf_run_(tb, true, true, 0, stats->batched)) {
      return 1;
    }
    float total_time            = su_exec_time_ms();
    float latency_excl_overhead = total_time - stats->invocation_overhead - stats->model_loading_overhead;
    stats->latency_excl_overhead += latency_excl_overhead;
    printf("[SW][util] (%u/%u) latency excl. overhead is: %f ms\n", i + 1, latency_num_samples, latency_excl_overhead);
  }
  stats->latency_excl_overhead /= latency_num_samples;
  printf("[SW][util] average latency excl. overhead over %u runs is: %f ms\n", latency_num_samples,
         stats->latency_excl_overhead);

  // throughput: only for MNIST, duplicate inputs and take average.
  stats->throughput            = 0;
  stats->throughput_total_time = 0;
  if (!stats->batched) {
    stats->throughput_batch_size = 0;
    return 0;
  }
  stats->throughput_batch_size = tb->len_num_inputs * 20;
  for (int i = 0; i < throughput_num_samples; ++i) {
    if (su_perf_run_(tb, true, false, stats->throughput_batch_size, stats->batched)) {
      return 1;
    }
    float total_time = su_exec_time_ms();
    float throughput = (float)stats->throughput_batch_size / total_time;
    stats->throughput += throughput;
    stats->throughput_total_time += total_time;
    printf("[SW][util] (%u/%u) total time is: %f ms\n", i + 1, throughput_num_samples, total_time);
    printf("[SW][util] (%u/%u) throughput is: %f ops/s\n", i + 1, throughput_num_samples, throughput * 1000);
  }
  stats->throughput_total_time /= throughput_num_samples;
  stats->throughput /= throughput_num_samples;
  stats->throughput *= 1000;
  printf("[SW][util] (batch size = %u) average total time over %u runs is: %f ms\n", stats->throughput_batch_size,
         throughput_num_samples, stats->throughput_total_time);
  printf("[SW][util] (batch size = %u) average throughput over %u runs is: %f ops/s\n", stats->throughput_batch_size,
         throughput_num_samples, stats->throughput);
  return 0;
}

void su_print_stats(spikehard_stats_t* stats) {
  printf("[SW][util] average invocation overhead: %f ms\n", stats->invocation_overhead);
  printf("[SW][util] average model loading overhead: %f ms\n", stats->model_loading_overhead);
  printf("[SW][util] average latency excl. overhead: %f ms\n", stats->latency_excl_overhead);
  if (stats->batched) {
    printf("[SW][util] average total time: %f ms\n", stats->throughput_total_time);
    printf("[SW][util] average throughput: %f ops/s\n", stats->throughput);
    printf("[SW][util] [%f, %f, %f, %f, %f, %u]\n", stats->invocation_overhead, stats->model_loading_overhead,
           stats->latency_excl_overhead, stats->throughput_total_time, stats->throughput, stats->throughput_batch_size);
  } else {
    printf("[SW][util] [%f, %f, %f]\n", stats->invocation_overhead, stats->model_loading_overhead,
           stats->latency_excl_overhead);
  }
}

#endif // defined(__unix__)