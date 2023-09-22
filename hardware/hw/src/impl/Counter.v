`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// Counter.v
//
// Created for Dr. Akoglu's Reconfigurable Computing Lab
//  at the University of Arizona
// 
// A simple counter module that is initialized to all 1's.
//////////////////////////////////////////////////////////////////////////////////

module Counter #(
    parameter DATA_WIDTH = 4
)(
    input wen,
    input clk,
    input rst,
    output reg [DATA_WIDTH-1:0] out
);    
    always@(negedge clk) begin
        if (!rst) begin
            out <= {DATA_WIDTH{1'b1}};
        end
        else if (wen) begin
            out <= out + 1;
        end
    end
   
endmodule
