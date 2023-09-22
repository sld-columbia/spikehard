`timescale 1 ns / 1 ps

module dma_controller
#(
    parameter DMA_BUS_WIDTH = 64,
    parameter READ_BUFFER_DEPTH = 32,
    parameter WRITE_BUFFER_DEPTH = 32,
    parameter DEBUG = 1 // logging will be enabled if DEBUG is non-zero.
)(
    input clk,
    input rst, // synchronous active low.

    // read control signals accessable to user.
    input [3:0] read_word_width,   // width of words to read, can be: 1, 2, 4, or 8 bytes.
    input [63:0] read_byte_offset, // read offset in bytes. This is assumed aligned w.r.t. bus width.
    input [63:0] read_length,      // number of words to read, which can be arbitrary.
    input read_valid,              // read request valid.
    output reg read_ready,         // dma controller can process read request.

    // read buffer signals accessable to user.
    output [63:0] rbuf_data,                        // data to read, lower bits used when data width less than 64.
    output rbuf_empty,                              // low if buffer contains at least r_data_width bits.
    input [3:0] rbuf_data_width,                    // number of bytes to read, can be any value between 1 and 8 inclusive.
    input rbuf_ready,                               // high if reading.
    output rbuf_aligned,                            // read and write pointers of read buffer are 64-bit aligned.
    output [$clog2(READ_BUFFER_DEPTH):0] rbuf_size, // number of bytes stored in read buffer.

    // write control signals accessable to user.
    // Note, unlike with reading, write_length*write_word_width is assumed to be a multiple of the bus width in bytes.
    // For instance, if a single 16-bit word is being written, then the user should appropriately pad the word so that
    // the resulting payload width is the same as the bus width (e.g. add 16 bits of padding when using a 32-bit bus).
    // This constraint is in place, otherwise we would either have to implicitly fetch the memory we do not want to
    // overwrite, or overwrite memory that we may not want to modify. It is up to the user to decide what to do.
    input [3:0] write_word_width,   // width of words to write, can be: 1, 2, 4, or 8 bytes.
    input [63:0] write_byte_offset, // write offset in bytes. This is assumed aligned w.r.t. bus width.
    input [63:0] write_length,      // number of words to write.
    input write_valid,              // write request valid.
    output reg write_ready,         // dma controller can process write request.

    // write buffer signals accessable to user.
    input [63:0] wbuf_data,                          // data to write, lower bits used when data width less than 64.
    output wbuf_full,                                // high if buffer has less than w_data_width bits in empty space.
    input [3:0] wbuf_data_width,                     // number of bytes to write, can be any value between 1 and 8 inclusive.
    input wbuf_valid,                                // high if writing.
    output wbuf_aligned,                             // read and write pointers of write buffer are 64-bit aligned.
    output [$clog2(WRITE_BUFFER_DEPTH):0] wbuf_size, // number of bytes stored in write buffer.

    // DMA signals to wire directly to accelerator interface.
    input dma_read_ctrl_ready,
    output reg dma_read_ctrl_valid,
    output reg [31:0] dma_read_ctrl_data_index,
    output reg [31:0] dma_read_ctrl_data_length,
    output reg [2:0] dma_read_ctrl_data_size,
    output dma_read_chnl_ready,
    input dma_read_chnl_valid,
    input [DMA_BUS_WIDTH-1:0] dma_read_chnl_data,
    input dma_write_ctrl_ready,
    output reg dma_write_ctrl_valid,
    output reg [31:0] dma_write_ctrl_data_index,
    output reg [31:0] dma_write_ctrl_data_length,
    output reg [2:0] dma_write_ctrl_data_size,
    input dma_write_chnl_ready,
    output dma_write_chnl_valid,
    output [DMA_BUS_WIDTH-1:0] dma_write_chnl_data
);
    localparam DMA_BUS_WIDTH_IN_BYTES = DMA_BUS_WIDTH >> 3;
    wire [3:0] bus_data_width = DMA_BUS_WIDTH_IN_BYTES;

    wire rbuf_full;
    wire wbuf_empty;

    wire [63:0] rbuf_w_data;
    wire [63:0] wbuf_r_data;

    generate
        if (DMA_BUS_WIDTH == 64) begin
            assign rbuf_w_data = dma_read_chnl_data;
            assign dma_write_chnl_data = wbuf_r_data;
        end
        else if (DMA_BUS_WIDTH == 32) begin
            assign rbuf_w_data[63:32] = 0;
            assign rbuf_w_data[31:0] = dma_read_chnl_data;
            assign dma_write_chnl_data = wbuf_r_data[31:0];
        end
    endgenerate

    reg [3:0] rbuf_w_data_width;

    dma_buffer #(
        .DEPTH(READ_BUFFER_DEPTH),
        .DEBUG(DEBUG)
    ) dma_buffer_inst_bus_to_acc (
        .clk(clk),
        .rst(rst),
        .r_data(rbuf_data),
        .r_empty(rbuf_empty),
        .r_ready(rbuf_ready),
        .r_data_width(rbuf_data_width),
        .w_data(rbuf_w_data),
        .w_full(rbuf_full),
        .w_data_width(rbuf_w_data_width),
        .w_valid(dma_read_chnl_valid && dma_read_chnl_ready),
        .aligned(rbuf_aligned),
        .size(rbuf_size)
    );

    dma_buffer #(
        .DEPTH(WRITE_BUFFER_DEPTH),
        .DEBUG(DEBUG)
    ) dma_buffer_inst_acc_to_bus (
        .clk(clk),
        .rst(rst),
        .r_data(wbuf_r_data),
        .r_empty(wbuf_empty),
        .r_ready(dma_write_chnl_valid && dma_write_chnl_ready),
        .r_data_width(bus_data_width),
        .w_data(wbuf_data),
        .w_full(wbuf_full),
        .w_valid(wbuf_valid),
        .w_data_width(wbuf_data_width),
        .aligned(wbuf_aligned),
        .size(wbuf_size)
    );

    assign dma_read_chnl_ready = !rbuf_full;
    assign dma_write_chnl_valid = !wbuf_empty;

    reg [2:0] read_state;
    reg [2:0] write_state;

    localparam STATE_CTRL = 2'b00,
               STATE_CHNL = 2'b01,
               STATE_IDLE = 2'b10;

    reg [3:0] read_last_beat_data_width;

    always @(posedge clk) begin  
        if (!rst) begin
            read_state <= STATE_IDLE;
            rbuf_w_data_width <= bus_data_width;
            dma_read_ctrl_valid <= 1'b0;
            read_ready <= 1'b0;
        end
        else begin
            case (read_state)
                STATE_IDLE: begin
                    read_ready <= 1'b1;
                    if (read_ready && read_valid && read_length) begin
                        if (DEBUG) begin
                            $display ("[RTL][dma_controller] changing read state to STATE_CTRL");
                        end // DEBUG
                        read_state <= STATE_CTRL;
                        dma_read_ctrl_data_index <= read_byte_offset / DMA_BUS_WIDTH_IN_BYTES; // all data accesses must be aligned w.r.t. bus width
                        dma_read_ctrl_data_length <= (((read_length*read_word_width-1) | (DMA_BUS_WIDTH_IN_BYTES-1))+1) / DMA_BUS_WIDTH_IN_BYTES; // does not have to be multiple of bus width
                        dma_read_ctrl_data_size <= (read_word_width == 8) ? 3'b011 : ((read_word_width == 4) ? 3'b010 : ((read_word_width == 2) ? 3'b001 : 3'b000));
                        dma_read_ctrl_valid <= 1'b1;
                        read_ready <= 1'b0;
                        rbuf_w_data_width <= bus_data_width;
                        read_last_beat_data_width <= bus_data_width - ((((read_length*read_word_width-1) | (DMA_BUS_WIDTH_IN_BYTES-1))+1) - (read_length*read_word_width));
                    end
                end
                STATE_CTRL: begin
                    if (dma_read_ctrl_ready) begin
                        if (DEBUG) begin
                            $display ("[RTL][dma_controller] read length: %d", dma_read_ctrl_data_length);
                            $display ("[RTL][dma_controller] read index: %d", dma_read_ctrl_data_index);
                            $display ("[RTL][dma_controller] read size: %d", dma_read_ctrl_data_size);
                            $display ("[RTL][dma_controller] read last beat width: %d", read_last_beat_data_width);
                            $display ("[RTL][dma_controller] changing read state to STATE_CHNL");
                        end // DEBUG
                        read_state <= STATE_CHNL;
                        dma_read_ctrl_valid <= 1'b0;
                        if (dma_read_ctrl_data_length == 1) begin
                            rbuf_w_data_width <= read_last_beat_data_width;
                        end
                    end
                end
                STATE_CHNL: begin
                    if (dma_read_chnl_valid && dma_read_chnl_ready) begin
                        if (DEBUG) begin
                            if (DMA_BUS_WIDTH == 64) begin
                                if (read_word_width == 1) begin
                                    $display ("[RTL][dma_controller] read: %d %d %d %d %d %d %d %d", dma_read_chnl_data[63:56], dma_read_chnl_data[55:48], dma_read_chnl_data[47:40], dma_read_chnl_data[39:32], dma_read_chnl_data[31:24], dma_read_chnl_data[23:16], dma_read_chnl_data[15:8], dma_read_chnl_data[7:0]);    
                                end
                                else if (read_word_width == 2) begin
                                    $display ("[RTL][dma_controller] read: %d %d %d %d", dma_read_chnl_data[63:48], dma_read_chnl_data[47:32], dma_read_chnl_data[31:16], dma_read_chnl_data[15:0]);    
                                end
                                else if (read_word_width == 4) begin
                                    $display ("[RTL][dma_controller] read: %d %d", dma_read_chnl_data[63:32], dma_read_chnl_data[31:0]);    
                                end
                                else if (read_word_width == 8) begin
                                    $display ("[RTL][dma_controller] read: %d", dma_read_chnl_data[63:0]);    
                                end
                            end
                            else if (DMA_BUS_WIDTH == 32) begin
                                if (read_word_width == 1) begin
                                    $display ("[RTL][dma_controller] read: %d %d %d %d", dma_read_chnl_data[31:24], dma_read_chnl_data[23:16], dma_read_chnl_data[15:8], dma_read_chnl_data[7:0]);    
                                end
                                else if (read_word_width == 2) begin
                                    $display ("[RTL][dma_controller] read: %d %d", dma_read_chnl_data[31:16], dma_read_chnl_data[15:0]);    
                                end
                                else if (read_word_width == 4) begin
                                    $display ("[RTL][dma_controller] read: %d", dma_read_chnl_data[31:0]);    
                                end
                            end
                        end // DEBUG
                        
                        dma_read_ctrl_data_length <= dma_read_ctrl_data_length - 1;
                        if (dma_read_ctrl_data_length == 1) begin
                            if (DEBUG) begin
                                $display ("[RTL][dma_controller] changing read state to STATE_IDLE");
                            end // DEBUG
                            read_state <= STATE_IDLE;
                        end
                        else if (dma_read_ctrl_data_length == 2) begin
                            rbuf_w_data_width <= read_last_beat_data_width;
                        end
                    end
                end
            endcase
        end
    end

    always @(posedge clk) begin  
        if (!rst) begin
            write_state <= STATE_IDLE;
            dma_write_ctrl_valid <= 1'b0;
            write_ready <= 1'b0;
        end
        else begin
            case (write_state)
                STATE_IDLE: begin
                    write_ready <= 1'b1;
                    if (write_ready && write_valid && write_length) begin
                        if (DEBUG) begin
                            $display ("[RTL][dma_controller] changing write state to STATE_CTRL");
                        end // DEBUG
                        write_state <= STATE_CTRL;
                        dma_write_ctrl_data_index <= write_byte_offset / DMA_BUS_WIDTH_IN_BYTES; // all data accesses must be aligned w.r.t. bus width
                        dma_write_ctrl_data_length <= write_length*write_word_width / DMA_BUS_WIDTH_IN_BYTES; // assume multiple of bus width otherwise we may undesirably overwrite data
                        dma_write_ctrl_data_size <= (write_word_width == 8) ? 3'b011 : ((write_word_width == 4) ? 3'b010 : ((write_word_width == 2) ? 3'b001 : 3'b000));
                        dma_write_ctrl_valid <= 1'b1;
                        write_ready <= 1'b0;
                    end
                end
                STATE_CTRL: begin
                    if (dma_write_ctrl_ready) begin
                        if (DEBUG) begin
                            $display ("[RTL][dma_controller] write length: %d", dma_write_ctrl_data_length);
                            $display ("[RTL][dma_controller] write index: %d", dma_write_ctrl_data_index);
                            $display ("[RTL][dma_controller] write size: %d", dma_write_ctrl_data_size);
                            $display ("[RTL][dma_controller] changing write state to STATE_CHNL");
                        end // DEBUG
                        write_state <= STATE_CHNL;
                        dma_write_ctrl_valid <= 1'b0;
                    end
                end
                STATE_CHNL: begin
                    if (dma_write_chnl_ready && dma_write_chnl_valid) begin
                        if (DEBUG) begin
                            if (DMA_BUS_WIDTH == 64) begin
                                if (write_word_width == 1) begin
                                    $display ("[RTL][dma_controller] write: %d %d %d %d %d %d %d %d", dma_write_chnl_data[63:56], dma_write_chnl_data[55:48], dma_write_chnl_data[47:40], dma_write_chnl_data[39:32], dma_write_chnl_data[31:24], dma_write_chnl_data[23:16], dma_write_chnl_data[15:8], dma_write_chnl_data[7:0]);    
                                end
                                else if (write_word_width == 2) begin
                                    $display ("[RTL][dma_controller] write: %d %d %d %d", dma_write_chnl_data[63:48], dma_write_chnl_data[47:32], dma_write_chnl_data[31:16], dma_write_chnl_data[15:0]);    
                                end
                                else if (write_word_width == 4) begin
                                    $display ("[RTL][dma_controller] write: %d %d", dma_write_chnl_data[63:32], dma_write_chnl_data[31:0]);    
                                end
                                else if (write_word_width == 8) begin
                                    $display ("[RTL][dma_controller] write: %d", dma_write_chnl_data[63:0]);    
                                end
                            end
                            else if (DMA_BUS_WIDTH == 32) begin
                                if (write_word_width == 1) begin
                                    $display ("[RTL][dma_controller] write: %d %d %d %d", dma_write_chnl_data[31:24], dma_write_chnl_data[23:16], dma_write_chnl_data[15:8], dma_write_chnl_data[7:0]);    
                                end
                                else if (write_word_width == 2) begin
                                    $display ("[RTL][dma_controller] write: %d %d", dma_write_chnl_data[31:16], dma_write_chnl_data[15:0]);    
                                end
                                else if (write_word_width == 4) begin
                                    $display ("[RTL][dma_controller] write: %d", dma_write_chnl_data[31:0]);    
                                end
                                else if (write_word_width == 8) begin
                                    $display ("[RTL][dma_controller] write partial: %d", dma_write_chnl_data[31:0]);    
                                end
                            end
                        end // DEBUG

                        dma_write_ctrl_data_length <= dma_write_ctrl_data_length - 1;
                        if (dma_write_ctrl_data_length == 1) begin
                            if (DEBUG) begin
                                $display ("[RTL][dma_controller] changing write state to STATE_IDLE");
                            end // DEBUG
                            write_state <= STATE_IDLE;
                        end
                    end
                end
            endcase
        end
    end
endmodule
