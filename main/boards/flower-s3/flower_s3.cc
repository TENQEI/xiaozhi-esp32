#include "application.h"
#include "button.h"
#include "codecs/no_audio_codec.h"
#include "config.h"
#include "led/gpio_led.h"
#include "wifi_board.h"

namespace {

class FlowerS3Board : public WifiBoard {
private:
    Button boot_button_{BOOT_BUTTON_GPIO, false, 3000};

    class FlowerAudioCodec : public NoAudioCodecSimplex {
    public:
        FlowerAudioCodec()
            : NoAudioCodecSimplex(AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
                                  AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK,
                                  AUDIO_I2S_SPK_GPIO_DOUT, AUDIO_I2S_MIC_GPIO_SCK,
                                  AUDIO_I2S_MIC_GPIO_WS, AUDIO_I2S_MIC_GPIO_DIN) {
            // Start quietly on a new device; AudioCodec::Start restores saved volume.
            output_volume_ = 20;
        }
    };

public:
    FlowerS3Board() {
        boot_button_.OnClick([this]() {
            Application::GetInstance().Schedule([this]() {
                auto& app = Application::GetInstance();
                if (app.GetDeviceState() == kDeviceStateStarting) {
                    EnterWifiConfigMode();
                    return;
                }
                app.ToggleChatState();
            });
        });
        boot_button_.OnLongPress(
            [this]() { Application::GetInstance().Schedule([this]() { EnterWifiConfigMode(); }); });
    }

    AudioCodec* GetAudioCodec() override {
        static FlowerAudioCodec codec;
        return &codec;
    }

    Led* GetLed() override {
        static GpioLed led(BUILTIN_LED_GPIO, BUILTIN_LED_OUTPUT_INVERT);
        return &led;
    }

    // Board::GetDisplay() supplies NoDisplay; no display bus is initialized.
};

}  // namespace

DECLARE_BOARD(FlowerS3Board);
