`timescale 1 ns / 1 ps

module spikehard #
(
    parameter GRID_DIMENSION_X = 4,
    parameter GRID_DIMENSION_Y = 4,
    parameter MAX_DIMENSION_X = 512,
    parameter MAX_DIMENSION_Y = 512,
    parameter OUTPUT_CORE_X_COORDINATE = 0,
    parameter OUTPUT_CORE_Y_COORDINATE = 0,
    parameter NUM_OUTPUTS = 16,
    parameter NUM_NEURONS = 32,
    parameter NUM_AXONS = 32,
    parameter NUM_TICKS = 16,
    parameter NUM_WEIGHTS = 4,
    parameter NUM_RESET_MODES = 2,
    parameter POTENTIAL_WIDTH = 9,
    parameter WEIGHT_WIDTH = 9,
    parameter LEAK_WIDTH = 9,
    parameter THRESHOLD_WIDTH = 9,
    parameter ROUTER_BUFFER_DEPTH = 4,
    parameter DMA_BUS_WIDTH = 32,
    parameter DMA_FRAME_HEADER_WORD_WIDTH = DMA_BUS_WIDTH
)(
    input clk,
    input rst,

    input [31:0] conf_info_tx_size,
    input [31:0] conf_info_rx_size,
    input conf_done,

    input dma_read_ctrl_ready,
    output dma_read_ctrl_valid,
    output [31:0] dma_read_ctrl_data_index,
    output [31:0] dma_read_ctrl_data_length,
    output [2:0] dma_read_ctrl_data_size,

    output dma_read_chnl_ready,
    input dma_read_chnl_valid,
    input [DMA_BUS_WIDTH-1:0] dma_read_chnl_data,

    input dma_write_ctrl_ready,
    output dma_write_ctrl_valid,
    output [31:0] dma_write_ctrl_data_index,
    output [31:0] dma_write_ctrl_data_length,
    output [2:0] dma_write_ctrl_data_size,

    input dma_write_chnl_ready,
    output dma_write_chnl_valid,
    output [DMA_BUS_WIDTH-1:0] dma_write_chnl_data,

    output acc_done,
    output [31:0] debug
);
    // This assumes that the dx and dy components are the most significant bits of the packet
    localparam DX_MSB = $clog2(MAX_DIMENSION_X) + $clog2(MAX_DIMENSION_Y) + $clog2(NUM_AXONS) + $clog2(NUM_TICKS) - 1;
    localparam DX_LSB = $clog2(MAX_DIMENSION_Y) + $clog2(NUM_AXONS) + $clog2(NUM_TICKS);
    localparam DY_MSB = $clog2(MAX_DIMENSION_Y) + $clog2(NUM_AXONS) + $clog2(NUM_TICKS) - 1;
    localparam DY_LSB = $clog2(NUM_AXONS) + $clog2(NUM_TICKS);
	
	localparam DX_WIDTH = DX_MSB - DX_LSB + 1;
	localparam DY_WIDTH = DY_MSB - DY_LSB + 1;
	localparam PACKET_WIDTH = DX_WIDTH+DY_WIDTH+$clog2(NUM_AXONS)+$clog2(NUM_TICKS);

    localparam CSRAM_READ_WIDTH = NUM_AXONS + POTENTIAL_WIDTH + POTENTIAL_WIDTH + WEIGHT_WIDTH*NUM_WEIGHTS + LEAK_WIDTH + THRESHOLD_WIDTH + THRESHOLD_WIDTH + $clog2(NUM_RESET_MODES) + DX_WIDTH + DY_WIDTH + $clog2(NUM_AXONS) + $clog2(NUM_TICKS);
    localparam NUM_CORES = GRID_DIMENSION_X * GRID_DIMENSION_Y;

    // Error Signals
    wire token_controller_error, scheduler_error;
    reg [1:0] err_latch_;
    assign debug[1:0] = err_latch_;
    assign debug[31:3] = 0;

    initial begin
        err_latch_ <= '0;
    end

    always@(posedge clk) begin
        if (!rst) begin
            err_latch_ <= '0;
        end
        else begin
            if (token_controller_error) begin
                err_latch_[0] <= 1'b1;
            end
            if (scheduler_error) begin
                err_latch_[1] <= 1'b1;
            end
        end
    end

	// SpikeHard controller wires
	wire [PACKET_WIDTH-1:0] packet_in;
	wire ren_to_input_buffer;
	wire input_buffer_empty;
    wire packet_out_valid;
    wire [$clog2(NUM_OUTPUTS)-1:0] packet_out;
    wire tick;
    wire [$clog2(NUM_WEIGHTS)-1:0] tc_data;
    wire [$clog2(NUM_AXONS)-1:0] tc_addr;
    wire [$clog2(NUM_CORES)-1:0] tc_core_idx;
    wire tc_valid;
    wire [CSRAM_READ_WIDTH-1:0] csram_data;
    wire [$clog2(NUM_NEURONS)-1:0] csram_addr;
    wire [$clog2(NUM_CORES)-1:0] csram_core_idx;
    wire csram_valid;
    wire rst_network;
    wire rst_model;

    spikehard_controller #(
        .NUM_OUTPUTS(NUM_OUTPUTS),
        .DMA_BUS_WIDTH(DMA_BUS_WIDTH),
        .PACKET_WIDTH(PACKET_WIDTH),
        .HEADER_WORD_WIDTH(DMA_FRAME_HEADER_WORD_WIDTH),
        .NUM_CORES(NUM_CORES),
        .NUM_NEURONS(NUM_NEURONS),
        .NUM_AXONS(NUM_AXONS),
        .NUM_WEIGHTS(NUM_WEIGHTS),
        .NUM_TICKS(NUM_TICKS),
        .CSRAM_READ_WIDTH(CSRAM_READ_WIDTH)
    ) spikehard_controller_inst (
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
        .tick(tick),
        .err_latch_(err_latch_),
        .ipbuf_empty(input_buffer_empty),
        .ren_to_ipbuf(ren_to_input_buffer),
        .ipbuf_dout(packet_in),
        .packet_out_valid(packet_out_valid),
        .packet_out(packet_out),
        .tc_data(tc_data),
        .tc_addr(tc_addr),
        .tc_core_idx(tc_core_idx),
        .tc_valid(tc_valid),
        .csram_data(csram_data),
        .csram_addr(csram_addr),
        .csram_core_idx(csram_core_idx),
        .csram_valid(csram_valid),
        .rst_network(rst_network),
        .rst_model(rst_model)
    );

	core_grid #(
        .GRID_DIMENSION_X(GRID_DIMENSION_X),
        .GRID_DIMENSION_Y(GRID_DIMENSION_Y),
        .OUTPUT_CORE_X_COORDINATE(OUTPUT_CORE_X_COORDINATE),
        .OUTPUT_CORE_Y_COORDINATE(OUTPUT_CORE_Y_COORDINATE),
        .NUM_OUTPUTS(NUM_OUTPUTS),
        .NUM_NEURONS(NUM_NEURONS),
        .NUM_AXONS(NUM_AXONS),
        .NUM_TICKS(NUM_TICKS),
        .NUM_WEIGHTS(NUM_WEIGHTS),
        .NUM_RESET_MODES(NUM_RESET_MODES),
        .POTENTIAL_WIDTH(POTENTIAL_WIDTH),
        .WEIGHT_WIDTH(WEIGHT_WIDTH),
        .LEAK_WIDTH(LEAK_WIDTH),
        .THRESHOLD_WIDTH(THRESHOLD_WIDTH),
        .DX_MSB(DX_MSB),
        .DX_LSB(DX_LSB),
        .DY_MSB(DY_MSB),
        .DY_LSB(DY_LSB),
        .ROUTER_BUFFER_DEPTH(ROUTER_BUFFER_DEPTH),
        .PACKET_WIDTH(PACKET_WIDTH),
        .CSRAM_READ_WIDTH(CSRAM_READ_WIDTH),
        .NUM_CORES(NUM_CORES)
    ) core_grid_inst (
        .clk(clk),
        .rst_network(rst_network),
        .rst_model(rst_model),
        .tick(tick),
        .input_buffer_empty(input_buffer_empty),
        .packet_in(packet_in),
        .packet_out(packet_out),
        .packet_out_valid(packet_out_valid),
        .ren_to_input_buffer(ren_to_input_buffer),
        .token_controller_error(token_controller_error),
        .scheduler_error(scheduler_error),
        .tc_data(tc_data),
        .tc_addr(tc_addr),
        .tc_core_idx(tc_core_idx),
        .tc_valid(tc_valid),
        .csram_data(csram_data),
        .csram_addr(csram_addr),
        .csram_core_idx(csram_core_idx),
        .csram_valid(csram_valid)
    );
    
endmodule
