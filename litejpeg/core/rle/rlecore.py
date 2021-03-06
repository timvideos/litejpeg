"""
RLE Core Module:
----------------
This module is the core module for the RLE for calculating
the amplitude and the zero_count of the input data.
amplitudes are the non-zero elements present in the matrix
and zero_count is the number of zeros before the non-zero
amplitude.
This helps is the reduction of data as no more memory is
required to store all the zeros instead a runlength is
sufficient for storing all the zeros.
"""

from litex.gen import *
from litex.soc.interconnect.stream import *

from litejpeg.core.common import *

# To provide delay so in order to sink the data coming from the main
# module to that of the Datapath module.
datapath_latency = 3


# CEInseter genenrates an additional instance named as self.ce
# This is used so that to provide an additional clock attached to the
# pipeline Actor in the main module.
@CEInserter()


class RLEDatapath(Module):
    """
    RLEDatapath Module:
    -------------------
    This module is the datapath set for the steps required for
    the RLE module to take place.

    The input matrix contains two components,
    * the first value of the matrix is called as the DC component and
    * the rest of the values within the matrix are the AC component.

    The DC part is been encoded by subtracting the DC cofficient to that of
    the DC cofficient of the previous value of the DC matrix.

    The AC cofficients are been encoded by calculating the number of zeros
    before the non-zero AC cofficient called as the runlength.

    Their is a need of seperate DC/AC cofficients because as the first element
    of the matrix is the DC cofficient so we already know that the
    runlength value for DC = 0
    Therefore while doing huffman encoding we do not want to waste our
    memory saying the runlength to be zero, that why we take it separate
    from the rest of the AC cofficients.

    Attributes:
    -----------
    dovalid : indicate wheather the output data is valid or not.

    sink : To take the input data to the Datapath module.

    source : To transfer the output data to the Datapath module.
    """
    def __init__(self):

        """
        Intialising the variable for the Datapath module.
        """

        self.sink = sink = Record(block_layout(12))
        self.source = source = Record(block_layout(18))
        self.source_inter = source_inter = Record(block_layout(18))
        self.write_cnt = Signal(6)

        accumulator = Signal(12)
        accumulator_temp = Signal(12)
        runlength = Signal(12)
        self.dovalid = Signal(1)
        self.dovalid_next = Signal(1)
        self.dovalid_next_next = Signal(1)

        zero_count = Signal(4)
        prev_dc_0 = Signal(12)

        # For calculating the runlength values.
        self.sync += [

           If(self.write_cnt == 0,
              # If the write_cnt is zero then it is the starting of a new data
              # hence the value of the runlength will be zero directly.
              # Since the DC encoding is been done by subtracting
              # the present value with the previous value, hence the
              # DC cofficient is been stored in the prev_dc_0.
              # After doing all making the dovalid equal to 1.
              accumulator.eq(sink.data - prev_dc_0),
              accumulator_temp.eq(accumulator),
              prev_dc_0.eq(sink.data),
              runlength.eq(0),
              accumulator_temp.eq(accumulator_temp + (-2)*accumulator_temp[11]*accumulator),
              self.dovalid.eq(1)
              ).Else(
                 If(sink.data == 0,
                    If(zero_count == 15,
                       accumulator.eq(0),
                       runlength.eq(15),
                       zero_count.eq(zero_count+1),
                       self.dovalid.eq(1)
                       ).Else(
                          If(self.write_cnt == 63,
                             # If the data is zero and it is the end of the
                             # matrix then the output is generated to be with
                             # amplitude = 0 and runlength=0 this will
                             # automatically indicate the end of the matrix.
                             accumulator.eq(0),
                             runlength.eq(0),
                             self.dovalid.eq(1)
                             ).Else(
                                  # Otherwise if zero is encountered in between
                                  # then the only contribution is
                                  # to increase the count of zero_count by 1.
                                  zero_count.eq(zero_count+1),
                                  self.dovalid.eq(0)))
                    ).Else(
                       # Else if a non-zero AC cofficient is detected then the
                       # output is been generated with the amplitude equal to
                       # that of the AC cofficient and the number of zeros are
                       # been indicated as the runlength.
                       # Making the dvalid to be 1.
                       accumulator.eq(sink.data),
                       runlength.eq(zero_count),
                       zero_count.eq(0),
                       accumulator_temp.eq(accumulator + (-2*accumulator[11]*accumulator)),
                       self.dovalid.eq(1)))
        ]

        self.sync += [
            self.dovalid_next.eq(self.dovalid),
            self.dovalid_next_next.eq(self.dovalid_next),
        ]

        self.sync += [

            # Connecting the Datapath module to the main module.
            self.source_inter.data[0:12].eq(accumulator),
            self.source_inter.data[12:16].eq(runlength),
            self.source_inter.data[16].eq(self.dovalid)

        ]

        self.sync += [
            self.source.data.eq(self.source_inter.data)
        ]


