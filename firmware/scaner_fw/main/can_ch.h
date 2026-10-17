// Канал CAN: контроллер TWAI + трансивер SN65HVD230 с управлением Rs
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_twai.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

typedef struct {
    uint32_t id;
    uint8_t dlc;
    bool ext;
    bool rtr;
    uint8_t data[8];
    uint64_t ts_us;
} can_msg_t;

typedef struct {
    const char *name;
    gpio_num_t tx, rx, rs;
    twai_node_handle_t node;
    QueueHandle_t rxq;
    bool listen_only;
    volatile uint32_t rx_count, rx_dropped, bus_errors;
} can_ch_t;

// Rs в 1 (только слушать) — вызывать как можно раньше после старта
void can_ch_init_pins(can_ch_t *ch);

// listen_only = true: Rs = 1 (передатчик трансивера выключен) и TWAI в режиме listen-only
esp_err_t can_ch_start(can_ch_t *ch, bool listen_only);
esp_err_t can_ch_stop(can_ch_t *ch);

esp_err_t can_ch_send(can_ch_t *ch, uint32_t id, const uint8_t *data, uint8_t len, int timeout_ms);
bool can_ch_recv(can_ch_t *ch, can_msg_t *msg, int timeout_ms);
void can_ch_print_status(can_ch_t *ch);
