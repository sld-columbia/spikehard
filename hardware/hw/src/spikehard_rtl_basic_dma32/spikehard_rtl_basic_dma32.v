module spikehard_rtl_basic_dma32(clk, rst, dma_read_chnl_valid, dma_read_chnl_data, dma_read_chnl_ready,
                                 conf_info_tx_size, conf_info_rx_size, conf_done, acc_done, debug, dma_read_ctrl_valid, dma_read_ctrl_data_index,
                                 dma_read_ctrl_data_length, dma_read_ctrl_data_size, dma_read_ctrl_ready, dma_write_ctrl_valid,
                                 dma_write_ctrl_data_index, dma_write_ctrl_data_length, dma_write_ctrl_data_size,
                                 dma_write_ctrl_ready, dma_write_chnl_valid, dma_write_chnl_data, dma_write_chnl_ready);
   input clk;
   input rst;

   input [31:0] conf_info_tx_size;
   input [31:0] conf_info_rx_size;
   input conf_done;

   input dma_read_ctrl_ready;
   output dma_read_ctrl_valid;
   output [31:0] dma_read_ctrl_data_index;
   output [31:0] dma_read_ctrl_data_length;
   output [2:0] dma_read_ctrl_data_size;

   output dma_read_chnl_ready;
   input dma_read_chnl_valid;
   input [31:0] dma_read_chnl_data;

   input dma_write_ctrl_ready;
   output dma_write_ctrl_valid;
   output [31:0] dma_write_ctrl_data_index;
   output [31:0] dma_write_ctrl_data_length;
   output [2:0] dma_write_ctrl_data_size;

   input dma_write_chnl_ready;
   output dma_write_chnl_valid;
   output [31:0] dma_write_chnl_data;

   output acc_done;
   output [31:0] debug;

   spikehard #(
      .DMA_BUS_WIDTH(32)
   ) spikehard_inst (
      .clk(clk),
      .rst(rst),
      .conf_info_tx_size(conf_info_tx_size),
      .conf_info_rx_size(conf_info_rx_size),
      .conf_done(conf_done),
      .dma_read_ctrl_ready(dma_read_ctrl_ready),
      .dma_read_ctrl_valid(dma_read_ctrl_valid),
      .dma_read_ctrl_data_index(dma_read_ctrl_data_index),
      .dma_read_ctrl_data_length(dma_read_ctrl_data_length),
      .dma_read_ctrl_data_size(dma_read_ctrl_data_size),
      .dma_read_chnl_ready(dma_read_chnl_ready),
      .dma_read_chnl_valid(dma_read_chnl_valid),
      .dma_read_chnl_data(dma_read_chnl_data),
      .dma_write_ctrl_ready(dma_write_ctrl_ready),
      .dma_write_ctrl_valid(dma_write_ctrl_valid),
      .dma_write_ctrl_data_index(dma_write_ctrl_data_index),
      .dma_write_ctrl_data_length(dma_write_ctrl_data_length),
      .dma_write_ctrl_data_size(dma_write_ctrl_data_size),
      .dma_write_chnl_ready(dma_write_chnl_ready),
      .dma_write_chnl_valid(dma_write_chnl_valid),
      .dma_write_chnl_data(dma_write_chnl_data),
      .acc_done(acc_done),
      .debug(debug)
   );
endmodule
