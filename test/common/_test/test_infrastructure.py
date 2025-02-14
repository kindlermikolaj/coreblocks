from amaranth import *
from test.common import *


class EmptyCircuit(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()
        return m


class TestNow(TestCaseWithSimulator):
    def setUp(self):
        self.test_cycles = 10
        self.m = SimpleTestCircuit(EmptyCircuit())

    def process(self):
        for k in range(self.test_cycles):
            now = yield Now()
            assert k == now
            # check if second call don't change the returned value
            now = yield Now()
            assert k == now

            yield

    def test_random(self):
        with self.run_simulation(self.m, 50) as sim:
            sim.add_sync_process(self.process)
