// Copyright (c) 2011-2022 Columbia University, System Level Design Group
// SPDX-License-Identifier: Apache-2.0
#ifndef __ESP_CFG_000_H__
#define __ESP_CFG_000_H__

#include "libesp.h"
#include "spikehard_rtl.h"

#define TX_SIZE 1
#define RX_SIZE 1
const int32_t tx_size = TX_SIZE;
const int32_t rx_size = RX_SIZE;

#define NACC 1

struct spikehard_rtl_access spikehard_cfg_000[] = {{
    /* <<--descriptor-->> */
    .tx_size       = TX_SIZE,
    .rx_size       = RX_SIZE,
    .src_offset    = 0,
    .dst_offset    = 0,
    .esp.coherence = ACC_COH_NONE,
    .esp.p2p_store = 0,
    .esp.p2p_nsrcs = 0,
    .esp.p2p_srcs  = {"", "", "", ""},
}};

esp_thread_info_t cfg_000[] = {{
    .run       = true,
    .devname   = "spikehard_rtl.0",
    .ioctl_req = SPIKEHARD_RTL_IOC_ACCESS,
    .esp_desc  = &(spikehard_cfg_000[0].esp),
}};

#endif /* __ESP_CFG_000_H__ */
