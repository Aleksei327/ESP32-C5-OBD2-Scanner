// WebSocket-сервер ws://192.168.4.1:81/ws: одно сообщение — один JSON в текстовом кадре
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

typedef void (*ws_text_cb_t)(int fd, const char *txt, size_t len);
typedef void (*ws_empty_cb_t)(void);

esp_err_t ws_server_start(ws_text_cb_t on_text, ws_empty_cb_t on_empty);

// Отправка из любой задачи (через очередь сервера). droppable — событие, которое можно
// выбросить, если телефон не успевает принимать (кадры шины); ответы на команды не выбрасываются.
void ws_send(int fd, const char *txt, bool droppable);
void ws_broadcast(const char *txt, bool droppable);
int ws_client_count(void);
// Закрыть все соединения (телефон ушёл из сети — сокеты могли остаться полуоткрытыми)
void ws_close_all(void);
