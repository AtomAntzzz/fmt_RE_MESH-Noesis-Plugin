cmake_minimum_required(VERSION 3.19)
project(pragmata_gdeflate LANGUAGES C CXX)

set(DIRECTSTORAGE_ROOT "" CACHE PATH "Pinned microsoft/DirectStorage checkout")
if(NOT EXISTS "${DIRECTSTORAGE_ROOT}/GDeflate/GDeflate/GDeflate.h")
  message(FATAL_ERROR "DIRECTSTORAGE_ROOT must name the pinned DirectStorage checkout")
endif()

set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_subdirectory(
  "${DIRECTSTORAGE_ROOT}/GDeflate/GDeflate"
  "${CMAKE_CURRENT_BINARY_DIR}/official-gdeflate"
)

add_library(pragmata_gdeflate SHARED pragmata_gdeflate.cpp)
target_compile_features(pragmata_gdeflate PRIVATE cxx_std_17)
target_link_libraries(pragmata_gdeflate PRIVATE GDeflate)

if(CMAKE_SIZEOF_VOID_P EQUAL 8)
  set_target_properties(pragmata_gdeflate PROPERTIES OUTPUT_NAME pragmata_gdeflate_x64)
else()
  set_target_properties(pragmata_gdeflate PROPERTIES OUTPUT_NAME pragmata_gdeflate_x86)
endif()
