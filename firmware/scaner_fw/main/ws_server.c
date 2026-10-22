#include "ws_server.h"

#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include "esp_http_server.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "ws";

#define MAX_CLIENTS   3
#define MAX_PENDING   48   // отправок в очереди сервера; события сверх этого выбрасываем

static httpd_handle_t s_hd;
static int s_fds[MAX_CLIENTS];
static int s_n;
static SemaphoreHandle_t s_lock;
static atomic_int s_pending;
static ws_text_cb_t s_on_text;
static ws_empty_cb_t s_on_empty;

typedef struct {
    int fd;
    size_t len;
    char txt[];
} job_t;

static void add_client(int fd)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool have = false;
    for (int i = 0; i < s_n; i++) {
        have |= s_fds[i] == fd;
    }
    if (!have && s_n < MAX_CLIENTS) {
        s_fds[s_n++] = fd;
    }
    int n = s_n;
    xSemaphoreGive(s_lock);
    ESP_LOGI(TAG, "приложение подключилось (сокет %d), соединений %d", fd, n);
}

static void remove_client(int fd)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool had = false;
    for (int i = 0; i < s_n; i++) {
        if (s_fds[i] == fd) {
            s_fds[i] = s_fds[--s_n];
            had = true;
            break;
        }
    }
    int n = s_n;
    xSemaphoreGive(s_lock);
    if (had) {
        ESP_LOGI(TAG, "приложение отключилось (сокет %d), соединений %d", fd, n);
        if (n == 0 && s_on_empty) {
            s_on_empty();
        }
    }
}

static void on_close(httpd_handle_t hd, int fd)
{
    remove_client(fd);
    close(fd);
}

// Рукопожатие WebSocket прошло (в IDF 6 обработчик URI на нём уже не вызывается)
static esp_err_t on_handshake(httpd_req_t *req)
{
    add_client(httpd_req_to_sockfd(req));
    return ESP_OK;
}

static esp_err_t ws_handler(httpd_req_t *req)
{
    int fd = httpd_req_to_sockfd(req);
    if (req->method == HTTP_GET) {
        return ESP_OK;
    }
    httpd_ws_frame_t pkt = {.type = HTTPD_WS_TYPE_TEXT};
    esp_err_t err = httpd_ws_recv_frame(req, &pkt, 0);
    if (err != ESP_OK) {
        return err;
    }
    if (pkt.len == 0 || pkt.len > 16384) {
        return ESP_OK;
    }
    char *buf = malloc(pkt.len + 1);
    if (buf == NULL) {
        return ESP_ERR_NO_MEM;
    }
    pkt.payload = (uint8_t *)buf;
    err = httpd_ws_recv_frame(req, &pkt, pkt.len);
    if (err == ESP_OK && pkt.type == HTTPD_WS_TYPE_TEXT) {
        buf[pkt.len] = 0;
        s_on_text(fd, buf, pkt.len);
    }
    free(buf);
    return err;
}

static void send_work(void *arg)
{
    job_t *j = arg;
    if (httpd_ws_get_fd_info(s_hd, j->fd) == HTTPD_WS_CLIENT_WEBSOCKET) {
        httpd_ws_frame_t f = {
            .final = true,
            .type = HTTPD_WS_TYPE_TEXT,
            .payload = (uint8_t *)j->txt,
            .len = j->len,
        };
        httpd_ws_send_frame_async(s_hd, j->fd, &f);
    }
    free(j);
    atomic_fetch_sub(&s_pending, 1);
}

void ws_send(int fd, const char *txt, bool droppable)
{
    if (s_hd == NULL || fd < 0 || (droppable && atomic_load(&s_pending) >= MAX_PENDING)) {
        return;
    }
    size_t len = strlen(txt);
    job_t *j = malloc(sizeof(job_t) + len + 1);
    if (j == NULL) {
        return;
    }
    j->fd = fd;
    j->len = len;
    memcpy(j->txt, txt, len + 1);
    atomic_fetch_add(&s_pending, 1);
    if (httpd_queue_work(s_hd, send_work, j) != ESP_OK) {
        atomic_fetch_sub(&s_pending, 1);
        free(j);
    }
}

void ws_broadcast(const char *txt, bool droppable)
{
    int fds[MAX_CLIENTS];
    xSemaphoreTake(s_lock, portMAX_DELAY);
    int n = s_n;
    memcpy(fds, s_fds, sizeof(fds));
    xSemaphoreGive(s_lock);
    for (int i = 0; i < n; i++) {
        ws_send(fds[i], txt, droppable);
    }
}

int ws_client_count(void)
{
    return s_n;
}

void ws_close_all(void)
{
    int fds[MAX_CLIENTS];
    xSemaphoreTake(s_lock, portMAX_DELAY);
    int n = s_n;
    memcpy(fds, s_fds, sizeof(fds));
    xSemaphoreGive(s_lock);
    for (int i = 0; i < n; i++) {
        httpd_sess_trigger_close(s_hd, fds[i]);
    }
}

esp_err_t ws_server_start(ws_text_cb_t on_text, ws_empty_cb_t on_empty)
{
    s_on_text = on_text;
    s_on_empty = on_empty;
    s_lock = xSemaphoreCreateMutex();

    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port = 81;
    cfg.ctrl_port = 32769;
    cfg.max_open_sockets = MAX_CLIENTS + 1;
    cfg.lru_purge_enable = true;  // новое подключение вытесняет старое, «зависшее»
    cfg.close_fn = on_close;
    cfg.stack_size = 6144;
    esp_err_t err = httpd_start(&s_hd, &cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "httpd_start: %s", esp_err_to_name(err));
        return err;
    }
    static const httpd_uri_t ws = {
        .uri = "/ws",
        .method = HTTP_GET,
        .handler = ws_handler,
        .is_websocket = true,
        .ws_post_handshake_cb = on_handshake,
    };
    return httpd_register_uri_handler(s_hd, &ws);
}
