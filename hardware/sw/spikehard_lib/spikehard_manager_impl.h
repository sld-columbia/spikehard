#if !defined(__unix__)
/* Size of the contiguous chunks for scatter/gather */
#define CHUNK_SHIFT 20
#define CHUNK_SIZE  BIT(CHUNK_SHIFT)
#define NCHUNK(_sz) ((_sz % CHUNK_SIZE == 0) ? (_sz / CHUNK_SIZE) : (_sz / CHUNK_SIZE) + 1)

/* Device Macros */
#define SLD_SPIKEHARD         0x04a
#define DEV_NAME              "sld,spikehard_rtl"
#define SPIKEHARD_TX_SIZE_REG 0x44
#define SPIKEHARD_RX_SIZE_REG 0x40
#endif // !defined(__unix__)

/* Logic Macros */
#define HEADER_LENGTH_IN_BITS      128
#define DMA_FRAME_TYPE_WIDTH       3
#define DMA_FRAME_TYPE_NOOP        0
#define DMA_FRAME_TYPE_NOOP_CONF   1
#define DMA_FRAME_TYPE_TERMINATE   2
#define DMA_FRAME_TYPE_IN_PACKETS  3
#define DMA_FRAME_TYPE_OUT_PACKETS 4
#define DMA_FRAME_TYPE_TICK        5
#define DMA_FRAME_TYPE_CORE_DATA   6
#define DMA_FRAME_TYPE_RESET       7

bool sm_init(spikehard_manager_t* mng, unsigned coherence, size_t tx_size, size_t rx_size) {
  mng->tx_size  = round_up(tx_size, sizeof(uint64_t));
  mng->rx_size  = round_up(rx_size, sizeof(uint64_t));
  mng->mem_size = mng->tx_size + mng->rx_size;
  mng->error    = false;

#if defined(__unix__)
  mng->mem                     = (uint32_t*)esp_alloc(mng->mem_size);
  cfg_000[0].hw_buf            = mng->mem;
  spikehard_cfg_000[0].tx_size = mng->tx_size;
  spikehard_cfg_000[0].rx_size = mng->rx_size;
#else
  { // Find device
    int ndev;
    struct esp_device* espdevs;
    printf("[SW][spikehard_manager] scanning device tree...\n");
    ndev = probe(&espdevs, VENDOR_SLD, SLD_SPIKEHARD, DEV_NAME);
    if (ndev == 0) {
      printf("[SW][spikehard_manager] spikehard not found\n");
      mng->error = true;
      return false;
    } else {
      printf("[SW][spikehard_manager] spikehard found\n");
    }
    mng->dev = &espdevs[0];
  }

  // Check DMA capabilities
  if (ioread32(mng->dev, PT_NCHUNK_MAX_REG) == 0) {
    printf("[SW][spikehard_manager] scatter-gather DMA is disabled, aborting.\n");
    mng->error = true;
    return false;
  }

  if (ioread32(mng->dev, PT_NCHUNK_MAX_REG) < NCHUNK(mng->mem_size)) {
    printf("[SW][spikehard_manager] not enough TLB entries available, aborting.\n");
    mng->error = true;
    return false;
  }

  // Allocate memory
  mng->mem = (uint32_t*)aligned_malloc(mng->mem_size);
  printf("[SW][spikehard_manager] memory buffer base-address = %p\n", mng->mem);

  // Alocate and populate page table
  mng->ptable = aligned_malloc(NCHUNK(mng->mem_size) * sizeof(unsigned*));
  for (int i = 0; i < NCHUNK(mng->mem_size); i++) {
    mng->ptable[i] = (unsigned*)&(((char*)mng->mem)[i * CHUNK_SIZE]);
  }

  printf("[SW][spikehard_manager] ptable = %p\n", mng->ptable);
  printf("[SW][spikehard_manager] nchunk = %lu\n", NCHUNK(mng->mem_size));

  iowrite32(mng->dev, SELECT_REG, ioread32(mng->dev, DEVID_REG));
  iowrite32(mng->dev, COHERENCE_REG, coherence);

#ifndef __sparc
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wpointer-to-int-cast"
  iowrite32(mng->dev, PT_ADDRESS_REG, (unsigned long long)mng->ptable);
#pragma GCC diagnostic pop
#else
  iowrite32(mng->dev, PT_ADDRESS_REG, (unsigned)mng->ptable);
#endif
  iowrite32(mng->dev, PT_NCHUNK_REG, NCHUNK(mng->mem_size));
  iowrite32(mng->dev, PT_SHIFT_REG, CHUNK_SHIFT);

  // Use the following if input and output data are not allocated at the default offsets
  iowrite32(mng->dev, SRC_OFFSET_REG, 0x0);
  iowrite32(mng->dev, DST_OFFSET_REG, 0x0);

  // Pass accelerator-specific configuration parameters
  iowrite32(mng->dev, SPIKEHARD_TX_SIZE_REG, mng->tx_size);
  iowrite32(mng->dev, SPIKEHARD_RX_SIZE_REG, mng->rx_size);

  // Flush (customize coherence model here)
  esp_flush(coherence);
#endif

  // Initialise DMA frame management
  mng->tx_offset = 0;
  mng->rx_offset = mng->tx_size / sizeof(uint32_t);

  printf("[SW][spikehard_manager] initialised\n");
  return true;
}

