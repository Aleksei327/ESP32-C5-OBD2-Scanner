#include "proto.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "board.h"
#include "cJSON.h"
#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "vbat.h"
#include "ws_server.h"

static const char *TAG = "proto";

#define ISOTP_MAX   4095
#define TESTERS     4
#define MON_MAX     192     // разных id в сводке монитора
#define MON_IDS     16      // фильтр id для монитора
#define PAD_BYTE    0x00
#define ANY_RX_MIN  0x600   // rx «*»: ответ ищем среди диагностических id
#define ANY_RX_MAX  0x7FF

typedef enum { J_OPEN, J_CLOSE, J_ISOTP, J_TESTER_START, J_TESTER_STOP, J_MON_START, J_MON_STOP, J_RESET } job_kind_t;

typedef struct {
    job_kind_t kind;
    int fd;             // кому отвечать; -1 — никому
    double id;          // id запроса приложения (число); NAN — не было
    bool has_id;
    uint32_t tx, rx;
    bool any_rx, listen, pad;
    int bitrate, timeout_ms, period_ms, mode;
    uint32_t ids[MON_IDS];
    int n_ids;
    uint16_t len;
    uint8_t data[];
} job_t;

typedef struct {
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
    uint32_t n, n_mark, hz;
} mon_ent_t;

typedef struct {
    char name;
    can_ch_t *ch;
    bool pad;                   // добивать кадры до 8 байт (OBD-II — да, PSA — нет)
    uint8_t stmin;              // какую паузу между кадрами просим у блока (мс)
    QueueHandle_t jobs;
    QueueHandle_t iso;          // кадры для текущего обмена ISO-TP
    volatile bool want, want_any;
    volatile uint32_t want_id;
    volatile bool print;

    struct {
        bool on;
        uint32_t tx;
        uint8_t data[8];
        uint8_t len;
        int period_ms;
        int64_t next_us;
    } tp[TESTERS];

    portMUX_TYPE mux;
    volatile int mon_mode;      // 0 — выкл, 1 — summary, 2 — raw
    uint32_t mon_ids[MON_IDS];
    int mon_n_ids;
    mon_ent_t mon[MON_MAX];
    int mon_count;

    uint8_t resp[ISOTP_MAX];
} bus_t;

static bus_t s_bus[2];

static bus_t *bus_by_name(const char *s)
{
    if (s && (s[0] == 'A' || s[0] == 'a') && s[1] == 0) {
        return &s_bus[0];
    }
    if (s && (s[0] == 'B' || s[0] == 'b') && s[1] == 0) {
        return &s_bus[1];
    }
    return NULL;
}

static int64_t now_us(void) { return esp_timer_get_time(); }

// ---------- ответы ----------

static void reply(const job_t *j, bool ok, const char *err, const char *extra)
{
    if (j->fd < 0) {
        return;
    }
    size_t n = 64 + (extra ? strlen(extra) : 0);
    char *buf = malloc(n);
    if (buf == NULL) {
        return;
    }
    char idbuf[24] = "null";
    if (j->has_id) {
        snprintf(idbuf, sizeof(idbuf), "%.0f", j->id);
    }
    if (ok) {
        snprintf(buf, n, "{\"id\":%s,\"ok\":true%s}", idbuf, extra ? extra : "");
    } else {
        snprintf(buf, n, "{\"id\":%s,\"ok\":false,\"err\":\"%s\"}", idbuf, err);
    }
    ws_send(j->fd, buf, false);
    free(buf);
}

static void hex(char *out, const uint8_t *d, int n)
{
    static const char h[] = "0123456789ABCDEF";
    for (int i = 0; i < n; i++) {
        out[2 * i] = h[d[i] >> 4];
        out[2 * i + 1] = h[d[i] & 15];
    }
    out[2 * n] = 0;
}

static int unhex(const char *s, uint8_t *out, int max)
{
    int n = strlen(s);
    if (n % 2 || n / 2 > max) {
        return -1;
    }
    for (int i = 0; i < n / 2; i++) {
        if (!isxdigit((unsigned char)s[2 * i]) || !isxdigit((unsigned char)s[2 * i + 1])) {
            return -1;
        }
        char b[3] = {s[2 * i], s[2 * i + 1], 0};
        out[i] = strtoul(b, NULL, 16);
    }
    return n / 2;
}

