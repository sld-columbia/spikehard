// Copyright (c) 2011-2022 Columbia University, System Level Design Group
// SPDX-License-Identifier: Apache-2.0
#include <linux/of_device.h>
#include <linux/mm.h>

#include <asm/io.h>

#include <esp_accelerator.h>
#include <esp.h>

#include "spikehard_rtl.h"

#define DRV_NAME "spikehard_rtl"

/* <<--regs-->> */
#define SPIKEHARD_TX_SIZE_REG 0x44
#define SPIKEHARD_RX_SIZE_REG 0x40

struct spikehard_rtl_device {
  struct esp_device esp;
};

static struct esp_driver spikehard_driver;

static struct of_device_id spikehard_device_ids[] = {
    {
        .name = "SLD_SPIKEHARD_RTL",
    },
    {
        .name = "eb_04a",
    },
    {
        .compatible = "sld,spikehard_rtl",
    },
    {},
};

static int spikehard_devs;

static inline struct spikehard_rtl_device* to_spikehard(struct esp_device* esp) {
  return container_of(esp, struct spikehard_rtl_device, esp);
}

static void spikehard_prep_xfer(struct esp_device* esp, void* arg) {
  struct spikehard_rtl_access* a = arg;

  /* <<--regs-config-->> */
  iowrite32be(a->tx_size, esp->iomem + SPIKEHARD_TX_SIZE_REG);
  iowrite32be(a->rx_size, esp->iomem + SPIKEHARD_RX_SIZE_REG);
  iowrite32be(a->src_offset, esp->iomem + SRC_OFFSET_REG);
  iowrite32be(a->dst_offset, esp->iomem + DST_OFFSET_REG);
}

static bool spikehard_xfer_input_ok(struct esp_device* esp, void* arg) {
  /* struct spikehard_rtl_device *spikehard = to_spikehard(esp); */
  /* struct spikehard_rtl_access *a = arg; */

  return true;
}

static int spikehard_probe(struct platform_device* pdev) {
  struct spikehard_rtl_device* spikehard;
  struct esp_device* esp;
  int rc;

  spikehard = kzalloc(sizeof(*spikehard), GFP_KERNEL);
  if (spikehard == NULL)
    return -ENOMEM;
  esp         = &spikehard->esp;
  esp->module = THIS_MODULE;
  esp->number = spikehard_devs;
  esp->driver = &spikehard_driver;
  rc          = esp_device_register(esp, pdev);
  if (rc)
    goto err;

  spikehard_devs++;
  return 0;
err:
  kfree(spikehard);
  return rc;
}

static int __exit spikehard_remove(struct platform_device* pdev) {
  struct esp_device* esp                 = platform_get_drvdata(pdev);
  struct spikehard_rtl_device* spikehard = to_spikehard(esp);

  esp_device_unregister(esp);
  kfree(spikehard);
  return 0;
}

static struct esp_driver spikehard_driver = {
    .plat =
        {
            .probe  = spikehard_probe,
            .remove = spikehard_remove,
            .driver =
                {
                    .name           = DRV_NAME,
                    .owner          = THIS_MODULE,
                    .of_match_table = spikehard_device_ids,
                },
        },
    .xfer_input_ok = spikehard_xfer_input_ok,
    .prep_xfer     = spikehard_prep_xfer,
    .ioctl_cm      = SPIKEHARD_RTL_IOC_ACCESS,
    .arg_size      = sizeof(struct spikehard_rtl_access),
};

static int __init spikehard_init(void) {
  return esp_driver_register(&spikehard_driver);
}

static void __exit spikehard_exit(void) {
  esp_driver_unregister(&spikehard_driver);
}

module_init(spikehard_init) module_exit(spikehard_exit)

    MODULE_DEVICE_TABLE(of, spikehard_device_ids);

MODULE_AUTHOR("Emilio G. Cota <cota@braap.org>");
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("spikehard_rtl driver");
