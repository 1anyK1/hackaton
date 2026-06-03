cmake_minimum_required(VERSION 3.16)
project(task4_pluto_walkie_talkie LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(pluto_walkie_cpp
    cpp/main.cpp
)

target_link_libraries(pluto_walkie_cpp PRIVATE dl pthread)

if (MSVC)
    target_compile_options(pluto_walkie_cpp PRIVATE /W4)
else()
    target_compile_options(pluto_walkie_cpp PRIVATE -Wall -Wextra -Wpedantic)
endif()
