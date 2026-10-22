idf_component_register(
    SRCS "main.c" "can_ch.c" "vbat.c" "proto.c" "wifi_ap.c" "ws_server.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_twai esp_driver_gpio esp_adc esp_timer console
             esp_wifi esp_netif esp_event nvs_flash esp_http_server lwip
             bootloader_support esp_app_format
)