// ---------- ISO-TP ----------

static esp_err_t send_frame(bus_t *b, uint32_t id, const uint8_t *d, int n, bool pad)
{
    uint8_t buf[8];
    memcpy(buf, d, n);
    if (pad) {
        memset(buf + n, PAD_BYTE, 8 - n);
        n = 8;
    }
    return can_ch_send(b->ch, id, buf, n, 50);
}

static bool wait_frame(bus_t *b, int64_t deadline_us, can_msg_t *m)
{
    int64_t left = deadline_us - now_us();
    if (left < 0) {
        left = 0;
    }
    return xQueueReceive(b->iso, m, pdMS_TO_TICKS(left / 1000 + 1)) == pdTRUE;
}

// STmin в микросекундах (ISO 15765-2: 0–127 мс, F1–F9 — 100–900 мкс)
static int stmin_us(uint8_t v)
{
    if (v <= 0x7F) {
        return v * 1000;
    }
    if (v >= 0xF1 && v <= 0xF9) {
        return (v - 0xF0) * 100;
    }
    return 127000;
}

static void pause_us(int us)
{
    if (us <= 0) {
        return;
    }
    if (us < 2000) {
        esp_rom_delay_us(us);
    } else {
        vTaskDelay(pdMS_TO_TICKS(us / 1000) + 1);
    }
}

// Ответ на запрос с этим сервисом: положительный (sid + 40) или отказ (7F sid ..)
static bool looks_like_answer(const can_msg_t *m, uint8_t sid)
{
    if (m->ext || m->id < ANY_RX_MIN || m->id > ANY_RX_MAX || m->dlc < 2) {
        return false;
    }
    uint8_t pci = m->data[0] >> 4;
    if (pci == 0) {
        int l = m->data[0] & 15;
        if (l == 0 || l + 1 > m->dlc) {
            return false;
        }
        return m->data[1] == (uint8_t)(sid + 0x40) || (l >= 2 && m->data[1] == 0x7F && m->data[2] == sid);
    }
    return pci == 1 && m->dlc >= 3 && m->data[2] == (uint8_t)(sid + 0x40);
}

static void lock_rx(bus_t *b, bool *any, uint32_t *rx, uint32_t id)
{
    if (*any) {
        *any = false;
        *rx = id;
        b->want_id = id;
        b->want_any = false;
    }
}

