cmake_minimum_required(VERSION 3.24)
project(Rpi5FanControlStandalone VERSION 0.2.0 LANGUAGES CXX RC)
if(NOT WIN32 OR NOT MSVC)
  message(FATAL_ERROR "Build with the Microsoft C++ compiler and Windows SDK.")
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
execute_process(COMMAND powershell.exe -NoProfile -ExecutionPolicy Bypass -File
  "${CMAKE_CURRENT_SOURCE_DIR}/Build-Assets.ps1"
  -Source "${CMAKE_CURRENT_SOURCE_DIR}/assets/fan-user.png"
  -Destination "${CMAKE_CURRENT_BINARY_DIR}/fan.ico"
  RESULT_VARIABLE asset_result)
if(NOT asset_result EQUAL 0)
  message(FATAL_ERROR "Could not generate embedded icon from the supplied PNG.")
endif()
configure_file(app.rc.in "${CMAKE_CURRENT_BINARY_DIR}/app.rc" @ONLY)
add_executable(Rpi5FanControl WIN32 Main.cpp Animation.h "${CMAKE_CURRENT_BINARY_DIR}/app.rc")
target_compile_definitions(Rpi5FanControl PRIVATE UNICODE _UNICODE _WIN32_WINNT=0x0A00 WINVER=0x0A00)
target_compile_options(Rpi5FanControl PRIVATE /W4 /permissive- /utf-8 /O2 /Gy)
target_link_options(Rpi5FanControl PRIVATE /MANIFEST:NO /INCREMENTAL:NO /OPT:REF /OPT:ICF /DYNAMICBASE /NXCOMPAT)
target_link_libraries(Rpi5FanControl PRIVATE gdiplus comctl32 shell32 shlwapi ole32 user32 gdi32 advapi32 uuid)
set_target_properties(Rpi5FanControl PROPERTIES OUTPUT_NAME "Rpi5FanControl-${CMAKE_GENERATOR_PLATFORM}")
