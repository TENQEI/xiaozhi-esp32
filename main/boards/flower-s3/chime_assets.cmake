# Keep recordings with the board and reuse the existing 2 MB assets partition.
# This cache option also permits a private recording directory outside the repo.
set(FLOWER_CHIME_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/boards/flower-s3/chimes"
    CACHE PATH "Directory containing Flower S3 hourly Ogg/Opus recordings")
get_filename_component(FLOWER_CHIME_SOURCE_DIR "${FLOWER_CHIME_SOURCE_DIR}"
                       ABSOLUTE BASE_DIR "${PROJECT_DIR}")
set(FLOWER_RANDOM_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/boards/flower-s3/phrases"
    CACHE PATH "Directory containing Flower S3 random phrase Ogg/Opus recordings")
get_filename_component(FLOWER_RANDOM_SOURCE_DIR "${FLOWER_RANDOM_SOURCE_DIR}"
                       ABSOLUTE BASE_DIR "${PROJECT_DIR}")
set(FLOWER_GREETING_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/boards/flower-s3/greetings"
    CACHE PATH "Directory containing Flower S3 good-morning/good-night Ogg/Opus recordings")
get_filename_component(FLOWER_GREETING_SOURCE_DIR "${FLOWER_GREETING_SOURCE_DIR}"
                       ABSOLUTE BASE_DIR "${PROJECT_DIR}")
set(FLOWER_CHIME_STAGING "${CMAKE_BINARY_DIR}/flower_chime_assets")
file(GLOB FLOWER_CHIME_INPUTS CONFIGURE_DEPENDS "${FLOWER_CHIME_SOURCE_DIR}/*")
file(GLOB FLOWER_RANDOM_INPUTS CONFIGURE_DEPENDS "${FLOWER_RANDOM_SOURCE_DIR}/*")
file(GLOB FLOWER_GREETING_INPUTS CONFIGURE_DEPENDS "${FLOWER_GREETING_SOURCE_DIR}/*")
list(APPEND FLOWER_CHIME_INPUTS ${FLOWER_RANDOM_INPUTS} ${FLOWER_GREETING_INPUTS})
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${PROJECT_DIR}/scripts/prepare_flower_chimes.py" ${FLOWER_CHIME_INPUTS})
execute_process(
    COMMAND python "${PROJECT_DIR}/scripts/prepare_flower_chimes.py"
            --source "${FLOWER_CHIME_SOURCE_DIR}" --output "${FLOWER_CHIME_STAGING}"
            --random-source "${FLOWER_RANDOM_SOURCE_DIR}"
            --greetings-source "${FLOWER_GREETING_SOURCE_DIR}"
    RESULT_VARIABLE FLOWER_CHIME_RESULT
    OUTPUT_VARIABLE FLOWER_CHIME_OUTPUT
    ERROR_VARIABLE FLOWER_CHIME_ERROR
)
if(NOT FLOWER_CHIME_RESULT EQUAL 0)
    message(FATAL_ERROR "${FLOWER_CHIME_ERROR}")
endif()
message(STATUS "${FLOWER_CHIME_OUTPUT}")
set(DEFAULT_ASSETS_EXTRA_FILES "${FLOWER_CHIME_STAGING}")
