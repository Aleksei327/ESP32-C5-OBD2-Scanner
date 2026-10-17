#pragma once

#include "esp_err.h"

esp_err_t vbat_init(void);
// Напряжение на пине 16 OBD, вольты. Отрицательное значение — ошибка АЦП.
float vbat_read(void);
