cmake_minimum_required(VERSION 3.16)
project(rpi_cabinet_controller VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(CTest)
find_package(Threads REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(MOSQUITTO REQUIRED IMPORTED_TARGET libmosquitto)
find_path(NLOHMANN_JSON_INCLUDE_DIR nlohmann/json.hpp REQUIRED)

add_library(cr100emur STATIC utils/cr100emur/src/cr100emur.c)
target_include_directories(cr100emur PUBLIC utils/cr100emur/include)
target_compile_definitions(cr100emur PRIVATE _DEFAULT_SOURCE)
target_compile_options(cr100emur PRIVATE -Wall -Wextra -Wpedantic)

add_library(cabinet_controller_core STATIC
    src/config.cpp
    src/controller.cpp
    src/protocol.cpp
)
target_include_directories(cabinet_controller_core
    PUBLIC src "${NLOHMANN_JSON_INCLUDE_DIR}"
)
target_compile_options(cabinet_controller_core PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_library(cabinet_controller_runtime STATIC
    src/mqtt_client.cpp
    src/serial_line.cpp
)
target_include_directories(cabinet_controller_runtime PUBLIC src)
target_link_libraries(cabinet_controller_runtime
    PUBLIC PkgConfig::MOSQUITTO Threads::Threads
)
target_compile_options(cabinet_controller_runtime PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(rpi-cabinet-controller src/main.cpp)
target_link_libraries(rpi-cabinet-controller PRIVATE
    cabinet_controller_core
    cabinet_controller_runtime
    cr100emur
    Threads::Threads
)
target_compile_options(rpi-cabinet-controller PRIVATE -Wall -Wextra -Wpedantic -Werror)

install(TARGETS rpi-cabinet-controller RUNTIME DESTINATION bin)

if(BUILD_TESTING)
    add_executable(protocol_test tests/protocol_test.cpp)
    target_link_libraries(protocol_test PRIVATE cabinet_controller_core)
    target_compile_options(protocol_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME protocol_test COMMAND protocol_test)

    add_executable(controller_test tests/controller_test.cpp)
    target_link_libraries(controller_test PRIVATE cabinet_controller_core)
    target_compile_options(controller_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME controller_test COMMAND controller_test)

    add_executable(config_test tests/config_test.cpp)
    target_link_libraries(config_test PRIVATE cabinet_controller_core)
    target_compile_options(config_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME config_test COMMAND config_test)

    add_executable(serial_line_test tests/serial_line_test.cpp)
    target_link_libraries(serial_line_test PRIVATE cabinet_controller_runtime util)
    target_compile_options(serial_line_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME serial_line_test COMMAND serial_line_test)

    find_program(MOSQUITTO_BROKER_EXECUTABLE mosquitto)
    if(MOSQUITTO_BROKER_EXECUTABLE)
        add_executable(mqtt_client_test tests/mqtt_client_test.cpp)
        target_link_libraries(mqtt_client_test PRIVATE cabinet_controller_runtime)
        target_compile_definitions(mqtt_client_test
            PRIVATE MOSQUITTO_BROKER_EXECUTABLE="${MOSQUITTO_BROKER_EXECUTABLE}")
        target_compile_options(mqtt_client_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
        add_test(NAME mqtt_client_test COMMAND mqtt_client_test)
    endif()

    find_program(PYTHON3_EXECUTABLE python3)
    if(PYTHON3_EXECUTABLE)
        add_test(
            NAME mock_server_test
            COMMAND "${PYTHON3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/mock-server/test_mock_server.py"
        )
    endif()
    find_program(MOSQUITTO_PUB_EXECUTABLE mosquitto_pub)
    find_program(MOSQUITTO_SUB_EXECUTABLE mosquitto_sub)
    if(MOSQUITTO_BROKER_EXECUTABLE
       AND MOSQUITTO_PUB_EXECUTABLE
       AND MOSQUITTO_SUB_EXECUTABLE
       AND PYTHON3_EXECUTABLE)
        add_test(
            NAME controller_integration_test
            COMMAND
                "${PYTHON3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/controller_integration_test.py"
                "$<TARGET_FILE:rpi-cabinet-controller>"
                "${MOSQUITTO_BROKER_EXECUTABLE}"
                "${MOSQUITTO_PUB_EXECUTABLE}"
                "${MOSQUITTO_SUB_EXECUTABLE}"
        )
        set_tests_properties(controller_integration_test PROPERTIES TIMEOUT 15)
    endif()
endif()
