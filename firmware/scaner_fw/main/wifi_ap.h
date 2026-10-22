// Точка доступа Wi-Fi адаптера: SCANER-C5-xxxx, адрес 192.168.4.1
#pragma once

#include "esp_err.h"

// Пароль — случайный, создаётся при первом запуске и хранится в NVS (консоль: wifi)
esp_err_t wifi_ap_start(void);
const char *wifi_ap_ssid(void);
const char *wifi_ap_pass(void);
int wifi_ap_clients(void);
esp_err_t wifi_ap_set_pass(const char *pass);

// Вызывается, когда от точки отключился последний телефон
void wifi_ap_on_empty(void (*cb)(void));
