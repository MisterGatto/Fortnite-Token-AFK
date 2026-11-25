cmake_minimum_required(VERSION 3.20)
project(fortnite_auto_ocr_native CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)
FetchContent_Declare(
    vigemclient
    GIT_REPOSITORY https://github.com/nefarius/ViGEmClient.git
    GIT_TAG        v1.21.222.0
)
FetchContent_MakeAvailable(vigemclient)

add_library(vigem_bridge SHARED vigem_bridge.cpp)
target_include_directories(vigem_bridge PRIVATE ${vigemclient_SOURCE_DIR}/include)
target_compile_definitions(vigem_bridge PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
target_link_libraries(vigem_bridge PRIVATE ViGEmClient setupapi)

add_library(dxgi_bridge SHARED dxgi_bridge.cpp)
target_compile_definitions(dxgi_bridge PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
target_link_libraries(dxgi_bridge PRIVATE d3d11 dxgi)