// Запрос — ответ. NULL — успех (ответ в b->resp, длина *rlen, адрес *rx_out), иначе код ошибки протокола
static const char *isotp_xfer(bus_t *b, const job_t *j, int *rlen, uint32_t *rx_out)
{
    uint32_t rx = j->rx;
    bool any = j->any_rx;
    const uint8_t sid = j->data[0];
    const char *err = NULL;
    can_msg_t m;

    xQueueReset(b->iso);
    b->want_id = rx;
    b->want_any = any;
    b->want = true;

    // --- запрос
    if (j->len <= 7) {
        uint8_t f[8] = {(uint8_t)j->len};
        memcpy(f + 1, j->data, j->len);
        if (send_frame(b, j->tx, f, j->len + 1, j->pad) != ESP_OK) {
            err = "bus_off";
            goto out;
        }
    } else {
        uint8_t f[8] = {(uint8_t)(0x10 | (j->len >> 8)), (uint8_t)(j->len & 0xFF)};
        memcpy(f + 2, j->data, 6);
        if (send_frame(b, j->tx, f, 8, false) != ESP_OK) {
            err = "bus_off";
            goto out;
        }
        int pos = 6;
        uint8_t sn = 1;
        while (pos < j->len) {
            int64_t dl = now_us() + 1000000;
            int waits = 0;
            for (;;) {  // ждём «продолжай» (flow control)
                if (!wait_frame(b, dl, &m)) {
                    err = "timeout";
                    goto out;
                }
                if ((!any && m.id != rx) || (m.data[0] >> 4) != 3) {
                    continue;
                }
                lock_rx(b, &any, &rx, m.id);
                uint8_t fs = m.data[0] & 15;
                if (fs == 0) {
                    break;
                }
                if (fs == 1 && ++waits < 10) {
                    dl = now_us() + 1000000;
                    continue;
                }
                err = "timeout";  // блок отказался принимать (переполнение) или слишком долго просит ждать
                goto out;
            }
            int bs = m.dlc > 1 ? m.data[1] : 0;
            int st = stmin_us(m.dlc > 2 ? m.data[2] : 0);
            for (int sent = 0; pos < j->len && (bs == 0 || sent < bs); sent++) {
                uint8_t c[8] = {(uint8_t)(0x20 | (sn & 15))};
                int n = j->len - pos > 7 ? 7 : j->len - pos;
                memcpy(c + 1, j->data + pos, n);
                pause_us(st);
                if (send_frame(b, j->tx, c, n + 1, j->pad) != ESP_OK) {
                    err = "bus_off";
                    goto out;
                }
                pos += n;
                sn++;
            }
        }
    }

    // --- ответ
    int64_t deadline = now_us() + (int64_t)j->timeout_ms * 1000;
    for (;;) {
        if (!wait_frame(b, deadline, &m)) {
            err = "timeout";
            goto out;
        }
        if (any ? !looks_like_answer(&m, sid) : m.id != rx) {
            continue;
        }
        uint8_t pci = m.data[0] >> 4;
        if (pci == 0) {
            int l = m.data[0] & 15;
            if (l == 0 || l + 1 > m.dlc) {
                continue;
            }
            lock_rx(b, &any, &rx, m.id);
            if (l >= 3 && m.data[1] == 0x7F && m.data[3] == 0x78) {  // «ждите, обрабатываю»
                deadline = now_us() + 5000000;
                continue;
            }
            memcpy(b->resp, m.data + 1, l);
            *rlen = l;
            break;
        }
        if (pci == 1) {
            int total = ((m.data[0] & 15) << 8) | m.data[1];
            if (total < 7 || m.dlc < 8) {
                continue;
            }
            lock_rx(b, &any, &rx, m.id);
            int got = 6;
            memcpy(b->resp, m.data + 2, 6);
            uint8_t fc[3] = {0x30, 0x00, b->stmin};  // присылай всё, без блоков
            if (send_frame(b, j->tx, fc, 3, j->pad) != ESP_OK) {
                err = "bus_off";
                goto out;
            }
            uint8_t sn = 1;
            while (got < total) {
                if (!wait_frame(b, now_us() + 1000000, &m)) {
                    err = "timeout";
                    goto out;
                }
                if (m.id != rx || (m.data[0] >> 4) != 2) {
                    continue;
                }
                if ((m.data[0] & 15) != (sn & 15)) {
                    ESP_LOGW(TAG, "%c: потерян кадр ответа %03lX", b->name, (unsigned long)rx);
                    err = "timeout";
                    goto out;
                }
                int n = total - got > 7 ? 7 : total - got;
                if (n > m.dlc - 1) {
                    n = m.dlc - 1;
                }
                memcpy(b->resp + got, m.data + 1, n);
                got += n;
                sn++;
            }
            *rlen = total;
            break;
        }
        // кадры FC/CF не к месту — пропускаем
    }
    *rx_out = rx;
out:
    b->want = false;
    return err;
}

// ---------- работа шины ----------

static void close_bus(bus_t *b)
{
    for (int i = 0; i < TESTERS; i++) {
        b->tp[i].on = false;
    }
    b->mon_mode = 0;
    can_ch_stop(b->ch);
}

// После ошибки передачи кадр может остаться в очереди контроллера — перезапускаем канал
static void restart_bus(bus_t *b)
{
    bool listen = b->ch->listen_only;
    int bitrate = b->ch->bitrate;
    can_ch_start(b->ch, listen, bitrate);
}

static const char *need_tx(bus_t *b)
{
    if (!can_ch_is_open(b->ch)) {
        return "bus_closed";
    }
    if (b->ch->listen_only) {
        return "listen_only";
    }
    return NULL;
}

