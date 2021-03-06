# !/usr/bin/env python3
# This is the module for testing the RLEmain.

from litex.gen import *

from litex.soc.interconnect.stream import *
from litex.soc.interconnect.stream_sim import *

from litejpeg.core.common import *
from litejpeg.core.rle.rlemain import RLEMain

from common import *

class TB(Module):
    def __init__(self):
        # Making pipeline and the getting the RLEmain module.
        """
        Streamer : It will pass the input to the entropycoder.
                   The data is a 12 bit number in the matrix.

        Logger : It will get the output to the TestBench.
                 Is a 22 bit number.
                 data[0:12] amplitude
                 data[12:16] Size
                 data[16:20] Runlength
                 data[21] dvalid
        """
        self.submodules.streamer = PacketStreamer(EndpointDescription([("data", 12)]))
        self.submodules.rlemain = RLEMain()
        self.submodules.logger = PacketLogger(EndpointDescription([("data", 21)]))

        # Connecting TestBench with the Entropycoder module.
        self.comb += [
            self.streamer.source.connect(self.rlemain.sink),
            self.rlemain.source.connect(self.logger.sink)
        ]


def main_generator(dut):

    # Results from the reference modules:
    model = RLE()
    print("The Input Module:")
    print(model.red_pixels_1)

    # Results from the implemented module.
    model2 = RLE()
    packet = Packet(model2.red_pixels_1)
    for i in range(1):
        dut.streamer.send(packet)
        yield from dut.logger.receive()
        print("\n")
        print("Output of the RLEmain module:")
        model2.set_rledata(dut.logger.packet)

# Going through the main module
if __name__ == "__main__":
    tb = TB()
    generators = {"sys" : [main_generator(tb)]}
    generators = {
        "sys" :   [main_generator(tb),
                   tb.streamer.generator(),
                   tb.logger.generator()]
    }
    clocks = {"sys": 10}
    run_simulation(tb, generators, clocks, vcd_name="sim.vcd")
