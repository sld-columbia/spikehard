`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// EnReg.v
//
// Created for Dr. Akoglu's Reconfigurable Computing Lab
//  at the University of Arizona
// 
// Passes through a value at the positive edge of enable.
//////////////////////////////////////////////////////////////////////////////////

module EnReg #(
    parameter DATA_WIDTH = 8
)(
    input en,
    input clk,
    input rst,
    input [DATA_WIDTH-1:0] d,
    output reg [DATA_WIDTH-1:0] q
);
   
    always@(negedge clk) begin
        if (!rst) begin
            q <= 0;
        end
        else if (en) begin
            q <= d;
        end
    end
    
endmodule