static void do_job(bus_t *b, job_t *j)
{
    const char *err;
    switch (j->kind) {
    case J_OPEN:
        if (can_ch_is_open(b->ch) && b->ch->listen_only == j->listen && b->ch->bitrate == j->bitrate) {
            reply(j, true, NULL, NULL);
            break;
        }
        if (can_ch_start(b->ch, j->listen, j->bitrate) != ESP_OK) {
            reply(j, false, "bad_args", NULL);
            break;
        }
        if (j->listen) {
            for (int i = 0; i < TESTERS; i++) {
                b->tp[i].on = false;
            }
        }
        reply(j, true, NULL, NULL);
        break;

    case J_CLOSE:
        close_bus(b);
        reply(j, true, NULL, NULL);
        break;

    case J_RESET:
        if (can_ch_is_open(b->ch)) {
            ESP_LOGI(TAG, "%c: приложение отключилось — закрываю шину", b->name);
        }
        close_bus(b);
        break;

    case J_ISOTP: {
        if ((err = need_tx(b)) != NULL) {
            reply(j, false, err, NULL);
            break;
        }
        int rlen = 0;
        uint32_t rx = 0;
        err = isotp_xfer(b, j, &rlen, &rx);
        if (err) {
            if (strcmp(err, "bus_off") == 0) {
                restart_bus(b);
            }
            reply(j, false, err, NULL);
            break;
        }
        char *extra = malloc(2 * rlen + 48);
        if (extra == NULL) {
            reply(j, false, "busy", NULL);
            break;
        }
        int n = sprintf(extra, ",\"rx\":\"%lX\",\"data\":\"", (unsigned long)rx);
        hex(extra + n, b->resp, rlen);
        strcat(extra, "\"");
        reply(j, true, NULL, extra);
        free(extra);
        break;
    }

    case J_TESTER_START: {
        if ((err = need_tx(b)) != NULL) {
            reply(j, false, err, NULL);
            break;
        }
        int slot = -1;
        for (int i = 0; i < TESTERS; i++) {
            if (b->tp[i].on && b->tp[i].tx == j->tx) {
                slot = i;
                break;
            }
            if (!b->tp[i].on && slot < 0) {
                slot = i;
            }
        }
        if (slot < 0) {
            reply(j, false, "busy", NULL);
            break;
        }
        b->tp[slot].tx = j->tx;
        b->tp[slot].len = j->len;
        memcpy(b->tp[slot].data, j->data, j->len);
        b->tp[slot].period_ms = j->period_ms;
        b->tp[slot].next_us = now_us();
        b->tp[slot].on = true;
        reply(j, true, NULL, NULL);
        break;
    }

    case J_TESTER_STOP:
        for (int i = 0; i < TESTERS; i++) {
            if (b->tp[i].tx == j->tx) {
                b->tp[i].on = false;
            }
        }
        reply(j, true, NULL, NULL);
        break;

    case J_MON_START:
        if (!can_ch_is_open(b->ch) && can_ch_start(b->ch, true, CAN_BITRATE) != ESP_OK) {
            reply(j, false, "bus_closed", NULL);
            break;
        }
        portENTER_CRITICAL(&b->mux);
        b->mon_count = 0;
        b->mon_n_ids = j->n_ids;
        memcpy(b->mon_ids, j->ids, sizeof(uint32_t) * j->n_ids);
        b->mon_mode = j->mode;
        portEXIT_CRITICAL(&b->mux);
        reply(j, true, NULL, NULL);
        break;

    case J_MON_STOP:
        b->mon_mode = 0;
        reply(j, true, NULL, NULL);
        break;
    }
}

static void tester_tick(bus_t *b)
{
    if (!can_ch_is_open(b->ch) || b->ch->listen_only) {
        return;
    }
    int64_t t = now_us();
    for (int i = 0; i < TESTERS; i++) {
        if (b->tp[i].on && t >= b->tp[i].next_us) {
            uint8_t f[8] = {b->tp[i].len};
            memcpy(f + 1, b->tp[i].data, b->tp[i].len);
            if (send_frame(b, b->tp[i].tx, f, b->tp[i].len + 1, b->pad) != ESP_OK) {
                restart_bus(b);
            }
            b->tp[i].next_us = t + (int64_t)b->tp[i].period_ms * 1000;
        }
    }
}

static TickType_t tester_wait(bus_t *b)
{
    int64_t next = INT64_MAX;
    for (int i = 0; i < TESTERS; i++) {
        if (b->tp[i].on && b->tp[i].next_us < next) {
            next = b->tp[i].next_us;
        }
    }
    if (next == INT64_MAX) {
        return portMAX_DELAY;
    }
    int64_t left = next - now_us();
    return left <= 0 ? 0 : pdMS_TO_TICKS(left / 1000 + 1);
}