class RunLength(PipelinedActor, Module):
    """
    This module will connect the RLE core datapath with the input
    and output either from other modules or from the Test Benches.
    The input is been taken from the sink and source and is been
    transferred to the RLE core datapath by using read and write count.
    The RLEDatapath will than calculate the number of zeros between two
    consecutive non-zero numbers and give the output as runlength.

    Attributes :
    ------------
    sink : 12 bits
           receives data from the RLEmain containing the amplitude.
    source : 17 bits
             transmit output to the RLEmain
             12 bits : amplitude
             4 bits : runlength
             1 bit : data_valid
    """
    def __init__(self):

        # Connecting the module to the input and the output.
        self.sink = sink = stream.Endpoint(
                               EndpointDescription(block_layout(12)))
        self.source = source = stream.Endpoint(
                                   EndpointDescription(block_layout(17)))

        # Adding PipelineActor to provide additional clock for the module.
        # This clock is useful to compensate the latency caused by the
        # datapath to process the first input.
        PipelinedActor.__init__(self, datapath_latency)
        self.latency = datapath_latency

        # Connecting RLE submodule.
        self.submodules.datapath = RLEDatapath()
        self.comb += self.datapath.ce.eq(self.pipe_ce)

        BLOCK_COUNT = 64
        # Check wheather to start write or not.
        write_sel = Signal()
        # To swap the write select.
        write_swap = Signal()
        # Check wheather to start read or not.
        read_sel = Signal(reset=1)
        # To swap the read_sel.
        read_swap = Signal()

        # read_swap and write_swap will keep on changing depending on the value
        # of the read and write select which further change the states of the FSM
        # to synchronize between reading and writing input.
        self.sync += [
            If(write_swap,
               write_sel.eq(~write_sel)),
            If(read_swap,
               read_sel.eq(~read_sel))
        ]

        # write path

        # To start the write_count back to 0.
        write_clear = Signal()
        # To increment the write_count.
        write_inc = Signal()
        # To keep track over which value of the matrix is under process.
        write_count = Signal(6)

        # For tracking the data adress.
        self.sync += \
            If(write_clear,
                write_count.eq(0)
            ).Elif(write_inc,
                write_count.eq(write_count + 1)
            )

        # To combine the datapath into the module
        self.comb += [
            self.datapath.write_cnt.eq(write_count),
            self.datapath.sink.data.eq(sink.data)
        ]

        """
        INIT

        Depending on the value of the read_sel and write_sel decide
        wheather the next state will be either read or write.
        Will clear the value of ``write_count`` to be 0.
        """
        self.submodules.write_fsm = write_fsm = FSM(reset_state="INIT")
        write_fsm.act("INIT",
                      write_clear.eq(1),
                      If(write_sel != read_sel,
                         NextState("WRITE_INPUT")))

        """
        WRITE_INPUT State

        Will increament the value of the write_count at every positive
        edge of the clock cycle till BLOCK_COUNT and write the data into the memory
        as per the data from the ``sink.data`` and when the value reaches
        BLOCK_COUNT the state again changes to that of the IDLE state.
        """
        write_fsm.act("WRITE_INPUT",
                      sink.ready.eq(1),
                      If(sink.valid,
                         If(write_count == BLOCK_COUNT-1,
                             write_swap.eq(1),
                             NextState("INIT")
                         ).Else(
                             write_inc.eq(1)
                         )
                      ))

        # read path

        # Intialising the values.
        read_clear = Signal()
        read_inc = Signal()
        read_count = Signal(6)

        # For keeping track of the adress by using the read_count.
        self.sync += \
            If(read_clear,
                read_count.eq(0)
            ).Elif(read_inc,
                read_count.eq(read_count + 1))

        # Reading the input from the Datapath only when
        # the output data is valid.
        self.comb += [
            If(self.datapath.dovalid_next_next,
               source.data.eq(self.datapath.source.data))
        ]

        # GET_RESET state
        self.submodules.read_fsm = read_fsm = FSM(reset_state="INIT")
        read_fsm.act("INIT",
                     read_clear.eq(1),
                     If(read_sel == write_sel,
                        read_swap.eq(1),
                        NextState("READ_OUTPUT")))

        """
        READ_INPUT state

        Will increament the value of the read_count at every positive edge
        of the clock cycle till BLOCK_COUNT and read the data from the memory,
        giving it to the ``source.data`` as input and when the value
        reaches BLOCK_COUNT the state again changes to that of the IDLE state.
        """
        read_fsm.act("READ_OUTPUT",
                     source.valid.eq(1),
                     source.last.eq(read_count == BLOCK_COUNT-1),
                     If(source.ready,
                         read_inc.eq(1),
                         If(source.last,
                             NextState("INIT")
                         )
                      ))
