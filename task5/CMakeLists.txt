cmake_minimum_required(VERSION 3.16)
project(task5_rc_car_hackrf LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(rc_car_tool
    src/main.cpp
    src/correlation.cpp
    src/iq_io.cpp
    src/protocol.cpp
)

target_include_directories(rc_car_tool PRIVATE src)

if (MSVC)
    target_compile_options(rc_car_tool PRIVATE /W4)
else()
    target_compile_options(rc_car_tool PRIVATE -Wall -Wextra -Wpedantic)
endif()
