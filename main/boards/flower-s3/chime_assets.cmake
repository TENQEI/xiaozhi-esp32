# Keep recordings with the board and reuse the existing 2 MB assets partition.
# This cache option also permits a private recording directory outside the repo.
set(FLOWER_CHIME_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/boards/flower-s3/chimes"
    CACHE PATH "Directory containing Flower S3 hourly Ogg/Opus recordings")
get_filename_component(FLOWER_CHIME_SOURCE_DIR "${FLOWER_CHIME_SOURCE_DIR}"
                       ABSOLUTE BASE_DIR "${PROJECT_DIR}")
set(FLOWER_CHIME_STAGING "${CMAKE_BINARY_DIR}/flower_chime_assets")
file(GLOB FLOWER_CHIME_INPUTS CONFIGURE_DEPENDS "${FLOWER_CHIME_SOURCE_DIR}/*")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${PROJECT_DIR}/scripts/prepare_flower_chimes.py" ${FLOWER_CHIME_INPUTS})
execute_process(
    COMMAND python "${PROJECT_DIR}/scripts/prepare_flower_chimes.py"
            --source "${FLOWER_CHIME_SOURCE_DIR}" --output "${FLOWER_CHIME_STAGING}"
    RESULT_VARIABLE FLOWER_CHIME_RESULT
    OUTPUT_VARIABLE FLOWER_CHIME_OUTPUT
    ERROR_VARIABLE FLOWER_CHIME_ERROR
)
if(NOT FLOWER_CHIME_RESULT EQUAL 0)
    message(FATAL_ERROR "${FLOWER_CHIME_ERROR}")
endif()
message(STATUS "${FLOWER_CHIME_OUTPUT}")
set(DEFAULT_ASSETS_EXTRA_FILES "${FLOWER_CHIME_STAGING}")
