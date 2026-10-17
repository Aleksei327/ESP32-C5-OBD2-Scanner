#include "vbat.h"

#include "board.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"

static const char *TAG = "vbat";
static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali;
static adc_channel_t s_chan;

esp_err_t vbat_init(void)
{
    adc_unit_t unit;
    ESP_ERROR_CHECK(adc_oneshot_io_to_channel(VBAT_ADC_GPIO, &unit, &s_chan));
    adc_oneshot_unit_init_cfg_t ucfg = {.unit_id = unit};
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&ucfg, &s_adc));
    adc_oneshot_chan_cfg_t ccfg = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc, s_chan, &ccfg));
#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    adc_cali_curve_fitting_config_t cal = {
        .unit_id = unit, .chan = s_chan, .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_cali_create_scheme_curve_fitting(&cal, &s_cali) != ESP_OK) {
        s_cali = NULL;
    }
#endif
    if (s_cali == NULL) {
        ESP_LOGW(TAG, "калибровки АЦП нет, напряжение будет приблизительным");
    }
    return ESP_OK;
}

float vbat_read(void)
{
    int sum = 0;
    for (int i = 0; i < 16; i++) {
        int raw = 0;
        if (adc_oneshot_read(s_adc, s_chan, &raw) != ESP_OK) {
            return -1.0f;
        }
        sum += raw;
    }
    int raw = sum / 16;
    int mv = 0;
    if (s_cali == NULL || adc_cali_raw_to_voltage(s_cali, raw, &mv) != ESP_OK) {
        mv = raw * 3300 / 4095;
    }
    if (mv < 50) {
        return 0.0f;  // машины нет, питание от USB
    }
    return mv / 1000.0f * VBAT_DIVIDER + VBAT_DIODE_DROP;
}
