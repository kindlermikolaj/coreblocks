# Makefile

# defaults
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# TOPLEVEL is the name of the toplevel module in your Verilog or VHDL file
TOPLEVEL = top

# MODULE is the basename of the Python test file
MODULE = benchmark_entrypoint

SIM_BUILD = build/benchmark

# Yosys/Amaranth borkedness workaround
ifeq ($(SIM),verilator)
  EXTRA_ARGS += -Wno-CASEINCOMPLETE -Wno-CASEOVERLAP -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC
endif

ifeq ($(TRACES),1)
  EXTRA_ARGS += --trace-fst --trace-structs
endif

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim

