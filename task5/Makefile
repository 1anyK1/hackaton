CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic

SRC := src/main.cpp src/correlation.cpp src/iq_io.cpp src/protocol.cpp
BIN := build/rc_car_tool

.PHONY: all clean

all: $(BIN)

$(BIN): $(SRC)
	mkdir -p build
	$(CXX) $(CXXFLAGS) $(SRC) -Isrc -o $(BIN)

clean:
	rm -rf build generated captures