static void worker_task(void *arg)
{
    bus_t *b = arg;
    for (;;) {
        job_t *j;
        if (xQueueReceive(b->jobs, &j, tester_wait(b)) == pdTRUE) {
            do_job(b, j);
            free(j);
        }
        tester_tick(b);
    }
}

// ---------- приём: всё, что пришло с шины ----------

static bool mon_wanted(bus_t *b, uint32_t id)
{
    if (b->mon_n_ids == 0) {
        return true;
    }
    for (int i = 0; i < b->mon_n_ids; i++) {
        if (b->mon_ids[i] == id) {
            return true;
        }
    }
    return false;
}

static void mon_add(bus_t *b, const can_msg_t *m)
{
    if (b->mon_mode == 2) {
        if (mon_wanted(b, m->id)) {
            char d[17], buf[128];
            hex(d, m->data, m->dlc);
            snprintf(buf, sizeof(buf), "{\"ev\":\"frame\",\"bus\":\"%c\",\"t_us\":%llu,\"id\":\"%03lX\",\"data\":\"%s\"}",
                     b->name, (unsigned long long)m->ts_us, (unsigned long)m->id, d);
            ws_broadcast(buf, true);
        }
        return;
    }
    if (!mon_wanted(b, m->id)) {
        return;
    }
    portENTER_CRITICAL(&b->mux);
    mon_ent_t *e = NULL;
    for (int i = 0; i < b->mon_count; i++) {
        if (b->mon[i].id == m->id) {
            e = &b->mon[i];
            break;
        }
    }
    if (e == NULL && b->mon_count < MON_MAX) {
        e = &b->mon[b->mon_count++];
        memset(e, 0, sizeof(*e));
        e->id = m->id;
    }
    if (e) {
        e->dlc = m->dlc;
        memcpy(e->data, m->data, m->dlc);
        e->n++;
    }
    portEXIT_CRITICAL(&b->mux);
}

static void rx_task(void *arg)
{
    bus_t *b = arg;
    can_msg_t m;
    for (;;) {
        if (b->ch->bus_off) {
            b->ch->bus_off = false;
            char buf[64];
            snprintf(buf, sizeof(buf), "{\"ev\":\"bus\",\"bus\":\"%c\",\"state\":\"bus_off\"}", b->name);
            ws_broadcast(buf, false);
            ESP_LOGW(TAG, "%c: bus-off", b->name);
        }
        if (!can_ch_recv(b->ch, &m, 100)) {
            continue;
        }
        if (b->want && !m.ext && (b->want_any || m.id == b->want_id)) {
            xQueueSend(b->iso, &m, 0);
        }
        if (b->mon_mode) {
            mon_add(b, &m);
        }
        if (b->print) {
            printf("%10.3f %c %03lX [%u]", m.ts_us / 1e6, b->name, (unsigned long)m.id, m.dlc);
            for (int i = 0; i < m.dlc; i++) {
                printf(" %02X", m.data[i]);
            }
            printf("\n");
        }
    }
}

// ---------- события: напряжение раз в секунду, сводка монитора 4 раза в секунду ----------

static void summary(bus_t *b, int64_t t_ms, bool new_second)
{
    static mon_ent_t copy[MON_MAX];
    portENTER_CRITICAL(&b->mux);
    int n = b->mon_count;
    if (new_second) {
        for (int i = 0; i < n; i++) {
            b->mon[i].hz = b->mon[i].n - b->mon[i].n_mark;
            b->mon[i].n_mark = b->mon[i].n;
        }
    }
    memcpy(copy, b->mon, sizeof(mon_ent_t) * n);
    portEXIT_CRITICAL(&b->mux);

    size_t cap = 96 + (size_t)n * 72;
    char *buf = malloc(cap);
    if (buf == NULL) {
        return;
    }
    size_t p = snprintf(buf, cap, "{\"ev\":\"frames\",\"bus\":\"%c\",\"t\":%lld,\"frames\":[", b->name, (long long)t_ms);
    for (int i = 0; i < n; i++) {
        char d[17];
        hex(d, copy[i].data, copy[i].dlc);
        p += snprintf(buf + p, cap - p, "%s{\"id\":\"%03lX\",\"data\":\"%s\",\"n\":%lu,\"hz\":%lu}", i ? "," : "",
                      (unsigned long)copy[i].id, d, (unsigned long)copy[i].n, (unsigned long)copy[i].hz);
    }
    snprintf(buf + p, cap - p, "]}");
    ws_broadcast(buf, true);
    free(buf);
}

