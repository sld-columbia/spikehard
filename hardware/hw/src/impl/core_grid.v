`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// core_grid.v
//
// Created for Dr. Akoglu's Reconfigurable Computing Lab
//  at the University of Arizona
// 
// Generates a grid of SpikeHard cores.
//////////////////////////////////////////////////////////////////////////////////

module core_grid #(
    parameter GRID_DIMENSION_X = 5,
    parameter GRID_DIMENSION_Y = 1,
    parameter OUTPUT_CORE_X_COORDINATE = 4,
    parameter OUTPUT_CORE_Y_COORDINATE = 0,
    parameter NUM_OUTPUTS = 256,
    parameter NUM_NEURONS = 256,
    parameter NUM_AXONS = 256,
    parameter NUM_TICKS = 16,
    parameter NUM_WEIGHTS = 4,
    parameter NUM_RESET_MODES = 2,
    parameter POTENTIAL_WIDTH = 9,
    parameter WEIGHT_WIDTH = 9,
    parameter LEAK_WIDTH = 9,
    parameter THRESHOLD_WIDTH = 9,
    parameter DX_MSB = 29,
    parameter DX_LSB = 21,
    parameter DY_MSB = 20,
    parameter DY_LSB = 12,
    parameter ROUTER_BUFFER_DEPTH = 4,
    parameter PACKET_WIDTH = (DX_MSB - DX_LSB + 1)+(DY_MSB - DY_LSB + 1)+$clog2(NUM_AXONS)+$clog2(NUM_TICKS),
    parameter CSRAM_READ_WIDTH = 367,
    parameter NUM_CORES = GRID_DIMENSION_X * GRID_DIMENSION_Y
)(
    input clk,
    input rst_network,
    input rst_model,
    input tick,
    input input_buffer_empty,
    input [PACKET_WIDTH-1:0] packet_in,
    output [$clog2(NUM_OUTPUTS)-1:0] packet_out,
    output packet_out_valid,
    output ren_to_input_buffer,
    output token_controller_error,
    output scheduler_error,
    input [$clog2(NUM_WEIGHTS)-1:0] tc_data,
    input [$clog2(NUM_AXONS)-1:0] tc_addr,
    input [$clog2(NUM_CORES)-1:0] tc_core_idx,
    input tc_valid,
    input [CSRAM_READ_WIDTH-1:0] csram_data,
    input [$clog2(NUM_NEURONS)-1:0] csram_addr,
    input [$clog2(NUM_CORES)-1:0] csram_core_idx,
    input csram_valid
);
    localparam DX_WIDTH = DX_MSB - DX_LSB + 1;
	localparam DY_WIDTH = DY_MSB - DY_LSB + 1;
    localparam OUTPUT_CORE = OUTPUT_CORE_X_COORDINATE + OUTPUT_CORE_Y_COORDINATE * GRID_DIMENSION_X;
    
    // Wires for Errors:
    wire [NUM_CORES - 1:0] token_controller_errors;
    wire [NUM_CORES - 1:0] scheduler_errors;
    
    // Wires for Eastward Routing Communication
    wire [NUM_CORES - 1:0] ren_east_bus;
    wire [NUM_CORES - 1:0] empty_east_bus;
    
    // Wires for Westward Routing Communication
    wire [NUM_CORES - 1:0] ren_west_bus;
    wire [NUM_CORES - 1:0] empty_west_bus;
    
    // Wires for Northward Routing Communication
    wire [NUM_CORES - 1:0] ren_north_bus;
    wire [NUM_CORES - 1:0] empty_north_bus;
    
    // Wires for Southward Routing Communication
    wire [NUM_CORES - 1:0] ren_south_bus;
    wire [NUM_CORES - 1:0] empty_south_bus;
    
    // Wires for packets
    wire [PACKET_WIDTH-1:0] east_out_packets [NUM_CORES - 1:0];
    wire [PACKET_WIDTH-1:0] west_out_packets [NUM_CORES - 1:0];
    wire [PACKET_WIDTH-DX_WIDTH-1:0] north_out_packets [NUM_CORES - 1:0];
    wire [PACKET_WIDTH-DX_WIDTH-1:0] south_out_packets [NUM_CORES - 1:0];
    
    genvar curr_core;
    
    assign token_controller_error = | token_controller_errors;  // OR all TC errors to get final token_controller_error
    assign scheduler_error = | scheduler_errors;                // OR all SCH errors to get final scheduler error
    assign ren_to_input_buffer = ren_west_bus[0];               // Read enable to the buffer that stores the input packets
    
    for (curr_core = 0; curr_core < GRID_DIMENSION_X * GRID_DIMENSION_Y; curr_core = curr_core + 1) begin : gencore
        localparam right_edge = curr_core % GRID_DIMENSION_X == (GRID_DIMENSION_X - 1);
        localparam left_edge = curr_core % GRID_DIMENSION_X == 0;
        localparam top_edge = curr_core / GRID_DIMENSION_X == (GRID_DIMENSION_Y - 1);
        localparam bottom_edge = curr_core / GRID_DIMENSION_X == 0;
        
        if (curr_core != OUTPUT_CORE) begin
            Core #(
                .PACKET_WIDTH(PACKET_WIDTH),
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
                .CORE_IDX(curr_core),
                .NUM_CORES(NUM_CORES),
                .CSRAM_READ_WIDTH(CSRAM_READ_WIDTH)
            ) Core (
                .clk(clk),
                .tick(tick),
                .rst_network(rst_network),
                .rst_model(rst_model),
                .ren_in_west(left_edge ? 1'b0 : ren_east_bus[curr_core - 1]),
                .ren_in_east(right_edge ? 1'b0 : ren_west_bus[curr_core + 1]),
                .ren_in_north(top_edge ? 1'b0 : ren_south_bus[curr_core + GRID_DIMENSION_X]),
                .ren_in_south(bottom_edge ? 1'b0 : ren_north_bus[curr_core - GRID_DIMENSION_X]),
                .empty_in_west(curr_core == 0 ? input_buffer_empty : left_edge ? 1'b1 : empty_east_bus[curr_core - 1]),
                .empty_in_east(right_edge ? 1'b1 : empty_west_bus[curr_core + 1]),
                .empty_in_north(top_edge ? 1'b1 : empty_south_bus[curr_core + GRID_DIMENSION_X]),
                .empty_in_south(bottom_edge ? 1'b1 : empty_north_bus[curr_core - GRID_DIMENSION_X]),
                .east_in(right_edge ? {PACKET_WIDTH{1'b0}} : west_out_packets[curr_core + 1]),
                .west_in(curr_core == 0 ? packet_in : left_edge ? {PACKET_WIDTH{1'b0}} : east_out_packets[curr_core - 1]),
                .north_in(top_edge ? {PACKET_WIDTH-DX_WIDTH{1'b0}} : south_out_packets[curr_core + GRID_DIMENSION_X]),
                .south_in(bottom_edge ? {PACKET_WIDTH-DX_WIDTH{1'b0}}: north_out_packets[curr_core - GRID_DIMENSION_X]),
                .ren_out_west(ren_west_bus[curr_core]),
                .ren_out_east(ren_east_bus[curr_core]),
                .ren_out_north(ren_north_bus[curr_core]),
                .ren_out_south(ren_south_bus[curr_core]),
                .empty_out_west(empty_west_bus[curr_core]),
                .empty_out_east(empty_east_bus[curr_core]),
                .empty_out_north(empty_north_bus[curr_core]),
                .empty_out_south(empty_south_bus[curr_core]),
                .east_out(east_out_packets[curr_core]),
                .west_out(west_out_packets[curr_core]),
                .north_out(north_out_packets[curr_core]),
                .south_out(south_out_packets[curr_core]),
                .token_controller_error(token_controller_errors[curr_core]),
                .scheduler_error(scheduler_errors[curr_core]),
                .tc_data(tc_data),
                .tc_addr(tc_addr),
                .tc_core_idx(tc_core_idx),
                .tc_valid(tc_valid),
                .csram_data(csram_data),
                .csram_addr(csram_addr),
                .csram_core_idx(csram_core_idx),
                .csram_valid(csram_valid)
            );
        end
        else begin
            OutputBus #(
                .PACKET_WIDTH(PACKET_WIDTH),
                .NUM_OUTPUTS(NUM_OUTPUTS),
                .NUM_AXONS(NUM_AXONS),
                .NUM_TICKS(NUM_TICKS),
                .DX_MSB(DX_MSB),
                .DX_LSB(DX_LSB),
                .DY_MSB(DY_MSB),
                .DY_LSB(DY_LSB),
                .ROUTER_BUFFER_DEPTH(ROUTER_BUFFER_DEPTH)
            ) OutputBus (
                .clk(clk),
                .rst(rst_network),
                .ren_in_west(left_edge ? 1'b0 : ren_east_bus[curr_core - 1]),
                .ren_in_east(right_edge ? 1'b0 : ren_west_bus[curr_core + 1]),
                .ren_in_north(top_edge ? 1'b0 : ren_south_bus[curr_core + GRID_DIMENSION_X]),
                .ren_in_south(bottom_edge ? 1'b0 : ren_north_bus[curr_core - GRID_DIMENSION_X]),
                .empty_in_west(curr_core == 0 ? input_buffer_empty : left_edge ? 1'b1 : empty_east_bus[curr_core - 1]),
                .empty_in_east(right_edge ? 1'b1 : empty_west_bus[curr_core + 1]),
                .empty_in_north(top_edge ? 1'b1 : empty_south_bus[curr_core + GRID_DIMENSION_X]),
                .empty_in_south(bottom_edge ? 1'b1 : empty_north_bus[curr_core - GRID_DIMENSION_X]),
                .ren_out_west(ren_west_bus[curr_core]),
                .ren_out_east(ren_east_bus[curr_core]),
                .ren_out_north(ren_north_bus[curr_core]),
                .ren_out_south(ren_south_bus[curr_core]),
                .empty_out_west(empty_west_bus[curr_core]),
                .empty_out_east(empty_east_bus[curr_core]),
                .empty_out_north(empty_north_bus[curr_core]),
                .empty_out_south(empty_south_bus[curr_core]),
                .east_in(right_edge ? {PACKET_WIDTH{1'b0}} : west_out_packets[curr_core + 1]),
                .west_in(curr_core == 0 ? packet_in : left_edge ? {PACKET_WIDTH{1'b0}} : east_out_packets[curr_core - 1]),
                .north_in(top_edge ? {PACKET_WIDTH-DX_WIDTH{1'b0}} : south_out_packets[curr_core + GRID_DIMENSION_X]),      // North In From Next North's South Out
                .south_in(bottom_edge ? {PACKET_WIDTH-DX_WIDTH{1'b0}} : north_out_packets[curr_core - GRID_DIMENSION_X]),      // South In From Next South's North Out
                .east_out(east_out_packets[curr_core]),     // East Out, Next East's West In
                .west_out(west_out_packets[curr_core]),     // West Out, Next West's East In
                .north_out(north_out_packets[curr_core]),    // North Out, Next North's South In
                .south_out(south_out_packets[curr_core]),    // South Out, Next South's North In
                .packet_out(packet_out),
                .packet_out_valid(packet_out_valid),
                .token_controller_error(token_controller_errors[curr_core]),
                .scheduler_error(scheduler_errors[curr_core])
            );
        end
    end     
    
endmodule