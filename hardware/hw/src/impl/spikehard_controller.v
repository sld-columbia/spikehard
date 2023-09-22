`timescale 1 ns / 1 ps

module spikehard_controller
#(
    parameter DMA_BUS_WIDTH = 32,
    parameter DMA_READ_BUFFER_DEPTH = 32,
    parameter DMA_WRITE_BUFFER_DEPTH = 32,
    parameter IN_PACKET_BUFFER_DEPTH = 4,
    parameter OUT_PACKET_BUFFER_DEPTH = 32,
    parameter FLUSH_OUT_PACKET_BUFFER_THRESHOLD = 8,
    parameter HEADER_WORD_WIDTH = DMA_BUS_WIDTH,
    parameter PACKET_WIDTH = 32,
    parameter NUM_OUTPUTS = 256,
    parameter NUM_CORES = 999,
    parameter NUM_NEURONS = 256,
    parameter NUM_AXONS = 256,
    parameter NUM_WEIGHTS = 4,
    parameter NUM_TICKS = 16,
    parameter CSRAM_READ_WIDTH = 367,
    parameter DEBUG = 0 // logging will be enabled if DEBUG is non-zero.
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

    output reg acc_done,

    // SpikeHard
    output reg tick,
    input [1:0] err_latch_,
    output ipbuf_empty,
    input ren_to_ipbuf,
    output [PACKET_WIDTH-1:0] ipbuf_dout,
    input packet_out_valid,
    input [$clog2(NUM_OUTPUTS)-1:0] packet_out,
    output reg rst_network,
    output reg rst_model,

    // tc read signals (all cores constantly monitor these signals).
    output reg [$clog2(NUM_WEIGHTS)-1:0] tc_data,    // data to read.
    output reg [$clog2(NUM_AXONS)-1:0] tc_addr,      // address to write data.
    output reg [$clog2(NUM_CORES)-1:0] tc_core_idx,  // core index.
    output tc_valid,                                 // high if outputting data.

    // csram read signals (all cores constantly monitor these signals).
    output reg [CSRAM_READ_WIDTH-1:0] csram_data,       // data to read.
    output reg [$clog2(NUM_NEURONS)-1:0] csram_addr,    // address to write data.
    output reg [$clog2(NUM_CORES)-1:0] csram_core_idx,  // core index.
    output csram_valid                                  // high if outputting data.
);
    localparam OUT_PACKET_WIDTH = $clog2(NUM_OUTPUTS);

    wire read_ready;
    reg read_valid;
    wire [63:0] rbuf_data;
    reg rbuf_ready;
    wire rbuf_empty;
    wire rbuf_aligned;
    wire [$clog2(DMA_READ_BUFFER_DEPTH):0] rbuf_size;

    wire write_ready;
    reg write_valid;
    reg [63:0] wbuf_data;
    reg wbuf_valid;
    wire wbuf_full;
    wire wbuf_aligned;
    wire [$clog2(DMA_WRITE_BUFFER_DEPTH):0] wbuf_size;
	
    reg [3:0] read_word_width;
    reg [3:0] write_word_width;
    wire [3:0] rbuf_data_width;
    wire [3:0] wbuf_data_width;
    reg [63:0] read_byte_offset;
    reg [63:0] write_byte_offset;
    reg [63:0] read_length;
    reg [63:0] write_length;

	dma_controller #(
	   .DMA_BUS_WIDTH(DMA_BUS_WIDTH),
       .READ_BUFFER_DEPTH(DMA_READ_BUFFER_DEPTH),
       .WRITE_BUFFER_DEPTH(DMA_WRITE_BUFFER_DEPTH),
       .DEBUG(DEBUG)
	) dma_controller_inst (
        .clk(clk),
        .rst(rst),
        .read_word_width(read_word_width),
        .read_byte_offset(read_byte_offset),
        .read_length(read_length),
        .read_valid(read_valid),
        .read_ready(read_ready),
        .rbuf_data(rbuf_data),
        .rbuf_empty(rbuf_empty),
        .rbuf_aligned(rbuf_aligned),
        .rbuf_size(rbuf_size),
        .rbuf_ready(rbuf_ready),
        .rbuf_data_width(rbuf_data_width),
        .write_word_width(write_word_width),
        .write_byte_offset(write_byte_offset),
        .write_length(write_length),
        .write_valid(write_valid),
        .write_ready(write_ready),
        .wbuf_data(wbuf_data),
        .wbuf_full(wbuf_full),
        .wbuf_valid(wbuf_valid),
        .wbuf_data_width(wbuf_data_width),
        .wbuf_aligned(wbuf_aligned),
        .wbuf_size(wbuf_size),
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
        .dma_write_chnl_data(dma_write_chnl_data)
    );

	wire [PACKET_WIDTH-1:0] dma_to_ipbuf;
	wire dma_to_ipbuf_valid;
    wire ipbuf_almost_full;

	fifo_buffer #(
        .DATA_WIDTH(PACKET_WIDTH),
        .BUFFER_DEPTH(IN_PACKET_BUFFER_DEPTH),
        .TYPE(1),
        .DEBUG(DEBUG)
    ) in_packet_buffer (
        .clk(clk),
        .rst(rst_network),
        .din(dma_to_ipbuf),
        .din_valid(dma_to_ipbuf_valid),
        .read_en(ren_to_ipbuf),
        .dout(ipbuf_dout),
        .empty(ipbuf_empty),
        .full(),
        .almost_full(ipbuf_almost_full)
    );

    wire [OUT_PACKET_WIDTH-1:0] opbuf_dout;
	wire opbuf_full;
    wire opbuf_empty;
    reg opbuf_ren;

	fifo_buffer #(
        .DATA_WIDTH(OUT_PACKET_WIDTH),
        .BUFFER_DEPTH(OUT_PACKET_BUFFER_DEPTH),
        .TYPE(2),
        .DEBUG(DEBUG)
    ) out_packet_buffer (
        .clk(clk),
        .rst(rst_network),
        .din(packet_out),
        .din_valid(packet_out_valid),
        .read_en(opbuf_ren),
        .dout(opbuf_dout),
        .empty(opbuf_empty),
        .full(opbuf_full),
        .almost_full()
    );

    localparam CORE_DATA_PAYLOAD_WORD_WIDTH = 64;
    localparam TC_READ_WIDTH = $clog2(NUM_WEIGHTS);
    localparam TC_PADDING = (1 << $clog2(TC_READ_WIDTH)) - TC_READ_WIDTH;
    localparam CSRAM_PADDING = (1 << $clog2(CSRAM_READ_WIDTH)) - CSRAM_READ_WIDTH;
    localparam TC_READ_PADDED_WIDTH = TC_READ_WIDTH + TC_PADDING;
    localparam CSRAM_READ_PADDED_WIDTH = CSRAM_READ_WIDTH + CSRAM_PADDING;
    localparam TC_DEPTH = 3;
    localparam CSRAM_DEPTH = 3;
    localparam TC_NUM_WORDS = ((((TC_READ_PADDED_WIDTH*NUM_AXONS)-1)|((CORE_DATA_PAYLOAD_WORD_WIDTH)-1))+1) / CORE_DATA_PAYLOAD_WORD_WIDTH;
    localparam CSRAM_NUM_WORDS = ((((CSRAM_READ_PADDED_WIDTH*NUM_NEURONS)-1)|((CORE_DATA_PAYLOAD_WORD_WIDTH)-1))+1) / CORE_DATA_PAYLOAD_WORD_WIDTH;

    wire [TC_READ_PADDED_WIDTH-1:0] tc_r_data;
    wire tc_r_empty;
    wire tc_r_ready;
    wire tc_w_full;
    wire tc_w_close_to_full;
    wire tc_w_valid;
    reg tc_buf_rst;

    wire [CSRAM_READ_PADDED_WIDTH-1:0] csram_r_data;
    wire csram_r_empty;
    wire csram_r_ready;
    wire csram_w_full;
    wire csram_w_close_to_full;
    wire csram_w_valid;
    reg csram_buf_rst;
    
    assign tc_data = tc_r_data[TC_READ_WIDTH-1:0];
    assign csram_data = csram_r_data[CSRAM_READ_WIDTH-1:0];
    
    static_buffer #(
        .DEPTH(TC_DEPTH),
        .READ_WIDTH(TC_READ_PADDED_WIDTH),
        .WRITE_WIDTH(CORE_DATA_PAYLOAD_WORD_WIDTH),
        .DEBUG(DEBUG)
    ) static_buffer_tc_inst (
        .clk(clk),
        .rst(rst && tc_buf_rst),
        .r_data(tc_r_data),
        .r_empty(tc_r_empty),
        .r_ready(tc_r_ready),
        .w_data(rbuf_data[CORE_DATA_PAYLOAD_WORD_WIDTH-1:0]),
        .w_full(tc_w_full),
        .w_close_to_full(tc_w_close_to_full),
        .w_valid(tc_w_valid)
    );

    static_buffer #(
        .DEPTH(CSRAM_DEPTH),
        .READ_WIDTH(CSRAM_READ_PADDED_WIDTH),
        .WRITE_WIDTH(CORE_DATA_PAYLOAD_WORD_WIDTH),
        .DEBUG(DEBUG)
    ) static_buffer_csram_inst (
        .clk(clk),
        .rst(rst && csram_buf_rst),
        .r_data(csram_r_data),
        .r_empty(csram_r_empty),
        .r_ready(csram_r_ready),
        .w_data(rbuf_data[CORE_DATA_PAYLOAD_WORD_WIDTH-1:0]),
        .w_full(csram_w_full),
        .w_close_to_full(csram_w_close_to_full),
        .w_valid(csram_w_valid)
    );

    localparam EXEC_STATE_WIDTH = 4;
    wire [EXEC_STATE_WIDTH-1:0] INIT_READ_HEADER = 0,
                                READ_HEADER = 1,
                                INIT_READ_IN_PACKETS_PAYLOAD = 2,
                                READ_IN_PACKETS_PAYLOAD = 3,
                                INIT_READ_CORE_DATA_PAYLOAD = 4,
                                READ_CORE_DATA_PAYLOAD = 5,
                                INIT_WRITE_HEADER_1 = 6,
                                INIT_WRITE_HEADER_2 = 7,
                                WRITE_HEADER = 8,
                                INIT_WRITE_OUT_PACKETS_PAYLOAD = 9,
                                WRITE_OUT_PACKETS_PAYLOAD = 10,
                                INIT_WRITE_TERMINATE_HEADER = 11,
                                WRITE_TERMINATE_HEADER = 12,
                                DONE  = 13,
                                IDLE  = 14;

    reg [EXEC_STATE_WIDTH-1:0] exec_state;
    reg [31:0] words_read;
    reg [31:0] words_written;
    reg [63:0] next_read_byte_offset;
    reg [63:0] next_write_byte_offset;

    reg [15:0] w_tick_idx;
    reg [15:0] w_num_elapsed_ticks;
    reg w_has_ticked;
    reg [3:0] w_exec_state_to_restore;
    reg [$clog2(OUT_PACKET_BUFFER_DEPTH):0] w_prev_tick_num_rem_packets;
    reg [$clog2(OUT_PACKET_BUFFER_DEPTH):0] w_curr_tick_num_rem_packets;
    reg [15:0] w_num_packets;
    reg [63:0] w_payload_address;
    reg w_has_packet_to_send;

    reg tick_before_next_frame;
    
    localparam HEADER_LENGTH_IN_BITS = 128;
    localparam DMA_HEADER_LENGTH = HEADER_LENGTH_IN_BITS / HEADER_WORD_WIDTH;
    localparam IN_PACKETS_PAYLOAD_WORD_WIDTH = (PACKET_WIDTH <= 8) ? 8 : ((PACKET_WIDTH <= 16) ? 16 : ((PACKET_WIDTH <= 32) ? 32 : 64));
    localparam OUT_PACKETS_PAYLOAD_WORD_WIDTH = (OUT_PACKET_WIDTH <= 8) ? 8 : ((OUT_PACKET_WIDTH <= 16) ? 16 : ((OUT_PACKET_WIDTH <= 32) ? 32 : 64));
    
    localparam DMA_FRAME_TYPE_WIDTH = 3;
    wire [DMA_FRAME_TYPE_WIDTH-1:0] DMA_FRAME_TYPE_NOOP = 0,
                                    DMA_FRAME_TYPE_NOOP_CONF = 1,
                                    DMA_FRAME_TYPE_TERMINATE  = 2,
                                    DMA_FRAME_TYPE_IN_PACKETS = 3,
                                    DMA_FRAME_TYPE_OUT_PACKETS = 4,
                                    DMA_FRAME_TYPE_TICK = 5,
                                    DMA_FRAME_TYPE_CORE_DATA = 6,
                                    DMA_FRAME_TYPE_RESET = 7;
    
    reg [HEADER_WORD_WIDTH-1:0] r_dma_header_words [DMA_HEADER_LENGTH-1:0];
    wire [HEADER_WORD_WIDTH-1:0] w_dma_header_words [DMA_HEADER_LENGTH-1:0];

    wire [31:0] dma_frame_metadata;
    wire [DMA_FRAME_TYPE_WIDTH-1:0] dma_frame_type;
    
    assign dma_frame_type = dma_frame_metadata[DMA_FRAME_TYPE_WIDTH-1:0];
    
    // DMA_FRAME_TYPE_NOOP_CONF
    reg [63:0] noop_amount;
    reg [63:0] noop_num_past_clk_posedge;
    wire [63:0] noop_conf_amount;
    localparam NOOP_DELAY_TYPE_TICK = 0;
    localparam NOOP_DELAY_TYPE_CLK = 1;
    
    // DMA_FRAME_TYPE_IN_PACKETS
    wire [31:0] in_packets_length;
    wire [63:0] in_packets_byte_offset;

    // DMA_FRAME_TYPE_TICK
    wire [15:0] tick_total_amount;
    reg [15:0] tick_remaining_amount;
    wire [63:0] tick_delay;
    reg [63:0] clk_cycles_since_last_tick;

    // DMA_FRAME_TYPE_CORE_DATA
    wire [$clog2(NUM_CORES)-1:0] core_data_idx;
    wire [63:0] core_data_byte_offset;
    reg [$clog2(NUM_AXONS):0] tc_rem_words_to_read;
    reg [$clog2(NUM_NEURONS):0] csram_rem_words_to_read;

    // DMA_FRAME_TYPE_RESET
    reg [5:0] reset_rem_cycles;
    wire should_reset_tick_idx;
    wire should_reset_network;
    wire should_reset_model;

    generate
        if (HEADER_WORD_WIDTH == 32) begin
            assign dma_frame_metadata = r_dma_header_words[0];

            // DMA_FRAME_TYPE_NOOP_CONF
            assign noop_conf_amount[31:0] = r_dma_header_words[2];
            assign noop_conf_amount[63:32] = r_dma_header_words[3];

            // DMA_FRAME_TYPE_IN_PACKETS
            assign in_packets_length = r_dma_header_words[1];
            assign in_packets_byte_offset[31:0] = r_dma_header_words[2];
            assign in_packets_byte_offset[63:32] = r_dma_header_words[3];

            // DMA_FRAME_TYPE_OUT_PACKETS
            assign w_dma_header_words[0] = DMA_FRAME_TYPE_OUT_PACKETS;
            assign w_dma_header_words[1][15:0] = w_num_packets;
            assign w_dma_header_words[1][31:16] = w_tick_idx;
            assign w_dma_header_words[2] = w_payload_address[31:0];
            assign w_dma_header_words[3] = w_payload_address[63:32];

            // DMA_FRAME_TYPE_TICK
            assign tick_total_amount = r_dma_header_words[1][15:0];
            assign tick_delay[31:0] = r_dma_header_words[2];
            assign tick_delay[63:32] = r_dma_header_words[3];
            
            // DMA_FRAME_TYPE_CORE_DATA
            assign core_data_idx = r_dma_header_words[1][$clog2(NUM_CORES)-1:0];
            assign core_data_byte_offset[31:0] = r_dma_header_words[2];
            assign core_data_byte_offset[63:32] = r_dma_header_words[3];

            // DMA_FRAME_TYPE_RESET
            assign should_reset_tick_idx = r_dma_header_words[1][0];
            assign should_reset_network = r_dma_header_words[1][1];
            assign should_reset_model = r_dma_header_words[1][2];
        end
        else if (HEADER_WORD_WIDTH == 64) begin
            assign dma_frame_metadata = r_dma_header_words[0][31:0];

            // DMA_FRAME_TYPE_NOOP_CONF
            assign noop_conf_amount = r_dma_header_words[1];

            // DMA_FRAME_TYPE_IN_PACKETS
            assign in_packets_length = r_dma_header_words[0][63:32];
            assign in_packets_byte_offset = r_dma_header_words[1];

            // DMA_FRAME_TYPE_OUT_PACKETS
            assign w_dma_header_words[0][31:0] = DMA_FRAME_TYPE_OUT_PACKETS;
            assign w_dma_header_words[0][47:32] = w_num_packets;
            assign w_dma_header_words[0][63:48] = w_tick_idx;
            assign w_dma_header_words[1] = w_payload_address;

            // DMA_FRAME_TYPE_TICK
            assign tick_total_amount = r_dma_header_words[0][47:32];
            assign tick_delay = r_dma_header_words[1];

            // DMA_FRAME_TYPE_CORE_DATA
            assign core_data_idx = r_dma_header_words[0][32+$clog2(NUM_CORES)-1:32];
            assign core_data_byte_offset = r_dma_header_words[1];
            
            // DMA_FRAME_TYPE_RESET
            assign should_reset_tick_idx = r_dma_header_words[0][32];
            assign should_reset_network = r_dma_header_words[0][33];
            assign should_reset_model = r_dma_header_words[0][34];
        end
    endgenerate
    
    always @(posedge clk) begin
        if (!rst || acc_done) begin
            if (DEBUG) begin
                $display ("[RTL][spikehard_controller] reset");
            end // DEBUG
            
            acc_done <= 1'b0;
            read_valid <= 1'b0;
            write_valid <= 1'b0;
            rbuf_ready <= 1'b0;
            wbuf_valid <= 1'b0;
            next_read_byte_offset <= 0;
            next_write_byte_offset <= 0;
            w_has_ticked <= 1'b0;
            w_prev_tick_num_rem_packets <= 0;
            w_curr_tick_num_rem_packets <= 0;
            w_num_elapsed_ticks <= 0;
            opbuf_ren <= 1'b0;
            w_has_packet_to_send <= 1'b0;
            noop_amount <= 10000;
            noop_num_past_clk_posedge <= 0;
            tick_remaining_amount <= ~'0;
            clk_cycles_since_last_tick <= 0;
            tick <= 1'b0;
            tc_buf_rst <= 1'b0;
            csram_buf_rst <= 1'b0;
            tc_rem_words_to_read <= 0;
            csram_rem_words_to_read <= 0;
            rst_network <= 1'b0;
            rst_model <= 1'b1;
            reset_rem_cycles <= ~'0;
            tick_before_next_frame <= 1'b0;

            if (conf_done) begin
                next_write_byte_offset <= conf_info_tx_size;
                if (DEBUG) begin
                    $display ("[RTL][spikehard_controller] changing state to INIT_READ_HEADER");
                end // DEBUG
                exec_state <= INIT_READ_HEADER;
            end
            else begin
                if (DEBUG) begin
                    $display ("[RTL][spikehard_controller] changing state to IDLE");
                end // DEBUG
                exec_state <= IDLE;
            end
        end
        else begin
            if (!rst_network) begin
                clk_cycles_since_last_tick <= 0;
                w_prev_tick_num_rem_packets <= 0;
                w_curr_tick_num_rem_packets <= 0;
                w_has_packet_to_send <= 1'b0;
            end

            tick <= 1'b0;
            if (tick) begin
                w_num_elapsed_ticks <= w_num_elapsed_ticks + 1;
                w_has_ticked <= 1'b1;
                w_prev_tick_num_rem_packets <= w_curr_tick_num_rem_packets;
                w_curr_tick_num_rem_packets <= packet_out_valid;
                clk_cycles_since_last_tick <= 0;
            end
            else begin
                w_curr_tick_num_rem_packets <= w_curr_tick_num_rem_packets + packet_out_valid;
                if (clk_cycles_since_last_tick != ~'0) begin
                    clk_cycles_since_last_tick <= clk_cycles_since_last_tick + 1;
                end
            end

            noop_num_past_clk_posedge <= noop_num_past_clk_posedge + 1;

            case (exec_state)
                INIT_READ_HEADER: begin
                    if (rbuf_aligned) begin
                        if (read_valid && read_ready) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to READ_HEADER");
                            end // DEBUG
                            exec_state <= READ_HEADER;
                            next_read_byte_offset <= next_read_byte_offset + read_word_width * read_length;
                            words_read <= 0;
                            rbuf_ready <= 1'b1;
                            read_valid <= 1'b0;
                        end
                        else begin
                            read_valid <= 1'b1;
                            read_length <= DMA_HEADER_LENGTH;
                            read_word_width <= (HEADER_WORD_WIDTH >> 3);
                            read_byte_offset <= next_read_byte_offset;
                        end
                    end
                end
                READ_HEADER: begin
                    if (rbuf_ready && !rbuf_empty) begin
                        if (DEBUG) begin
                            $display ("[RTL][spikehard_controller] read word %d", rbuf_data[HEADER_WORD_WIDTH-1:0]);
                        end // DEBUG
                        r_dma_header_words[words_read] <= rbuf_data[HEADER_WORD_WIDTH-1:0];
                        words_read <= words_read + 1;
                        if (words_read == read_length - 1) begin
                            rbuf_ready <= 1'b0;
                            noop_num_past_clk_posedge <= 0;
                            if (DEBUG) begin
                                $display ("dma_frame_type: %d", dma_frame_type);
                            end // DEBUG
                        end
                    end
                    
                    if (words_read == read_length) begin
                        if (tick_before_next_frame) begin
                            tick_before_next_frame <= 1'b0;
                            if (dma_frame_type != DMA_FRAME_TYPE_TERMINATE) begin
                                tick <= 1'b1;
                            end
                        end

                        if (w_has_ticked || tick || tick_before_next_frame || w_curr_tick_num_rem_packets >= FLUSH_OUT_PACKET_BUFFER_THRESHOLD) begin
                            // Need to write to memory all output packets, and once finished we will
                            // automatically come back to this state and resume the read operation.
                            exec_state <= INIT_WRITE_HEADER_1;
                            w_exec_state_to_restore <= READ_HEADER;
                        end
                        else begin
                            case (dma_frame_type)
                                DMA_FRAME_TYPE_NOOP: begin
                                    // A no-op header is unique in that it will cause the controller to continuously (re)read this
                                    // header until it has been modified to something actionable. In particular, a no-op header is
                                    // meant to be overwritten. However, the user must modify the header atomically. Specifically,
                                    // the dma_frame_type bits should be overwritten last and atomically, which can be done easily
                                    // as dma_frame_type is less than 8 bits. The no-op header essentially implements busy waiting.
                                    // By default, no-op waits for 10 000 clock cycles to occur.

                                    if (noop_num_past_clk_posedge >= noop_amount) begin
                                        if (DEBUG) begin
                                            $display ("[RTL][spikehard_controller] no-op, changing state to INIT_READ_HEADER");
                                        end // DEBUG
                                        exec_state <= INIT_READ_HEADER;
                                        next_read_byte_offset <= next_read_byte_offset - read_word_width * read_length; // (re)read header
                                    end
                                end
                                DMA_FRAME_TYPE_NOOP_CONF: begin
                                    noop_amount <= noop_conf_amount;
                                    if (DEBUG) begin
                                        $display ("[RTL][spikehard_controller] noop_amount: %d", noop_conf_amount);
                                        $display ("[RTL][spikehard_controller] changing state to INIT_READ_HEADER");
                                    end // DEBUG
                                    exec_state <= INIT_READ_HEADER;
                                end
                                DMA_FRAME_TYPE_TERMINATE: begin
                                    if (DEBUG) begin
                                        $display ("[RTL][spikehard_controller] changing state to INIT_WRITE_TERMINATE_HEADER");
                                    end // DEBUG
                                    exec_state <= INIT_WRITE_TERMINATE_HEADER;
                                end
                                DMA_FRAME_TYPE_IN_PACKETS: begin
                                    if (DEBUG) begin
                                        $display ("in_packets_length: %d", in_packets_length);
                                        $display ("in_packets_byte_offset: %d", in_packets_byte_offset);
                                    end // DEBUG
                                    if (in_packets_length == 0) begin
                                        if (DEBUG) begin
                                            $display ("[RTL][spikehard_controller] no packets to read, changing state to INIT_READ_HEADER");
                                        end // DEBUG
                                        exec_state <= INIT_READ_HEADER;
                                    end
                                    else begin
                                        if (DEBUG) begin
                                            $display ("[RTL][spikehard_controller] changing state to INIT_READ_IN_PACKETS_PAYLOAD");
                                        end // DEBUG
                                        exec_state <= INIT_READ_IN_PACKETS_PAYLOAD;
                                    end
                                end
                                DMA_FRAME_TYPE_TICK: begin
                                    if (!tick_remaining_amount || !tick_total_amount) begin
                                        if (DEBUG) begin
                                            $display ("[RTL][spikehard_controller] changing state to INIT_READ_HEADER");
                                        end // DEBUG
                                        exec_state <= INIT_READ_HEADER;
                                        tick_remaining_amount <= ~'0;
                                    end
                                    else if (ipbuf_empty && clk_cycles_since_last_tick >= tick_delay && !tick) begin
                                        if (tick_total_amount == 1 || tick_remaining_amount == 1) begin
                                            tick_before_next_frame <= 1'b1;
                                        end
                                        else begin
                                            tick <= 1'b1;
                                        end
                                        if (tick_remaining_amount >= tick_total_amount) begin
                                            tick_remaining_amount <= tick_total_amount - 1;
                                            if (DEBUG) begin
                                                $display ("[RTL][spikehard_controller] tick_delay: %d", tick_delay);
                                                $display ("[RTL][spikehard_controller] tick_total_amount: %d", tick_total_amount);
                                            end // DEBUG
                                        end
                                        else begin
                                            tick_remaining_amount <= tick_remaining_amount - 1;
                                        end
                                    end
                                end
                                DMA_FRAME_TYPE_CORE_DATA: begin
                                    if (DEBUG) begin
                                        $display ("[RTL][spikehard_controller] changing state to INIT_READ_CORE_DATA_PAYLOAD");
                                    end // DEBUG
                                    exec_state <= INIT_READ_CORE_DATA_PAYLOAD;
                                end
                                DMA_FRAME_TYPE_RESET: begin
                                    if (reset_rem_cycles) begin
                                        reset_rem_cycles <= reset_rem_cycles - 1;
                                        if (should_reset_tick_idx) begin
                                            w_tick_idx <= 0;
                                            w_num_elapsed_ticks <= 0;
                                            w_has_ticked <= 1'b0;
                                        end
                                        rst_network <= !should_reset_network;
                                        rst_model <= !should_reset_model;
                                        if (DEBUG) begin
                                            $display ("[RTL][spikehard_controller] resetting tick_idx: %b, network: %b, model: %b", should_reset_tick_idx, should_reset_network, should_reset_model);
                                        end // DEBUG
                                    end
                                    else begin
                                        rst_network <= 1'b1;
                                        rst_model <= 1'b1;

                                        if (clk_cycles_since_last_tick > NUM_TICKS) begin
                                            if (DEBUG) begin
                                                $display ("[RTL][spikehard_controller] done resetting, changing state to INIT_READ_HEADER");
                                            end // DEBUG
                                            exec_state <= INIT_READ_HEADER;
                                            reset_rem_cycles <= ~'0;
                                        end
                                    end
                                end
                            endcase
                        end
                    end
                end
                INIT_READ_IN_PACKETS_PAYLOAD: begin
                    if (rbuf_aligned) begin
                        if (read_valid && read_ready) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to READ_IN_PACKETS_PAYLOAD");
                            end // DEBUG
                            exec_state <= READ_IN_PACKETS_PAYLOAD;
                            next_read_byte_offset <= (((in_packets_byte_offset + read_word_width * read_length - 1) | ((DMA_BUS_WIDTH >> 3)-1))+1);
                            words_read <= 0;
                            rbuf_ready <= !ipbuf_almost_full;
                            read_valid <= 1'b0;
                        end
                        else begin
                            read_valid <= 1'b1;
                            read_length[63:32] <= 0;
                            read_length[31:0] <= in_packets_length;
                            read_word_width <= (IN_PACKETS_PAYLOAD_WORD_WIDTH >> 3);
                            read_byte_offset <= in_packets_byte_offset;
                        end
                    end
                end
                READ_IN_PACKETS_PAYLOAD: begin
                    rbuf_ready <= !ipbuf_almost_full;
                    if (rbuf_ready && !rbuf_empty) begin
                        if (DEBUG) begin
                            $display ("[RTL][spikehard_controller] read word %d", rbuf_data[PACKET_WIDTH-1:0]);          
                        end // DEBUG
                        words_read <= words_read + 1;
                        if (words_read == read_length - 1) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to INIT_READ_HEADER");
                            end // DEBUG
                            exec_state <= INIT_READ_HEADER;
                            rbuf_ready <= 1'b0;
                        end
                    end
                end
                INIT_READ_CORE_DATA_PAYLOAD: begin
                    tc_rem_words_to_read <= NUM_AXONS;
                    csram_rem_words_to_read <= NUM_NEURONS;
                    words_read <= 0;

                    if (rbuf_aligned) begin
                        if (read_valid && read_ready) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to READ_CORE_DATA_PAYLOAD");
                            end // DEBUG
                            exec_state <= READ_CORE_DATA_PAYLOAD;
                            next_read_byte_offset <= (((core_data_byte_offset + read_word_width * read_length - 1) | ((DMA_BUS_WIDTH >> 3)-1))+1);
                            rbuf_ready <= !tc_w_close_to_full && !csram_w_close_to_full;
                            read_valid <= 1'b0;

                            tc_buf_rst <= 1'b1;
                            tc_core_idx <= core_data_idx;
                            tc_addr <= 0;

                            csram_buf_rst <= 1'b1;
                            csram_core_idx <= core_data_idx;
                            csram_addr <= 0;
                        end
                        else begin
                            read_valid <= 1'b1;
                            read_length <= TC_NUM_WORDS + CSRAM_NUM_WORDS;
                            read_word_width <= (CORE_DATA_PAYLOAD_WORD_WIDTH >> 3);
                            read_byte_offset <= core_data_byte_offset;
                        end
                    end
                end
                READ_CORE_DATA_PAYLOAD: begin
                    rbuf_ready <= (words_read >= TC_NUM_WORDS) ? !csram_w_close_to_full : !tc_w_close_to_full;

                    if (tc_valid) begin
                        tc_addr <= tc_addr + 1;
                        tc_rem_words_to_read <= tc_rem_words_to_read - 1;
                    end
                    if (csram_valid) begin
                        csram_addr <= csram_addr + 1;
                        csram_rem_words_to_read <= csram_rem_words_to_read - 1;
                    end

                    if (rbuf_ready && !rbuf_empty) begin
                        words_read <= words_read + 1;
                        if (words_read == read_length - 1) begin
                            rbuf_ready <= 1'b0;
                        end
                    end
                    if (words_read == read_length && !tc_rem_words_to_read && !csram_rem_words_to_read) begin
                        if (DEBUG) begin
                            $display ("[RTL][spikehard_controller] changing state to INIT_READ_HEADER");
                        end // DEBUG
                        exec_state <= INIT_READ_HEADER;
                        tc_buf_rst <= 1'b0;
                        csram_buf_rst <= 1'b0;
                        clk_cycles_since_last_tick <= 0;
                    end
                end
                INIT_WRITE_HEADER_1: begin
                    exec_state <= INIT_WRITE_HEADER_2;
                    w_has_ticked <= 1'b0;
                    if (w_has_ticked) begin
                        w_tick_idx <= w_num_elapsed_ticks - 1;
                        w_num_packets <= w_prev_tick_num_rem_packets;
                    end
                    else begin
                        w_tick_idx <= w_num_elapsed_ticks;
                        w_num_packets <= w_curr_tick_num_rem_packets + packet_out_valid;
                        w_curr_tick_num_rem_packets <= 0;
                    end
                end
                INIT_WRITE_HEADER_2: begin
                    if (wbuf_aligned) begin
                        if (write_valid && write_ready) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to WRITE_HEADER");
                            end // DEBUG
                            exec_state <= WRITE_HEADER;
                            next_write_byte_offset <= next_write_byte_offset + write_word_width * write_length;
                            w_payload_address <= next_write_byte_offset + write_word_width * write_length; // same as next_write_byte_offset
                            words_written <= 0;
                            write_valid <= 1'b0;
                        end
                        else begin
                            write_valid <= 1'b1;
                            write_length <= DMA_HEADER_LENGTH;
                            write_word_width <= (HEADER_WORD_WIDTH >> 3);
                            write_byte_offset <= next_write_byte_offset;
                        end
                    end
                end
                WRITE_HEADER: begin
                    wbuf_valid <= 1'b0;
                    if (!wbuf_full && words_written < write_length) begin
                        if (DEBUG) begin
                            $display ("[RTL][spikehard_controller] write word %d", w_dma_header_words[words_written]);
                        end // DEBUG
                        wbuf_data[HEADER_WORD_WIDTH-1:0] <= w_dma_header_words[words_written];
                        words_written <= words_written + 1;
                        wbuf_valid <= 1'b1;
                    end
                    else if (wbuf_full) begin
                        if (wbuf_valid) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] failed to write word %d", wbuf_data);
                            end // DEBUG
                            words_written <= words_written - 1;
                        end
                    end
                    else if (words_written == write_length) begin
                        if (w_num_packets) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to INIT_WRITE_OUT_PACKETS_PAYLOAD");
                            end // DEBUG
                            exec_state <= INIT_WRITE_OUT_PACKETS_PAYLOAD;
                        end
                        else begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] empty payload, restoring state");
                            end // DEBUG
                            exec_state <= w_exec_state_to_restore;
                        end
                    end
                end
                INIT_WRITE_OUT_PACKETS_PAYLOAD: begin
                    if (wbuf_aligned) begin
                        if (write_valid && write_ready) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to WRITE_OUT_PACKETS_PAYLOAD");
                            end // DEBUG
                            exec_state <= WRITE_OUT_PACKETS_PAYLOAD;
                            next_write_byte_offset <= next_write_byte_offset + write_word_width * write_length;
                            words_written <= 0;
                            write_valid <= 1'b0;
                        end
                        else begin
                            write_valid <= 1'b1;
                            if (DMA_BUS_WIDTH > OUT_PACKETS_PAYLOAD_WORD_WIDTH) begin
                                // account for pad words
                                write_length <= ((w_num_packets-1) | ((DMA_BUS_WIDTH / OUT_PACKETS_PAYLOAD_WORD_WIDTH)-1))+1;
                            end
                            else begin
                                write_length <= w_num_packets;
                            end
                            write_word_width <= (OUT_PACKETS_PAYLOAD_WORD_WIDTH >> 3);
                            write_byte_offset <= next_write_byte_offset;
                        end
                    end
                end
                WRITE_OUT_PACKETS_PAYLOAD: begin
                    wbuf_valid <= 1'b0;
                    if (!wbuf_full && words_written < write_length) begin
                        if (words_written >= w_num_packets) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] writing pad word");
                            end // DEBUG
                            wbuf_data <= 0;
                            words_written <= words_written + 1;
                            wbuf_valid <= 1'b1;
                        end
                        else begin
                            if (w_has_packet_to_send) begin
                                if (DEBUG) begin
                                    $display ("[RTL][spikehard_controller] write word %d", opbuf_dout);
                                end // DEBUG
                                if (OUT_PACKETS_PAYLOAD_WORD_WIDTH != OUT_PACKET_WIDTH) begin
                                    wbuf_data[(OUT_PACKETS_PAYLOAD_WORD_WIDTH == OUT_PACKET_WIDTH) ? OUT_PACKET_WIDTH : (OUT_PACKETS_PAYLOAD_WORD_WIDTH-1):OUT_PACKET_WIDTH] <= 0;
                                end
                                wbuf_data[OUT_PACKET_WIDTH-1:0] <= opbuf_dout;
                                words_written <= words_written + 1;
                                w_has_packet_to_send <= 1'b0;
                                wbuf_valid <= 1'b1;
                            end
                            else begin
                                opbuf_ren <= !opbuf_ren;
                                w_has_packet_to_send <= opbuf_ren;
                            end
                        end
                    end
                    else if (wbuf_full) begin
                        if (wbuf_valid) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] failed to write word %d", wbuf_data);
                            end // DEBUG
                            words_written <= words_written - 1;
                            w_has_packet_to_send <= 1'b1;
                        end
                    end
                    else if (words_written == write_length) begin
                        if (DEBUG) begin
                            $display ("[RTL][spikehard_controller] restoring state");
                        end // DEBUG
                        exec_state <= w_exec_state_to_restore;
                    end
                end
                INIT_WRITE_TERMINATE_HEADER: begin
                    if (wbuf_aligned) begin
                        if (write_valid && write_ready) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] changing state to WRITE_TERMINATE_HEADER");
                            end // DEBUG
                            exec_state <= WRITE_TERMINATE_HEADER;
                            next_write_byte_offset <= next_write_byte_offset + write_word_width * write_length;
                            words_written <= 0;
                            write_valid <= 1'b0;
                        end
                        else begin
                            write_valid <= 1'b1;
                            write_length <= DMA_HEADER_LENGTH;
                            write_word_width <= (HEADER_WORD_WIDTH >> 3);
                            write_byte_offset <= next_write_byte_offset;
                        end
                    end
                end
                WRITE_TERMINATE_HEADER: begin
                    wbuf_valid <= 1'b0;
                    if (!wbuf_full && words_written < write_length) begin
                        if (words_written == 0) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] write word %d", DMA_FRAME_TYPE_TERMINATE);
                            end // DEBUG
                            wbuf_data[DMA_FRAME_TYPE_WIDTH-1:0] <= DMA_FRAME_TYPE_TERMINATE;
                            wbuf_data[DMA_FRAME_TYPE_WIDTH+1:DMA_FRAME_TYPE_WIDTH] <= err_latch_;
                            wbuf_data[HEADER_WORD_WIDTH-1:DMA_FRAME_TYPE_WIDTH+2] <= 0;
                        end
                        else begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] write word %d", 0);
                            end // DEBUG
                            wbuf_data[HEADER_WORD_WIDTH-1:0] <= 0;
                        end
                        words_written <= words_written + 1;
                        wbuf_valid <= 1'b1;
                    end
                    else if (wbuf_full) begin
                        if (wbuf_valid) begin
                            if (DEBUG) begin
                                $display ("[RTL][spikehard_controller] failed to write word %d", wbuf_data);
                            end // DEBUG
                            words_written <= words_written - 1;
                        end
                    end
                    else if (words_written == write_length) begin
                        if (DEBUG) begin
                            $display ("[RTL][spikehard_controller] changing state to DONE");
                        end // DEBUG
                        exec_state <= DONE;
                    end
                end
                DONE: begin
                    if (read_ready && write_ready) begin
                        acc_done <= 1'b1;
                    end
                end
                IDLE: begin
                    if (conf_done) begin
                        next_write_byte_offset <= conf_info_tx_size;
                        if (DEBUG) begin
                            $display ("[RTL][spikehard_controller] changing state to INIT_READ_HEADER");
                        end // DEBUG
                        exec_state <= INIT_READ_HEADER;
                    end
                end
            endcase
        end
    end

    assign dma_to_ipbuf_valid = rbuf_ready && !rbuf_empty && (exec_state == READ_IN_PACKETS_PAYLOAD);
    assign dma_to_ipbuf = rbuf_data[PACKET_WIDTH-1:0];
    assign rbuf_data_width = read_word_width;
    assign wbuf_data_width = write_word_width;

    assign tc_r_ready = 1'b1;
    assign tc_w_valid = rbuf_ready && !rbuf_empty && (exec_state == READ_CORE_DATA_PAYLOAD) && (words_read < TC_NUM_WORDS);
    assign tc_valid = tc_r_ready && !tc_r_empty && (exec_state == READ_CORE_DATA_PAYLOAD) && tc_rem_words_to_read;

    assign csram_r_ready = 1'b1;
    assign csram_w_valid = rbuf_ready && !rbuf_empty && (exec_state == READ_CORE_DATA_PAYLOAD) && (words_read >= TC_NUM_WORDS);
    assign csram_valid = csram_r_ready && !csram_r_empty && (exec_state == READ_CORE_DATA_PAYLOAD) && csram_rem_words_to_read;

endmodule
