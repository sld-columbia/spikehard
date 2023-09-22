`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// CSRAM.v
//
// Created for Dr. Akoglu's Reconfigurable Computing Lab
//  at the University of Arizona
// 
// Holds the configuration parameters for the neurons for a core.
//////////////////////////////////////////////////////////////////////////////////

module CSRAM #(
    parameter CORE_IDX = 0,
    parameter NUM_NEURONS = 256,
    parameter WIDTH = 367,
    parameter WRITE_WIDTH = 9
)(
    input clk,
    input wen,  
    input [$clog2(NUM_NEURONS)-1:0] address,
    input [WIDTH-1:0] data_in,
    output reg [WIDTH-1:0] data_out
); 

    reg [WIDTH-1:0] memory [0:NUM_NEURONS-1];

    always@(negedge clk) begin
        if (wen) begin
            memory[address] <= data_in;
        end
        else begin
            data_out <= memory[address];
        end
    end
endmodule
