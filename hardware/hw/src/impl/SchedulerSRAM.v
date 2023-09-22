`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// SchedulerSRAM.v
//
// Created for Dr. Akoglu's Reconfigurable Computing Lab
//  at the University of Arizona
// 
// Stores spikes that are to be processed for a core.
//////////////////////////////////////////////////////////////////////////////////

module SchedulerSRAM #(
    parameter NUM_AXONS = 256,
    parameter NUM_TICKS = 16
)(
    input clk,
    input rst,
    input clr,
    input wen,
    input [$clog2(NUM_TICKS)-1:0] read_address,
    input [$clog2(NUM_AXONS) + $clog2(NUM_TICKS) - 1:0] packet,
    output reg [NUM_AXONS-1:0] out
);

    reg [NUM_AXONS-1:0] memory [0:NUM_TICKS-1];
    reg [$clog2(NUM_TICKS)-1:0] address_to_reset;

    wire [$clog2(NUM_TICKS)-1:0] write_address;
    
    assign write_address = packet[$clog2(NUM_TICKS)-1:0] + read_address + 1;

    always@(posedge clk) begin
        if (!rst) begin
            address_to_reset <= '1;
            memory[0] <= '0;
        end
        else if (address_to_reset) begin
            memory[address_to_reset] <= '0;
            address_to_reset <= address_to_reset + '1;
        end
        else if (clr) begin
            memory[read_address] <= '0;
        end
        else if (wen) begin
            memory[write_address][packet[$clog2(NUM_AXONS) + $clog2(NUM_TICKS)-1:$clog2(NUM_TICKS)]] <= 1'b1;
        end
    end

    always@(*) begin
        if (address_to_reset) begin
            out <= '0;
        end
        else begin
            out <= memory[read_address];
        end
    end
    
endmodule