static int vbat_mv(void)
{
    float v = vbat_read();
    return v > 0 ? (int)(v * 1000) : 0;
}

static void events_task(void *arg)
{
    TickType_t last = xTaskGetTickCount();
    for (int tick = 0;; tick++) {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(250));
        if (ws_client_count() == 0) {
            continue;
        }
        bool new_second = tick % 4 == 0;
        int64_t t_ms = now_us() / 1000;
        for (int i = 0; i < 2; i++) {
            if (s_bus[i].mon_mode == 1) {
                summary(&s_bus[i], t_ms, new_second);
            }
        }
        if (new_second) {
            char buf[48];
            snprintf(buf, sizeof(buf), "{\"ev\":\"vbat\",\"mv\":%d}", vbat_mv());
            ws_broadcast(buf, true);
        }
    }
}

// ---------- команды приложения ----------

static const char *jstr(const cJSON *o, const char *k)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    return cJSON_IsString(v) ? v->valuestring : NULL;
}

static int jint(const cJSON *o, const char *k, int def)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    return cJSON_IsNumber(v) ? v->valueint : def;
}

static bool jbool(const cJSON *o, const char *k, bool def)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    return cJSON_IsBool(v) ? cJSON_IsTrue(v) : def;
}

static bool jhexid(const cJSON *o, const char *k, uint32_t *out)
{
    const char *s = jstr(o, k);
    if (s == NULL || *s == 0 || strlen(s) > 8) {
        return false;
    }
    char *end;
    unsigned long v = strtoul(s, &end, 16);
    if (*end) {
        return false;
    }
    *out = v;
    return true;
}

void proto_on_text(int fd, const char *txt, size_t len)
{
    job_t head = {.fd = fd};
    cJSON *root = cJSON_ParseWithLength(txt, len);
    const cJSON *jid = root ? cJSON_GetObjectItemCaseSensitive(root, "id") : NULL;
    if (cJSON_IsNumber(jid)) {
        head.has_id = true;
        head.id = jid->valuedouble;
    }
    const char *cmd = root ? jstr(root, "cmd") : NULL;
    if (cmd == NULL) {
        reply(&head, false, "bad_args", NULL);
        goto done;
    }

    if (strcmp(cmd, "hello") == 0) {
        char extra[160];
        snprintf(extra, sizeof(extra), ",\"fw\":\"%s (%s)\",\"hw\":\"xiao-esp32c5-v1\",\"buses\":[\"A\",\"B\"],\"mv\":%d",
                 FW_VERSION, esp_app_get_description()->version, vbat_mv());
        reply(&head, true, NULL, extra);
        goto done;
    }
    if (strcmp(cmd, "vbat") == 0) {
        char extra[32];
        snprintf(extra, sizeof(extra), ",\"mv\":%d", vbat_mv());
        reply(&head, true, NULL, extra);
        goto done;
    }

    bus_t *b = bus_by_name(jstr(root, "bus"));
    if (b == NULL) {
        reply(&head, false, "bad_args", NULL);
        goto done;
    }

    // данные запроса (isotp.req, tester.start)
    const char *hexdata = jstr(root, "data");
    int max = strcmp(cmd, "tester.start") == 0 ? 7 : ISOTP_MAX;
    uint8_t *tmp = NULL;
    int n = 0;
    if (hexdata) {
        tmp = malloc(strlen(hexdata) / 2 + 1);
        n = tmp ? unhex(hexdata, tmp, max) : -1;
    }

    job_t *j = calloc(1, sizeof(job_t) + (n > 0 ? n : 0));
    if (j == NULL) {
        free(tmp);
        reply(&head, false, "busy", NULL);
        goto done;
    }
    *j = head;
    j->pad = jbool(root, "pad", b->pad);
    bool ok = true;

    if (strcmp(cmd, "bus.open") == 0) {
        j->kind = J_OPEN;
        j->listen = jbool(root, "listen", true);
        j->bitrate = jint(root, "bitrate", CAN_BITRATE);
    } else if (strcmp(cmd, "bus.close") == 0) {
        j->kind = J_CLOSE;
    } else if (strcmp(cmd, "isotp.req") == 0) {
        j->kind = J_ISOTP;
        const char *rx = jstr(root, "rx");
        j->any_rx = rx && strcmp(rx, "*") == 0;
        ok = jhexid(root, "tx", &j->tx) && (j->any_rx || jhexid(root, "rx", &j->rx)) && n > 0;
        j->timeout_ms = jint(root, "timeout_ms", 1000);
        if (j->timeout_ms < 10 || j->timeout_ms > 10000) {
            j->timeout_ms = 1000;
        }
    } else if (strcmp(cmd, "tester.start") == 0) {
        j->kind = J_TESTER_START;
        ok = jhexid(root, "tx", &j->tx) && n > 0;
        j->period_ms = jint(root, "period_ms", 2000);
        if (j->period_ms < 100) {
            j->period_ms = 100;
        }
    } else if (strcmp(cmd, "tester.stop") == 0) {
        j->kind = J_TESTER_STOP;
        ok = jhexid(root, "tx", &j->tx);
    } else if (strcmp(cmd, "monitor.start") == 0) {
        j->kind = J_MON_START;
        const char *mode = jstr(root, "mode");
        j->mode = mode && strcmp(mode, "raw") == 0 ? 2 : 1;
        const cJSON *ids = cJSON_GetObjectItemCaseSensitive(root, "ids");
        const cJSON *it;
        cJSON_ArrayForEach(it, ids) {
            if (cJSON_IsString(it) && j->n_ids < MON_IDS) {
                j->ids[j->n_ids++] = strtoul(it->valuestring, NULL, 16);
            }
        }
    } else if (strcmp(cmd, "monitor.stop") == 0) {
        j->kind = J_MON_STOP;
    } else {
        ok = false;
    }

    if (ok && n > 0) {
        memcpy(j->data, tmp, n);
        j->len = n;
    }
    free(tmp);
    if (!ok) {
        reply(&head, false, "bad_args", NULL);
        free(j);
    } else if (xQueueSend(b->jobs, &j, 0) != pdTRUE) {
        reply(&head, false, "busy", NULL);
        free(j);
    }
done:
    cJSON_Delete(root);
}