void sm_destroy(spikehard_manager_t* mng) {
#if defined(__unix__)
  esp_free(mng->mem);
#else
  aligned_free(mng->ptable);
  aligned_free(mng->mem);
#endif
  printf("[SW][spikehard_manager] destroyed\n");
}

void sm_run(spikehard_manager_t* mng) {
  printf("[SW][spikehard_manager] start...\n");

  if (mng->error) {
    printf("[SW][spikehard_manager] exiting due to error\n");
    return;
  }

#if defined(__unix__)
  esp_run(cfg_000, NACC);
#else
  // Start
  iowrite32(mng->dev, CMD_REG, CMD_MASK_START);

  // Wait for completion
  unsigned done = 0;
  while (!done) {
    done = ioread32(mng->dev, STATUS_REG);
    done &= STATUS_MASK_DONE;
  }
  iowrite32(mng->dev, CMD_REG, 0x0);
#endif

  printf("[SW][spikehard_manager] done\n");
}

static uint32_t make_32bit_word_zeros_(unsigned idx) {
  return 0;
}

static uint32_t* get_then_inc_tx_ptr(spikehard_manager_t* mng) {
  if (mng->tx_offset * sizeof(uint32_t) == mng->tx_size) {
    printf("[SW][spikehard_manager][error] reached limit of tx memory region\n");
    mng->error = true;
    return mng->mem;
  } else {
    return mng->mem + (mng->tx_offset++);
  }
}

static void sm_tx_align_(spikehard_manager_t* mng) {
  if (sizeof(void*) == 8) {
    if (mng->tx_offset & ((uint32_t)1u)) {
      printf("[SW][spikehard_manager] aligning header\n");
      *get_then_inc_tx_ptr(mng) = (uint32_t)0u;
    } else {
      printf("[SW][spikehard_manager] header already aligned\n");
    }
  }
}

static void sm_tx_header_(spikehard_manager_t* mng, uint32_t dma_frame_type, uint32_t (*make_32bit_word)(unsigned)) {
  printf("[SW][spikehard_manager] writing header %u\n", (unsigned)dma_frame_type);
  sm_tx_align_(mng);
  *get_then_inc_tx_ptr(mng) = dma_frame_type;
  for (unsigned i = 1; i < (HEADER_LENGTH_IN_BITS >> 5); ++i) {
    *get_then_inc_tx_ptr(mng) = make_32bit_word(i);
  }
}

static void sm_tx_empty_header_(spikehard_manager_t* mng, uint32_t dma_frame_type) {
  sm_tx_header_(mng, dma_frame_type, make_32bit_word_zeros_);
}

static uint64_t sm_tx_payload_address_(spikehard_manager_t* mng) {
  return mng->tx_offset * sizeof(uint32_t) + (HEADER_LENGTH_IN_BITS >> 3);
}

void sm_tx_terminate(spikehard_manager_t* mng) {
  sm_tx_empty_header_(mng, DMA_FRAME_TYPE_TERMINATE);
}

static uint16_t tick_amount_;
static uint64_t tick_delay_;

