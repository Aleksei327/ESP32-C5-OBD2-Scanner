// Распиновка платы v1 (Seeed XIAO ESP32-C5). См. DOCS/ПЛАТА_v1.md
#pragma once

#include "driver/gpio.h"

// Канал A — OBD 6/14, стандартный OBD-II
#define CAN_A_TX_GPIO   GPIO_NUM_10   // D10
#define CAN_A_RX_GPIO   GPIO_NUM_9    // D9
#define CAN_A_RS_GPIO   GPIO_NUM_23   // D4: 1 = только слушать, 0 = работа

// Канал B — OBD 3/8, PSA Diag-on-CAN
#define CAN_B_TX_GPIO   GPIO_NUM_8    // D8
#define CAN_B_RX_GPIO   GPIO_NUM_0    // D1
#define CAN_B_RS_GPIO   GPIO_NUM_24   // D5

// Напряжение АКБ: делитель 220k/33k после HS1M на D0 (GPIO1, ADC1_CH0)
#define VBAT_ADC_GPIO   GPIO_NUM_1
#define VBAT_DIVIDER    ((220.0f + 33.0f) / 33.0f)
#define VBAT_DIODE_DROP 0.9f          // падение на HS1M, уточнить калибровкой

#define CAN_BITRATE     500000        // и OBD-II, и Diag-on-CAN PSA — 500 кбит/с
