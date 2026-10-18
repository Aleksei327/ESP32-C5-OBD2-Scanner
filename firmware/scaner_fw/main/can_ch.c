#include "can_ch.h"

#include <stdio.h>
#include <string.h>
#include "board.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_twai_onchip.h"

static const char *TAG = "can";

static bool IRAM_ATTR on_rx(twai_node_handle_t handle, const twai_rx_done_event_data_t *edata, void *user_ctx)
{
    can_ch_t *ch = (can_ch_t *)user_ctx;
    uint8_t buf[TWAI_FRAME_MAX_LEN];
    twai_frame_t frame = {.buffer = buf, .buffer_len = sizeof(buf)};
    BaseType_t woken = pdFALSE;

    if (twai_node_receive_from_isr(handle, &frame) != ESP_OK) {
        return false;
    }
    can_msg_t msg = {
        .id = frame.header.id,
        .dlc = frame.header.dlc > 8 ? 8 : frame.header.dlc,
        .ext = frame.header.ide,
        .rtr = frame.header.rtr,
        .ts_us = frame.header.timestamp,
    };
    memcpy(msg.data, buf, msg.dlc);
    if (xQueueSendFromISR(ch->rxq, &msg, &woken) == pdTRUE) {
        ch->rx_count++;
    } else {
        ch->rx_dropped++;
    }
    return woken == pdTRUE;
}

static bool IRAM_ATTR on_error(twai_node_handle_t handle, const twai_error_event_data_t *edata, void *user_ctx)
{
    ((can_ch_t *)user_ctx)->bus_errors++;
    return false;
}

// TX трансивера держим в 1 («тишина»), пока им не управляет контроллер CAN:
// подтяжки на D на плате нет, защита — Rs = 1 (передатчик выключен) плюс этот уровень.
static void tx_idle(can_ch_t *ch)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << ch->tx,
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_set_level(ch->tx, 1);
    gpio_config(&io);
    gpio_set_level(ch->tx, 1);
}

void can_ch_init_pins(can_ch_t *ch)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << ch->rs,
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_set_level(ch->rs, 1);
    gpio_config(&io);
    gpio_set_level(ch->rs, 1);
    tx_idle(ch);
    if (ch->rxq == NULL) {
        ch->rxq = xQueueCreate(256, sizeof(can_msg_t));
    }
}

esp_err_t can_ch_start(can_ch_t *ch, bool listen_only)
{
    if (ch->node) {
        can_ch_stop(ch);
    }
    // Трансивер в «только слушать» (Rs = 1), пока контроллер не запущен и не держит на TX «тишину»
    gpio_set_level(ch->rs, 1);

    twai_onchip_node_config_t cfg = {
        .io_cfg = {
            .tx = listen_only ? GPIO_NUM_NC : ch->tx,
            .rx = ch->rx,
            .quanta_clk_out = GPIO_NUM_NC,
            .bus_off_indicator = GPIO_NUM_NC,
        },
        .bit_timing.bitrate = CAN_BITRATE,
        .timestamp_resolution_hz = 1000000,
        .tx_queue_depth = 8,
        .flags.enable_listen_only = listen_only,
    };
    esp_err_t err = twai_new_node_onchip(&cfg, &ch->node);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s: twai_new_node_onchip: %s", ch->name, esp_err_to_name(err));
        ch->node = NULL;
        gpio_set_level(ch->rs, 1);
        return err;
    }
    twai_event_callbacks_t cbs = {
        .on_rx_done = on_rx,
        .on_error = on_error,
    };
    ESP_ERROR_CHECK(twai_node_register_event_callbacks(ch->node, &cbs, ch));
    ESP_ERROR_CHECK(twai_node_enable(ch->node));
    if (!listen_only) {
        gpio_set_level(ch->rs, 0);  // контроллер уже держит TX в 1 — теперь можно включать передатчик
    }
    ch->listen_only = listen_only;
    xQueueReset(ch->rxq);
    ESP_LOGI(TAG, "%s: %s, %d бит/с", ch->name, listen_only ? "только слушать" : "работа", CAN_BITRATE);
    return ESP_OK;
}

esp_err_t can_ch_stop(can_ch_t *ch)
{
    gpio_set_level(ch->rs, 1);
    if (ch->node == NULL) {
        return ESP_OK;
    }
    twai_node_disable(ch->node);
    esp_err_t err = twai_node_delete(ch->node);
    ch->node = NULL;
    tx_idle(ch);  // вывод отпущен контроллером — снова держим «тишину» сами
    return err;
}

esp_err_t can_ch_send(can_ch_t *ch, uint32_t id, const uint8_t *data, uint8_t len, int timeout_ms)
{
    if (ch->node == NULL || ch->listen_only) {
        return ESP_ERR_INVALID_STATE;
    }
    uint8_t buf[8] = {0};
    memcpy(buf, data, len > 8 ? 8 : len);
    twai_frame_t frame = {
        .header.id = id,
        .header.dlc = len > 8 ? 8 : len,
        .buffer = buf,
        .buffer_len = len > 8 ? 8 : len,
    };
    esp_err_t err = twai_node_transmit(ch->node, &frame, timeout_ms);
    if (err == ESP_OK) {
        // frame лежит на стеке: дожидаемся, пока драйвер его отправит
        err = twai_node_transmit_wait_all_done(ch->node, timeout_ms);
    }
    return err;
}

bool can_ch_recv(can_ch_t *ch, can_msg_t *msg, int timeout_ms)
{
    return xQueueReceive(ch->rxq, msg, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

void can_ch_print_status(can_ch_t *ch)
{
    if (ch->node == NULL) {
        printf("%s: выключен\n", ch->name);
        return;
    }
    const char *st[] = {"error_active", "error_warning", "error_passive", "bus_off"};
    twai_node_status_t s = {0};
    twai_node_record_t r = {0};
    twai_node_get_info(ch->node, &s, &r);
    printf("%s: %s, %s, TEC=%u REC=%u, принято %lu, потеряно %lu, ошибок шины %lu\n",
           ch->name, ch->listen_only ? "только слушать" : "работа",
           s.state < 4 ? st[s.state] : "?", s.tx_error_count, s.rx_error_count,
           (unsigned long)ch->rx_count, (unsigned long)ch->rx_dropped, (unsigned long)r.bus_err_num);
}
