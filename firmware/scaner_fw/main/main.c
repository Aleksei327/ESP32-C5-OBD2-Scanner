// Прошивка самотеста платы v1: два канала CAN, «только слушать», напряжение АКБ.
// Консоль — встроенный USB XIAO (idf.py monitor или любой терминал 115200).
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
#include "vbat.h"

static can_ch_t s_a = {.name = "CAN-A (OBD 6/14)", .tx = CAN_A_TX_GPIO, .rx = CAN_A_RX_GPIO, .rs = CAN_A_RS_GPIO};
static can_ch_t s_b = {.name = "CAN-B (OBD 3/8)", .tx = CAN_B_TX_GPIO, .rx = CAN_B_RX_GPIO, .rs = CAN_B_RS_GPIO};

static void print_msg(const char *ch, const can_msg_t *m)
{
    printf("%10.3f %s %03lX%s [%u]", m->ts_us / 1e6, ch, (unsigned long)m->id, m->ext ? "x" : "", m->dlc);
    for (int i = 0; i < m->dlc; i++) {
        printf(" %02X", m->data[i]);
    }
    printf("\n");
}

// Каналы A и B соединены друг с другом, оба терминатора JP2/JP3 замкнуты
static int one_way(can_ch_t *from, can_ch_t *to, uint32_t id, int n)
{
    int ok = 0;
    for (int i = 0; i < n; i++) {
        uint8_t data[8] = {0xA5, 0x5A, (uint8_t)i, 1, 2, 3, 4, 5};
        if (can_ch_send(from, id, data, 8, 100) != ESP_OK) {
            printf("  %s: передача %d не прошла\n", from->name, i);
            continue;
        }
        can_msg_t m;
        if (can_ch_recv(to, &m, 100) && m.id == id && m.data[2] == (uint8_t)i) {
            ok++;
        } else {
            printf("  %s: кадр %d не дошёл\n", to->name, i);
        }
    }
    return ok;
}

static int cmd_selftest(int argc, char **argv)
{
    const int n = 20;
    printf("Самотест: каналы A и B соединены проводами, JP2 и JP3 замкнуты.\n");
    if (can_ch_start(&s_a, false) != ESP_OK || can_ch_start(&s_b, false) != ESP_OK) {
        return 1;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    int ab = one_way(&s_a, &s_b, 0x123, n);
    int ba = one_way(&s_b, &s_a, 0x321, n);
    can_ch_print_status(&s_a);
    can_ch_print_status(&s_b);
    printf("A -> B: %d/%d, B -> A: %d/%d — %s\n", ab, n, ba, n, (ab == n && ba == n) ? "ОК" : "ОШИБКА");
    can_ch_start(&s_a, true);
    can_ch_start(&s_b, true);
    return (ab == n && ba == n) ? 0 : 1;
}

static int cmd_listen(int argc, char **argv)
{
    int seconds = argc > 1 ? atoi(argv[1]) : 10;
    if (seconds <= 0) {
        seconds = 10;
    }
    can_ch_start(&s_a, true);
    can_ch_start(&s_b, true);
    printf("Слушаю оба канала %d с. Трансиверы в режиме «только слушать» (Rs = 1).\n", seconds);
    int64_t end = esp_timer_get_time() + (int64_t)seconds * 1000000;
    can_msg_t m;
    while (esp_timer_get_time() < end) {
        bool got = false;
        if (can_ch_recv(&s_a, &m, 0)) {
            print_msg("A", &m);
            got = true;
        }
        if (can_ch_recv(&s_b, &m, 0)) {
            print_msg("B", &m);
            got = true;
        }
        if (!got) {
            vTaskDelay(1);
        }
    }
    can_ch_print_status(&s_a);
    can_ch_print_status(&s_b);
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

static int cmd_status(int argc, char **argv)
{
    can_ch_print_status(&s_a);
    can_ch_print_status(&s_b);
    return cmd_vbat(0, NULL);
}

void app_main(void)
{
    // Первым делом — Rs в 1: трансиверы молчат, пока мы не решим иначе
    can_ch_init_pins(&s_a);
    can_ch_init_pins(&s_b);
    vbat_init();
    can_ch_start(&s_a, true);
    can_ch_start(&s_b, true);

    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t repl_cfg = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    repl_cfg.prompt = "scaner>";
    esp_console_dev_usb_serial_jtag_config_t hw_cfg = ESP_CONSOLE_DEV_USB_SERIAL_JTAG_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_console_new_repl_usb_serial_jtag(&hw_cfg, &repl_cfg, &repl));

    const esp_console_cmd_t cmds[] = {
        {.command = "selftest", .help = "Самотест: A и B соединены проводами, JP2/JP3 замкнуты", .func = cmd_selftest},
        {.command = "listen", .help = "listen [секунды] — слушать оба канала, ничего не передавая", .func = cmd_listen},
        {.command = "vbat", .help = "Напряжение АКБ", .func = cmd_vbat},
        {.command = "status", .help = "Состояние каналов и АКБ", .func = cmd_status},
    };
    for (size_t i = 0; i < sizeof(cmds) / sizeof(cmds[0]); i++) {
        ESP_ERROR_CHECK(esp_console_cmd_register(&cmds[i]));
    }
    ESP_ERROR_CHECK(esp_console_register_help_command());
    printf("\nСканер-адаптер OBD, прошивка самотеста. Команды: help, selftest, listen, vbat, status\n");
    ESP_ERROR_CHECK(esp_console_start_repl(repl));
}
