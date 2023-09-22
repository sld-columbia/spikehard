`timescale 1ns / 1ps

module dma_buffer
#(
    parameter DEPTH = 8, // number of bytes, which has to be a power of 2.
    parameter DEBUG = 1  // logging will be enabled if DEBUG is non-zero.
)(
    input clk,
    input rst, // synchronous active low.

    // read signals.
    output [63:0] r_data,     // data to read, lower bits used when data width less than 64.
    output r_empty,           // low if buffer contains at least r_data_width bits.
    input [3:0] r_data_width, // number of bytes to read, can be any value between 1 and 8 inclusive.
    input r_ready,            // high if reading.

    // write signals.
    input [63:0] w_data,      // data to write, lower bits used when data width less than 64.
    output w_full,            // high if buffer has less than w_data_width bits in empty space.
    input [3:0] w_data_width, // number of bytes to write, can be any value between 1 and 8 inclusive.
    input w_valid,            // high if writing.
    
    output aligned, // read and write pointers are 64-bit aligned.
    output [$clog2(DEPTH):0] size // number of bytes stored in buffer.
);
    reg [7:0] data [DEPTH-1:0];
    reg [$clog2(DEPTH)-1:0] r_ptr;
    reg [$clog2(DEPTH)-1:0] w_ptr;
    reg [$clog2(DEPTH):0] size_;
    wire should_read;
    wire should_write;
    wire [3:0] size_to_remove;
    wire [3:0] size_to_add;

    assign w_full = size_ > (DEPTH-w_data_width);
    assign r_empty = size_ < r_data_width;

    assign size = size_;
    assign aligned = ((r_ptr & 7) == 7) && ((w_ptr & 7) == 7);
    assign r_data = {data[r_ptr-7], data[r_ptr-6], data[r_ptr-5], data[r_ptr-4], data[r_ptr-3], data[r_ptr-2], data[r_ptr-1], data[r_ptr]};
    assign should_read = (r_ready && !r_empty && r_data_width && r_data_width < 9);
    assign should_write = (w_valid && !w_full && w_data_width && w_data_width < 9);
    assign size_to_remove = should_read ? r_data_width : 0;
    assign size_to_add = should_write ? w_data_width : 0;

    always@(posedge clk) begin
        if (!rst || (!should_read && !should_write && !size)) begin
            // This block is triggered when (!should_read && !should_write && !size) so as to align
            // the pointers to 64-bits to avoid read/write across boundary whilst processing a DMA frame.
            r_ptr <= ~'0;
            w_ptr <= ~'0;
            size_ <= '0;
        end
        else begin
            size_ <= size_ - size_to_remove + size_to_add;
            
            if (should_read) begin
                if (DEBUG) begin
                    $display("[RTL][dma_buffer] reading %d bytes", r_data_width);
                end // DEBUG
                r_ptr <= r_ptr - r_data_width;
            end

            if (should_write) begin
                if (DEBUG) begin
                    $display("[RTL][dma_buffer] writing %d bytes", w_data_width);
                end // DEBUG
                data[w_ptr] <= w_data[7:0];
                if (w_data_width > 1) begin
                    data[w_ptr-1] <= w_data[15:8];
                end
                if (w_data_width > 2) begin
                    data[w_ptr-2] <= w_data[23:16];
                end
                if (w_data_width > 3) begin
                    data[w_ptr-3] <= w_data[31:24];
                end
                if (w_data_width > 4) begin
                    data[w_ptr-4] <= w_data[39:32];
                end
                if (w_data_width > 5) begin
                    data[w_ptr-5] <= w_data[47:40];
                end
                if (w_data_width > 6) begin
                    data[w_ptr-6] <= w_data[55:48];
                end
                if (w_data_width > 7) begin
                    data[w_ptr-7] <= w_data[63:56];
                end
                w_ptr <= w_ptr - w_data_width;
            end
        end
    end
endmodule
