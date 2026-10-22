#include "wifi_ap.h"

#include <stdio.h>
#include <string.h>
#include "bootloader_random.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_wifi.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "wifi";
static const char *NVS_NS = "scaner";

static char s_ssid[33];
static char s_pass[65];
static volatile int s_clients;
static void (*s_on_empty)(void);

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (id == WIFI_EVENT_AP_STACONNECTED) {
        const wifi_event_ap_staconnected_t *e = data;
        s_clients++;
        ESP_LOGI(TAG, "подключился " MACSTR ", всего %d", MAC2STR(e->mac), s_clients);
    } else if (id == WIFI_EVENT_AP_STADISCONNECTED) {
        const wifi_event_ap_stadisconnected_t *e = data;
        if (s_clients > 0) {
            s_clients--;
        }
        ESP_LOGI(TAG, "отключился " MACSTR ", осталось %d", MAC2STR(e->mac), s_clients);
        if (s_clients == 0 && s_on_empty) {
            s_on_empty();
        }
    }
}

// Пароль без похожих символов (0/O, 1/l/I) — его вводят руками в телефоне
static void make_pass(char *out, size_t n)
{
    static const char abc[] = "abcdefghjkmnpqrstuvwxyz23456789";
    bootloader_random_enable();  // настоящий ГСЧ, пока радио ещё не запущено
    for (size_t i = 0; i < n; i++) {
        out[i] = abc[esp_random() % (sizeof(abc) - 1)];
    }
    bootloader_random_disable();
    out[n] = 0;
}

static void load_pass(void)
{
    nvs_handle_t h;
    size_t len = sizeof(s_pass);
    if (nvs_open(NVS_NS, NVS_READWRITE, &h) != ESP_OK) {
        make_pass(s_pass, 10);
        return;
    }
    if (nvs_get_str(h, "wifi_pass", s_pass, &len) != ESP_OK || strlen(s_pass) < 8) {
        make_pass(s_pass, 10);
        nvs_set_str(h, "wifi_pass", s_pass);
        nvs_commit(h);
        ESP_LOGI(TAG, "создан новый пароль Wi-Fi");
    }
    nvs_close(h);
}

static esp_err_t apply_config(void)
{
    wifi_config_t cfg = {
        .ap = {
            .channel = 6,
            .max_connection = 2,
            .authmode = WIFI_AUTH_WPA2_PSK,
            .pmf_cfg = {.required = false},
        },
    };
    strncpy((char *)cfg.ap.ssid, s_ssid, sizeof(cfg.ap.ssid));
    cfg.ap.ssid_len = strlen(s_ssid);
    strncpy((char *)cfg.ap.password, s_pass, sizeof(cfg.ap.password));
    return esp_wifi_set_config(WIFI_IF_AP, &cfg);
}

esp_err_t wifi_ap_start(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    load_pass();

    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
    snprintf(s_ssid, sizeof(s_ssid), "SCANER-C5-%02X%02X", mac[4], mac[5]);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(apply_config());
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_wifi_set_ps(WIFI_PS_NONE);  // без энергосбережения: задержки ответа в единицы мс
    ESP_LOGI(TAG, "точка доступа %s, адрес ws://192.168.4.1:81/ws", s_ssid);
    return ESP_OK;
}

const char *wifi_ap_ssid(void) { return s_ssid; }
const char *wifi_ap_pass(void) { return s_pass; }
int wifi_ap_clients(void) { return s_clients; }
void wifi_ap_on_empty(void (*cb)(void)) { s_on_empty = cb; }

esp_err_t wifi_ap_set_pass(const char *pass)
{
    size_t n = strlen(pass);
    if (n < 8 || n > 63) {
        return ESP_ERR_INVALID_ARG;
    }
    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NS, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        return err;
    }
    err = nvs_set_str(h, "wifi_pass", pass);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    if (err != ESP_OK) {
        return err;
    }
    strcpy(s_pass, pass);
    return apply_config();  // подключённые телефоны отключатся и войдут с новым паролем
}
