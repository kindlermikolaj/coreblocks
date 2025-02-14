from amaranth import *
from transactron.core import Priority
from transactron.lib import BasicFifo, Semaphore
from coreblocks.frontend.icache import ICacheInterface
from coreblocks.frontend.rvc import InstrDecompress, is_instr_compressed
from transactron import def_method, Method, Transaction, TModule
from ..params import *


class Fetch(Elaboratable):
    """
    Simple fetch unit. It has a PC inside and increments it by `isa.ilen_bytes`
    after each fetch.
    """

    def __init__(self, gen_params: GenParams, icache: ICacheInterface, cont: Method) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        icache : ICacheInterface
            Instruction Cache
        cont : Method
            Method which should be invoked to send fetched data to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gen_params = gen_params
        self.icache = icache
        self.cont = cont

        self.resume = Method(i=self.gen_params.get(FetchLayouts).resume)
        self.stall_exception = Method()
        # Fetch can be resumed to unstall from 'unsafe' instructions, and stalled because
        # of exception report, both can happen at any time during normal excecution.
        # ExceptionCauseRegister uses separate Transaction for it, so performace is not affected.
        self.stall_exception.add_conflict(self.resume, Priority.LEFT)

        # PC of the last fetched instruction. For now only used in tests.
        self.pc = Signal(self.gen_params.isa.xlen)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.fetch_target_queue = self.fetch_target_queue = BasicFifo(
            layout=[("addr", self.gen_params.isa.xlen), ("spin", 1)], depth=2
        )

        speculative_pc = Signal(self.gen_params.isa.xlen, reset=self.gen_params.start_pc)

        stalled = Signal()
        stalled_unsafe = Signal()
        stalled_exception = Signal()
        spin = Signal()

        m.d.av_comb += stalled.eq(stalled_unsafe | stalled_exception)

        with Transaction().body(m, request=~stalled):
            self.icache.issue_req(m, addr=speculative_pc)
            self.fetch_target_queue.write(m, addr=speculative_pc, spin=spin)

            m.d.sync += speculative_pc.eq(speculative_pc + self.gen_params.isa.ilen_bytes)

        def stall(exception=False):
            if exception:
                m.d.sync += stalled_exception.eq(1)
            else:
                m.d.sync += stalled_unsafe.eq(1)
            with m.If(~stalled):
                m.d.sync += spin.eq(~spin)

        with Transaction().body(m):
            target = self.fetch_target_queue.read(m)
            res = self.icache.accept_res(m)

            opcode = res.instr[2:7]
            # whether we have to wait for the retirement of this instruction before we make futher speculation
            unsafe_instr = opcode == Opcode.SYSTEM

            with m.If(spin == target.spin):
                instr = Signal(self.gen_params.isa.ilen)
                fetch_error = Signal()

                with m.If(res.error):
                    # TODO: Raise different code for page fault when supported
                    stall()
                    m.d.comb += fetch_error.eq(1)
                with m.Else():
                    with m.If(unsafe_instr):
                        stall()

                    m.d.sync += self.pc.eq(target.addr)
                    m.d.comb += instr.eq(res.instr)

                self.cont(m, instr=instr, pc=target.addr, access_fault=fetch_error, rvc=0)

        @def_method(m, self.resume, ready=stalled)
        def _(pc: Value, resume_from_exception: Value):
            m.d.sync += speculative_pc.eq(pc)
            m.d.sync += stalled_unsafe.eq(0)
            with m.If(resume_from_exception):
                m.d.sync += stalled_exception.eq(0)

        @def_method(m, self.stall_exception)
        def _():
            stall(exception=True)

        return m


