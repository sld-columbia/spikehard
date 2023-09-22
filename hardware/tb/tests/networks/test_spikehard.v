
`timescale 1ns / 1ps


module test_spikehard;

reg clk;
reg rst;

reg [31:0] conf_info_tx_size;
reg [31:0] conf_info_rx_size;
reg conf_done;

reg dma_read_ctrl_ready;
wire dma_read_ctrl_valid;
wire [31:0] dma_read_ctrl_data_index;
wire [31:0] dma_read_ctrl_data_length;
wire [2:0] dma_read_ctrl_data_size;

wire dma_read_chnl_ready;
reg dma_read_chnl_valid;
reg [`DMA_BUS_WIDTH-1:0] dma_read_chnl_data;

reg dma_write_ctrl_ready;
wire dma_write_ctrl_valid;
wire [31:0] dma_write_ctrl_data_index;
wire [31:0] dma_write_ctrl_data_length;
wire [2:0] dma_write_ctrl_data_size;

reg dma_write_chnl_ready;
wire dma_write_chnl_valid;
wire [`DMA_BUS_WIDTH-1:0] dma_write_chnl_data;

wire acc_done;
wire [31:0] debug;

initial begin
    $from_myhdl(clk, rst, conf_info_tx_size, conf_info_rx_size, conf_done, dma_read_ctrl_ready, dma_read_chnl_valid, dma_read_chnl_data, dma_write_ctrl_ready, dma_write_chnl_ready);
    $to_myhdl(dma_read_ctrl_valid, dma_read_ctrl_data_index, dma_read_ctrl_data_length,dma_read_ctrl_data_size, dma_read_chnl_ready, dma_write_ctrl_valid, dma_write_ctrl_data_index, dma_write_ctrl_data_length, dma_write_ctrl_data_size, dma_write_chnl_valid, dma_write_chnl_data, acc_done, debug);
end

spikehard #(
    .GRID_DIMENSION_X(`GRID_DIMENSION_X),
    .GRID_DIMENSION_Y(`GRID_DIMENSION_Y),
    .OUTPUT_CORE_X_COORDINATE(`OUTPUT_CORE_X_COORDINATE),
    .OUTPUT_CORE_Y_COORDINATE(`OUTPUT_CORE_Y_COORDINATE),
    .NUM_OUTPUTS(`NUM_OUTPUTS),
    .NUM_NEURONS(`NUM_NEURONS),
    .NUM_AXONS(`NUM_AXONS),
    .NUM_TICKS(`NUM_TICKS),
    .NUM_WEIGHTS(`NUM_WEIGHTS),
    .NUM_RESET_MODES(`NUM_RESET_MODES),
    .POTENTIAL_WIDTH(`POTENTIAL_WIDTH),
    .WEIGHT_WIDTH(`WEIGHT_WIDTH),
    .LEAK_WIDTH(`LEAK_WIDTH),
    .THRESHOLD_WIDTH(`THRESHOLD_WIDTH),
    .MAX_DIMENSION_X(`MAX_DIMENSION_X),
    .MAX_DIMENSION_Y(`MAX_DIMENSION_Y),
    .ROUTER_BUFFER_DEPTH(`ROUTER_BUFFER_DEPTH),
    .DMA_BUS_WIDTH(`DMA_BUS_WIDTH),
    .DMA_FRAME_HEADER_WORD_WIDTH(`DMA_FRAME_HEADER_WORD_WIDTH)
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
