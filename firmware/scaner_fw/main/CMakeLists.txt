idf_component_register(
    SRCS "main.c" "can_ch.c" "vbat.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_twai esp_driver_gpio esp_adc esp_timer console
)