static uint32_t make_32bit_word_tick_(unsigned idx) {
  if (idx == 1) {
    return (uint32_t)tick_amount_;
  } else if (idx == 2) {
    return (uint32_t)tick_delay_;
  } else if (idx == 3) {
    return (uint32_t)(tick_delay_ >> 32);
  } else {
    return 0;
  }
}

void sm_tx_tick(spikehard_manager_t* mng, uint16_t amount, uint64_t delay) {
  tick_amount_ = amount;
  tick_delay_  = delay;

  sm_tx_header_(mng, DMA_FRAME_TYPE_TICK, make_32bit_word_tick_);
}

static unsigned reset_network_;
static unsigned reset_model_;
static unsigned reset_tick_idx_;

static uint32_t make_32bit_word_reset_(unsigned idx) {
  if (idx == 1) {
    return (reset_tick_idx_ & 1) | ((reset_network_ & 1) << 1) | ((reset_model_ & 1) << 2);
  } else {
    return 0;
  }
}

void sm_tx_reset(spikehard_manager_t* mng, bool reset_network, bool reset_model, bool reset_tick_idx) {
  reset_network_  = reset_network;
  reset_model_    = reset_model;
  reset_tick_idx_ = reset_tick_idx;

  sm_tx_header_(mng, DMA_FRAME_TYPE_RESET, make_32bit_word_reset_);
}

static uint32_t tx_packets_length_;
static uint64_t tx_packets_address_;

static uint32_t make_32bit_word_tx_packets_(unsigned idx) {
  if (idx == 1) {
    return tx_packets_length_;
  } else if (idx == 2) {
    return (uint32_t)tx_packets_address_;
  } else if (idx == 3) {
    return (uint32_t)(tx_packets_address_ >> 32);
  } else {
    return 0;
  }
}

void sm_tx_packets(spikehard_manager_t* mng, const packet_t* packets, uint32_t length) {
  tx_packets_length_  = length;
  tx_packets_address_ = sm_tx_payload_address_(mng);

  sm_tx_header_(mng, DMA_FRAME_TYPE_IN_PACKETS, make_32bit_word_tx_packets_);

  for (uint32_t i = 0; i < length; ++i) {
    *get_then_inc_tx_ptr(mng) = packets[i];
  }
}

static uint32_t tx_core_data_core_idx_;
static uint64_t tx_core_data_address_;

static uint32_t make_32bit_word_tx_core_data_(unsigned idx) {
  if (idx == 1) {
    return tx_core_data_core_idx_;
  } else if (idx == 2) {
    return (uint32_t)tx_core_data_address_;
  } else if (idx == 3) {
    return (uint32_t)(tx_core_data_address_ >> 32);
  } else {
    return 0;
  }
}

void sm_tx_core_data(spikehard_manager_t* mng, const core_data_t* core_data) {
  tx_core_data_core_idx_ = core_data->x + core_data->y * GRID_DIMENSION_X;
  tx_core_data_address_  = sm_tx_payload_address_(mng);

  sm_tx_header_(mng, DMA_FRAME_TYPE_CORE_DATA, make_32bit_word_tx_core_data_);

  for (uint32_t i = 0; i < core_data->tc_data_length; ++i) {
    *((uint64_t*)get_then_inc_tx_ptr(mng)) = core_data->tc_data[i];
    get_then_inc_tx_ptr(mng);
  }

  for (uint32_t i = 0; i < core_data->csram_data_length; ++i) {
    *((uint64_t*)get_then_inc_tx_ptr(mng)) = core_data->csram_data[i];
    get_then_inc_tx_ptr(mng);
  }
}

static uint32_t* get_then_inc_rx_ptr(spikehard_manager_t* mng) {
  if (mng->rx_offset * sizeof(uint32_t) == mng->mem_size) {
    printf("[SW][spikehard_manager][error] reached limit of rx memory region\n");
    mng->error = true;
    return mng->mem + mng->tx_size / sizeof(uint32_t);
  } else {
    return mng->mem + (mng->rx_offset++);
  }
}

static uint32_t* get_rx_ptr(spikehard_manager_t* mng) {
  if (mng->rx_offset * sizeof(uint32_t) == mng->mem_size) {
    printf("[SW][spikehard_manager][error] reached limit of rx memory region\n");
    mng->error = true;
    return mng->mem + mng->tx_size / sizeof(uint32_t);
  } else {
    return mng->mem + mng->rx_offset;
  }
}