class UnalignedFetch(Elaboratable):
    """
    Simple fetch unit that works with unaligned and RVC instructions.
    """

    def __init__(self, gen_params: GenParams, icache: ICacheInterface, cont: Method) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        icache : ICacheInterface
            Instruction Cache
        cont : Method
            Method which should be invoked to send fetched data to the next step.
            It has layout as described by `FetchLayout`.
        """
        self.gen_params = gen_params
        self.icache = icache
        self.cont = cont

        self.resume = Method(i=self.gen_params.get(FetchLayouts).resume)
        self.stall_exception = Method()
        self.stall_exception.add_conflict(self.resume, Priority.LEFT)

        # PC of the last fetched instruction. For now only used in tests.
        self.pc = Signal(self.gen_params.isa.xlen)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.req_limiter = req_limiter = Semaphore(2)

        m.submodules.decompress = decompress = InstrDecompress(self.gen_params)

        cache_req_pc = Signal(self.gen_params.isa.xlen, reset=self.gen_params.start_pc)
        current_pc = Signal(self.gen_params.isa.xlen, reset=self.gen_params.start_pc)

        flushing = Signal()
        stalled = Signal()
        stalled_unsafe = Signal()
        stalled_exception = Signal()
        m.d.av_comb += stalled.eq(stalled_unsafe | stalled_exception)

        with Transaction().body(m, request=~stalled):
            aligned_pc = Cat(C(0, 2), cache_req_pc[2:])
            self.icache.issue_req(m, addr=aligned_pc)
            req_limiter.acquire(m)

            m.d.sync += cache_req_pc.eq(cache_req_pc + 4)

        with m.If(req_limiter.count == 0):
            m.d.sync += flushing.eq(0)

        half_instr_buff = Signal(16)
        half_instr_buff_v = Signal()

        with Transaction().body(m):
            fetching_now = Signal()
            m.d.top_comb += fetching_now.eq(~(half_instr_buff_v & is_instr_compressed(half_instr_buff)))
            with m.If(fetching_now):
                cache_resp = self.icache.accept_res(m)
                req_limiter.release(m)

            is_unaligned = current_pc[1]
            resp_upper_half = cache_resp.instr[16:]
            resp_lower_half = cache_resp.instr[:16]
            resp_first_half = Mux(is_unaligned, resp_upper_half, resp_lower_half)
            resp_valid = ~flushing & (cache_resp.error == 0)
            is_resp_upper_rvc = Signal()
            m.d.top_comb += is_resp_upper_rvc.eq(is_instr_compressed(resp_upper_half))

            instr_lo_half = Signal(16)
            m.d.top_comb += instr_lo_half.eq(Mux(half_instr_buff_v, half_instr_buff, resp_first_half))
            m.d.top_comb += decompress.instr_in.eq(instr_lo_half)

            is_rvc = is_instr_compressed(instr_lo_half)

            full_instr = Mux(half_instr_buff_v, Cat(half_instr_buff, resp_lower_half), cache_resp.instr)

            instr = Signal(32)
            m.d.top_comb += instr.eq(Mux(is_rvc, decompress.instr_out, full_instr))

            opcode = instr[2:7]
            # whether we have to wait for the retirement of this instruction before we make futher speculation
            unsafe_instr = opcode == Opcode.SYSTEM

            # Check if we are ready to dispatch an instruction in the current cycle.
            # This can happen in three situations:
            # - we have a half of the instruction in the buffer, so either it is a compressed
            #   instruction or we have just fetched another half,
            # - the instruction is aligned, so we fetched the whole,
            # - the instruction is unaligned, but it is a compressed instruction.
            ready_to_dispatch = half_instr_buff_v | ~is_unaligned | is_resp_upper_rvc

            # We have to store the upper half of the response if the current
            # response from the cache is valid and either:
            # - we fetched the first half of an unaligned instruction and it is not compressed,
            # - we fetched an aligned instruction, but the lower half is compressed,
            # - we have already something in the buffer (meaning that now we are completing the previous instruction).
            m.d.sync += half_instr_buff_v.eq(
                resp_valid
                & fetching_now
                & (
                    (is_unaligned & ~is_resp_upper_rvc)
                    | (~is_unaligned & is_instr_compressed(resp_lower_half))
                    | half_instr_buff_v
                )
            )
            m.d.sync += half_instr_buff.eq(resp_upper_half)

            with m.If((resp_valid & ready_to_dispatch) | (cache_resp.error & ~stalled)):
                with m.If(unsafe_instr | cache_resp.error):
                    m.d.sync += stalled_unsafe.eq(1)
                    m.d.sync += flushing.eq(1)

                m.d.sync += self.pc.eq(current_pc)
                with m.If(~cache_resp.error):
                    m.d.sync += current_pc.eq(current_pc + Mux(is_rvc, C(2, 3), C(4, 3)))

                self.cont(m, instr=instr, pc=current_pc, access_fault=cache_resp.error, rvc=is_rvc)

        @def_method(m, self.resume, ready=(stalled & ~flushing))
        def _(pc: Value, resume_from_exception: Value):
            m.d.sync += cache_req_pc.eq(pc)
            m.d.sync += current_pc.eq(pc)
            m.d.sync += stalled_unsafe.eq(0)
            with m.If(resume_from_exception):
                m.d.sync += stalled_exception.eq(0)

        @def_method(m, self.stall_exception)
        def _():
            m.d.sync += stalled_exception.eq(1)
            m.d.sync += flushing.eq(1)

        return m
