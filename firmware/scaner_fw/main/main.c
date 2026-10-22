// Прошивка адаптера: точка Wi-Fi + WebSocket (протокол DOCS/ПРОТОКОЛ.md), две шины CAN.
// Консоль — встроенный USB XIAO (idf.py monitor или любой терминал 115200): самотест, Wi-Fi, состояние.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "board.h"
#include "can_ch.h"
#include "esp_console.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "proto.h"
#include "vbat.h"
#include "wifi_ap.h"
#include "ws_server.h"

static can_ch_t s_a = {.name = "CAN-A (OBD 6/14)", .tx = CAN_A_TX_GPIO, .rx = CAN_A_RX_GPIO, .rs = CAN_A_RS_GPIO};
static can_ch_t s_b = {.name = "CAN-B (OBD 3/8)", .tx = CAN_B_TX_GPIO, .rx = CAN_B_RX_GPIO, .rs = CAN_B_RS_GPIO};

// Каналы A и B соединены друг с другом, оба терминатора JP2/JP3 замкнуты
static int one_way(can_ch_t *from, char to, uint32_t id, int n)
{
    int ok = 0;
    proto_tap_begin(to, id);
    for (int i = 0; i < n; i++) {
        uint8_t data[8] = {0xA5, 0x5A, (uint8_t)i, 1, 2, 3, 4, 5};
        if (can_ch_send(from, id, data, 8, 100) != ESP_OK) {
            printf("  %s: передача %d не прошла\n", from->name, i);
            continue;
        }
        can_msg_t m;
        if (proto_tap_get(to, &m, 100) && m.data[2] == (uint8_t)i) {
            ok++;
        } else {
            printf("  шина %c: кадр %d не дошёл\n", to, i);
        }
    }
    proto_tap_end(to);
    return ok;
}

static int cmd_selftest(int argc, char **argv)
{
    if (ws_client_count() > 0) {
        printf("Подключено приложение — самотест мешал бы ему. Отключите телефон.\n");
        return 1;
    }
    const int n = 20;
    printf("Самотест: каналы A и B соединены проводами, JP2 и JP3 замкнуты.\n");
    if (can_ch_start(&s_a, false, CAN_BITRATE) != ESP_OK || can_ch_start(&s_b, false, CAN_BITRATE) != ESP_OK) {
        return 1;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    int ab = one_way(&s_a, 'B', 0x123, n);
    int ba = one_way(&s_b, 'A', 0x321, n);
    can_ch_print_status(&s_a);
    can_ch_print_status(&s_b);
    printf("A -> B: %d/%d, B -> A: %d/%d — %s\n", ab, n, ba, n, (ab == n && ba == n) ? "ОК" : "ОШИБКА");
    can_ch_stop(&s_a);
    can_ch_stop(&s_b);
    return (ab == n && ba == n) ? 0 : 1;
}

static int cmd_listen(int argc, char **argv)
{
    int seconds = argc > 1 ? atoi(argv[1]) : 10;
    if (seconds <= 0) {
        seconds = 10;
    }
    bool a_was = can_ch_is_open(&s_a), b_was = can_ch_is_open(&s_b);
    if (!a_was) {
        can_ch_start(&s_a, true, CAN_BITRATE);
    }
    if (!b_was) {
        can_ch_start(&s_b, true, CAN_BITRATE);
    }
    printf("Слушаю обе шины %d с.\n", seconds);
    proto_console_print(true);
    vTaskDelay(pdMS_TO_TICKS(seconds * 1000));
    proto_console_print(false);
    can_ch_print_status(&s_a);
    can_ch_print_status(&s_b);
    if (!a_was) {
        can_ch_stop(&s_a);
    }
    if (!b_was) {
        can_ch_stop(&s_b);
    }
    return 0;
}

static int cmd_vbat(int argc, char **argv)
{
    float v = vbat_read();
    if (v < 0) {
        printf("Ошибка АЦП\n");
    } else if (v == 0) {
        printf("АКБ: нет (питание от USB)\n");
    } else {
        printf("АКБ: %.2f В\n", v);
    }
    return 0;
}

static int cmd_wifi(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "pass") == 0) {
        esp_err_t err = wifi_ap_set_pass(argv[2]);
        if (err == ESP_ERR_INVALID_ARG) {
            printf("Пароль — от 8 до 63 символов\n");
            return 1;
        }
        if (err != ESP_OK) {
            printf("Не сохранился: %s\n", esp_err_to_name(err));
            return 1;
        }
        printf("Пароль сменён\n");
    }
    printf("Сеть: %s\nПароль: %s\nАдрес для приложения: ws://192.168.4.1:81/ws\n", wifi_ap_ssid(), wifi_ap_pass());
    printf("Телефонов в сети: %d, приложений подключено: %d\n", wifi_ap_clients(), ws_client_count());
    return 0;
}

static int cmd_status(int argc, char **argv)
{
    can_ch_print_status(&s_a);
    can_ch_print_status(&s_b);
    printf("Wi-Fi: %s, телефонов %d, приложений %d; свободно памяти %lu байт\n", wifi_ap_ssid(), wifi_ap_clients(),
           ws_client_count(), (unsigned long)esp_get_free_heap_size());
    return cmd_vbat(0, NULL);
}

static void on_wifi_empty(void)
{
    ws_close_all();          // телефон ушёл из сети — его сокеты уже никто не закроет
    proto_on_no_clients();
}

void app_main(void)
{
    // Первым делом — Rs в 1: трансиверы молчат, пока приложение не откроет шину
    can_ch_init_pins(&s_a);
    can_ch_init_pins(&s_b);
    vbat_init();

    proto_init(&s_a, &s_b);
    ESP_ERROR_CHECK(wifi_ap_start());
    wifi_ap_on_empty(on_wifi_empty);
    ESP_ERROR_CHECK(ws_server_start(proto_on_text, proto_on_no_clients));

    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t repl_cfg = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    repl_cfg.prompt = "scaner>";
    esp_console_dev_usb_serial_jtag_config_t hw_cfg = ESP_CONSOLE_DEV_USB_SERIAL_JTAG_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_console_new_repl_usb_serial_jtag(&hw_cfg, &repl_cfg, &repl));

    const esp_console_cmd_t cmds[] = {
        {.command = "selftest", .help = "Самотест: A и B соединены проводами, JP2/JP3 замкнуты", .func = cmd_selftest},
        {.command = "listen", .help = "listen [секунды] — печатать кадры обеих шин, ничего не передавая", .func = cmd_listen},
        {.command = "vbat", .help = "Напряжение АКБ", .func = cmd_vbat},
        {.command = "wifi", .help = "Сеть и пароль; wifi pass <новый> — сменить пароль", .func = cmd_wifi},
        {.command = "status", .help = "Состояние шин, Wi-Fi и АКБ", .func = cmd_status},
    };
    for (size_t i = 0; i < sizeof(cmds) / sizeof(cmds[0]); i++) {
        ESP_ERROR_CHECK(esp_console_cmd_register(&cmds[i]));
    }
    ESP_ERROR_CHECK(esp_console_register_help_command());
    printf("\nСканер-адаптер OBD %s. Сеть %s, пароль %s, ws://192.168.4.1:81/ws\n"
           "Команды: help, status, wifi, vbat, listen, selftest\n",
           FW_VERSION, wifi_ap_ssid(), wifi_ap_pass());
    ESP_ERROR_CHECK(esp_console_start_repl(repl));
}