void proto_on_no_clients(void)
{
    for (int i = 0; i < 2; i++) {
        job_t *j = calloc(1, sizeof(job_t));
        if (j) {
            j->kind = J_RESET;
            j->fd = -1;
            if (xQueueSend(s_bus[i].jobs, &j, pdMS_TO_TICKS(100)) != pdTRUE) {
                free(j);
            }
        }
    }
}

// ---------- консоль ----------

void proto_console_print(bool on)
{
    s_bus[0].print = on;
    s_bus[1].print = on;
}

void proto_tap_begin(char bus, uint32_t id)
{
    bus_t *b = &s_bus[bus == 'A' ? 0 : 1];
    xQueueReset(b->iso);
    b->want_id = id;
    b->want_any = false;
    b->want = true;
}

bool proto_tap_get(char bus, can_msg_t *m, int timeout_ms)
{
    return xQueueReceive(s_bus[bus == 'A' ? 0 : 1].iso, m, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

void proto_tap_end(char bus)
{
    s_bus[bus == 'A' ? 0 : 1].want = false;
}

// ---------- запуск ----------

void proto_init(can_ch_t *a, can_ch_t *b)
{
    can_ch_t *chs[2] = {a, b};
    for (int i = 0; i < 2; i++) {
        bus_t *x = &s_bus[i];
        x->name = i == 0 ? 'A' : 'B';
        x->ch = chs[i];
        x->pad = i == 0;          // OBD-II требует кадры по 8 байт
        x->stmin = i == 0 ? 0 : 5; // PSA: как у ludwig-v, 5 мс между кадрами ответа
        x->mux = (portMUX_TYPE)portMUX_INITIALIZER_UNLOCKED;
        x->jobs = xQueueCreate(16, sizeof(job_t *));
        x->iso = xQueueCreate(64, sizeof(can_msg_t));
        char name[16];
        snprintf(name, sizeof(name), "bus%c_rx", x->name);
        xTaskCreate(rx_task, name, 4096, x, 6, NULL);
        snprintf(name, sizeof(name), "bus%c_job", x->name);
        xTaskCreate(worker_task, name, 6144, x, 5, NULL);
    }
    xTaskCreate(events_task, "events", 4096, NULL, 4, NULL);
}
