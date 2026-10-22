// Протокол адаптер ↔ приложение (DOCS/ПРОТОКОЛ.md): команды, ISO-TP, тестер, монитор шины
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "can_ch.h"

#define FW_VERSION "0.1.0"

// a — шина A (OBD 6/14, OBD-II), b — шина B (OBD 3/8, диагностика PSA)
void proto_init(can_ch_t *a, can_ch_t *b);

// Сообщение от приложения (вызывается из задачи веб-сервера, не блокирует)
void proto_on_text(int fd, const char *txt, size_t len);

// Приложение отключилось совсем: остановить тестеры и монитор, закрыть шины (Rs = 1)
void proto_on_no_clients(void);

// Для консоли: печатать все кадры обеих шин
void proto_console_print(bool on);

// Для самотеста из консоли: ловить кадры с заданным id на шине 'A'/'B'
void proto_tap_begin(char bus, uint32_t id);
bool proto_tap_get(char bus, can_msg_t *m, int timeout_ms);
void proto_tap_end(char bus);
