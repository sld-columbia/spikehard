#ifndef SPIKEHARD_SW_LIB_SPIKEHARD_MANAGER_H_INCLUDED
#define SPIKEHARD_SW_LIB_SPIKEHARD_MANAGER_H_INCLUDED

#include <stdbool.h>
#include <stdio.h>
#ifndef __riscv
#include <stdlib.h>
#endif

#if defined(__unix__)
#include "cfg.h"
#include "libesp.h"
#else
#include <esp_accelerator.h>
#include <esp_probe.h>
#include <fixed_point.h>
#endif

#include "spikehard_architecture.h"

typedef uint32_t packet_t;

struct spikehard_manager {
#if !defined(__unix__)
  struct esp_device* dev;
  unsigned** ptable;
#endif
  uint32_t* mem;
  uint32_t tx_offset;
  uint32_t rx_offset;

  size_t mem_size;
  size_t tx_size;
  size_t rx_size;

  bool error;
};

typedef struct spikehard_manager spikehard_manager_t;

struct core_data {
  uint32_t x;
  uint32_t y;
  const uint64_t* tc_data;
  const uint64_t* csram_data;
  uint32_t tc_data_length;
  uint32_t csram_data_length;
};

typedef struct core_data core_data_t;

bool sm_init(spikehard_manager_t* mng, unsigned coherence, size_t tx_size, size_t rx_size);
void sm_run(spikehard_manager_t* mng);
void sm_destroy(spikehard_manager_t* mng);

void sm_tx_terminate(spikehard_manager_t* mng);
void sm_tx_tick(spikehard_manager_t* mng, uint16_t amount, uint64_t delay);
void sm_tx_reset(spikehard_manager_t* mng, bool reset_network, bool reset_model, bool reset_tick_idx);
void sm_tx_packets(spikehard_manager_t* mng, const packet_t* packets, uint32_t length);
void sm_tx_core_data(spikehard_manager_t* mng, const core_data_t* core_data);

uint32_t sm_rx_frame_type(spikehard_manager_t* mng);
uint32_t sm_rx_error_flags(spikehard_manager_t* mng);
void sm_rx_peak_packets(spikehard_manager_t* mng, uint16_t* length, uint16_t* tick_idx);
void sm_rx_packets(spikehard_manager_t* mng, packet_t* packets, uint16_t max_length, uint16_t* length,
                   uint16_t* tick_idx);

#include "spikehard_manager_impl.h"

#endif // SPIKEHARD_SW_LIB_SPIKEHARD_MANAGER_H_INCLUDED