`timescale 1ns / 1ps

module static_buffer
#(
    parameter DEPTH = 3,        // desired number of largest word.
    parameter READ_WIDTH = 64,  // number of bits per read
    parameter WRITE_WIDTH = 64, // number of bits per write
    parameter DEBUG = 1         // logging will be enabled if DEBUG is non-zero.
)(
    input clk,
    input rst, // synchronous active low.

    // read signals.
    output [READ_WIDTH-1:0] r_data, // data to read
    output r_empty,                 // low if buffer contains at least READ_WIDTH bits.
    input r_ready,                  // high if reading.

    // write signals.
    input [WRITE_WIDTH-1:0] w_data, // data to write
    output w_full,                  // high if buffer has less than WRITE_WIDTH bits in empty space.
    output w_close_to_full,         // high if buffer has less than 2*WRITE_WIDTH bits in empty space.
    input w_valid                   // high if writing.
);
    localparam SMALLEST_WORD = (READ_WIDTH > WRITE_WIDTH) ? WRITE_WIDTH : READ_WIDTH;
    localparam WORDS_PER_WRITE = (WRITE_WIDTH / SMALLEST_WORD);
    localparam WORDS_PER_READ = (READ_WIDTH / SMALLEST_WORD);
    localparam DEPTH_ = 1 << $clog2(DEPTH * ((READ_WIDTH > WRITE_WIDTH) ? (READ_WIDTH / WRITE_WIDTH) : (WRITE_WIDTH / READ_WIDTH)));

    reg [SMALLEST_WORD-1:0] data [DEPTH_-1:0];
    reg [$clog2(DEPTH_)-1:0] r_ptr;
    reg [$clog2(DEPTH_)-1:0] w_ptr;
    reg [$clog2(DEPTH_):0] size_;

    generate
        if (SMALLEST_WORD == WRITE_WIDTH) begin
            wire should_read;
            wire should_write;
            wire [$clog2(DEPTH_):0] size_to_remove;
            wire [$clog2(DEPTH_):0] size_to_add;

            assign w_close_to_full = (((size_ - size_to_remove + size_to_add) > (DEPTH_-WORDS_PER_WRITE))) || w_full;
            assign w_full = size_ > (DEPTH_-WORDS_PER_WRITE);
            assign r_empty = size_ < WORDS_PER_READ;

            assign should_read = (r_ready && !r_empty);
            assign should_write = (w_valid && !w_full);
            assign size_to_remove = should_read ? WORDS_PER_READ : 0;
            assign size_to_add = should_write ? WORDS_PER_WRITE : 0;

            genvar r_data_idx;
            for (r_data_idx = 0; r_data_idx < WORDS_PER_READ; r_data_idx = r_data_idx + 1) begin : gen_r_data
                assign r_data[(r_data_idx[$clog2(DEPTH_)-1:0]+1) * SMALLEST_WORD - 1:(r_data_idx[$clog2(DEPTH_)-1:0]) * SMALLEST_WORD] = data[r_ptr-r_data_idx[$clog2(DEPTH_)-1:0]];
            end

            always@(posedge clk) begin
                if (!rst) begin
                    r_ptr <= {$clog2(DEPTH_){1'b1}};
                    w_ptr <= {$clog2(DEPTH_){1'b1}};
                    size_ <= '0;
                end
                else begin
                    size_ <= size_ - size_to_remove + size_to_add;

                    if (should_read) begin
                        if (DEBUG) begin
                            $display("[RTL][static_buffer] reading %d bits: %d", READ_WIDTH, r_data);
                        end // DEBUG
                        r_ptr <= r_ptr - WORDS_PER_READ;
                    end

                    if (should_write) begin
                        if (DEBUG) begin
                            $display("[RTL][static_buffer] writing %d bits: %d", WRITE_WIDTH, w_data);
                        end // DEBUG
                        w_ptr <= w_ptr - WORDS_PER_WRITE;
                        data[w_ptr] <= w_data;
                    end
                end
            end
        end
        else begin
            wire should_read;
            wire should_write;
            wire [$clog2(DEPTH_):0] size_to_remove;
            wire [$clog2(DEPTH_):0] size_to_add;

            reg [$clog2(WORDS_PER_WRITE):0] w_num_staged_words;
            reg [WRITE_WIDTH-READ_WIDTH-1:0] w_staged_words;

            assign w_close_to_full = (((size_ - size_to_remove + size_to_add) > (DEPTH_-WORDS_PER_WRITE))) || w_full || w_valid;
            assign w_full = (size_ > (DEPTH_-WORDS_PER_WRITE)) || (w_num_staged_words > 0);
            assign r_empty = size_ < WORDS_PER_READ;

            assign should_read = (r_ready && !r_empty);
            assign should_write = (w_valid && !w_full);
            assign size_to_remove = should_read ? WORDS_PER_READ : 0;
            assign size_to_add = should_write ? WORDS_PER_WRITE : 0;

            assign r_data = data[r_ptr];

            always@(posedge clk) begin
                if (!rst) begin
                    r_ptr <= {$clog2(DEPTH_){1'b1}};
                    w_ptr <= {$clog2(DEPTH_){1'b1}};
                    size_ <= '0;
                    w_num_staged_words <= '0;
                end
                else begin
                    size_ <= size_ - size_to_remove + size_to_add;

                    if (should_read) begin
                        if (DEBUG) begin
                            $display("[RTL][static_buffer] reading %d bits: %d", READ_WIDTH, r_data);
                        end // DEBUG
                        r_ptr <= r_ptr - 1;
                    end

                    if (should_write) begin
                        if (DEBUG) begin
                            $display("[RTL][static_buffer] writing %d bits: %d", WRITE_WIDTH, w_data);
                        end // DEBUG

                        w_staged_words[WRITE_WIDTH-READ_WIDTH-1:0] <= w_data[WRITE_WIDTH-1:READ_WIDTH];
                        data[w_ptr] <= w_data[READ_WIDTH-1:0];
                        w_num_staged_words <= WORDS_PER_WRITE - 1;
                        w_ptr <= w_ptr - 1;
                    end
                    else if (w_num_staged_words > 0) begin
                        data[w_ptr] <= w_staged_words[READ_WIDTH-1:0];
                        w_staged_words[WRITE_WIDTH-2*READ_WIDTH-1:0] <= w_staged_words[WRITE_WIDTH-READ_WIDTH-1:READ_WIDTH];
                        w_num_staged_words <= w_num_staged_words - 1;
                        w_ptr <= w_ptr - 1;
                    end
                end
            end
        end
    endgenerate
endmodule