static void sm_rx_align_(spikehard_manager_t* mng) {
  if (sizeof(void*) == 8) {
    if (mng->rx_offset & ((uint32_t)1u)) {
      get_then_inc_rx_ptr(mng);
    }
  }
}

uint32_t sm_rx_frame_type(spikehard_manager_t* mng) {
  sm_rx_align_(mng);
  uint32_t frame_type = (*get_rx_ptr(mng)) & ((uint32_t)((1 << DMA_FRAME_TYPE_WIDTH) - 1));
  printf("[SW][spikehard_manager] reading header %u\n", (unsigned)frame_type);
  return frame_type;
}

uint32_t sm_rx_error_flags(spikehard_manager_t* mng) {
  uint32_t frame_type = sm_rx_frame_type(mng);
  if (frame_type != DMA_FRAME_TYPE_TERMINATE) {
    printf("[SW][spikehard_manager][error] expected packet type %u, actual got %u\n",
           (unsigned)DMA_FRAME_TYPE_TERMINATE, (unsigned)frame_type);
    mng->error = true;
    return 0;
  }
  return ((*get_rx_ptr(mng)) & (~((uint32_t)((1 << DMA_FRAME_TYPE_WIDTH) - 1)))) >> DMA_FRAME_TYPE_WIDTH;
}

void sm_rx_peek_packets(spikehard_manager_t* mng, uint16_t* length, uint16_t* tick_idx) {
  const uint32_t frame_type = sm_rx_frame_type(mng);
  if (frame_type != DMA_FRAME_TYPE_OUT_PACKETS) {
    printf("[SW][spikehard_manager][error] expected packet type %u, actual got %u\n",
           (unsigned)DMA_FRAME_TYPE_OUT_PACKETS, (unsigned)frame_type);
    mng->error = true;
    *length    = 0;
    return;
  }

  if ((mng->rx_offset + 1) * sizeof(uint32_t) == mng->mem_size) {
    printf("[SW][spikehard_manager][error] reached limit of rx memory region\n");
    mng->error = true;
    *length    = 0;
    return;
  }

  const uint32_t metadata    = *(mng->mem + mng->rx_offset + 1);
  const uint16_t rx_length   = (uint16_t)metadata;
  const uint16_t rx_tick_idx = (uint16_t)(metadata >> 16);
  *length                    = rx_length;
  *tick_idx                  = rx_tick_idx;
}

void sm_rx_packets(spikehard_manager_t* mng, packet_t* packets, uint16_t max_length, uint16_t* length,
                   uint16_t* tick_idx) {
  uint32_t frame_type = sm_rx_frame_type(mng);
  if (frame_type != DMA_FRAME_TYPE_OUT_PACKETS) {
    printf("[SW][spikehard_manager][error] expected packet type %u, actual got %u\n",
           (unsigned)DMA_FRAME_TYPE_OUT_PACKETS, (unsigned)frame_type);
    mng->error = true;
    *length    = 0;
    return;
  }

  get_then_inc_rx_ptr(mng); // skip type
  uint32_t metadata    = *get_then_inc_rx_ptr(mng);
  uint16_t rx_length   = (uint16_t)metadata;
  uint16_t rx_tick_idx = (uint16_t)(metadata >> 16);
  uint64_t address     = *get_then_inc_rx_ptr(mng);
  address |= ((uint64_t)*get_then_inc_rx_ptr(mng)) << 32;
  mng->rx_offset = address / sizeof(uint32_t);
  printf("[SW][spikehard_manager] processing %i packets received at tick %i\n", rx_length, rx_tick_idx);

  *length   = rx_length;
  *tick_idx = rx_tick_idx;

  if (rx_length == 0) {
    return;
  }

  uint32_t offset = 0;
  while (true) {
    unsigned char* value = (unsigned char*)get_then_inc_rx_ptr(mng);
    for (int i = 0; i < sizeof(uint32_t); ++i) {
      if (offset == max_length) {
        printf("[SW][spikehard_manager][error] buffer overflow when trying to "
               "process received packets, allocated %i, required %i\n",
               max_length, rx_length);
        mng->error = true;
        return;
      }
      *(packets++) = (packet_t)(*(value++));
      if ((++offset) == rx_length) {
        return;
      }
    }
  }
}