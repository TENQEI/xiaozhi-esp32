#include "announcement_mcp_tools.h"
#include "application.h"
#include "button.h"
#include "codecs/no_audio_codec.h"
#include "config.h"
#include "hourly_chime.h"
#include "led/gpio_led.h"
#include "microphone_filter.h"
#include "time_config_web.h"
#include "wifi_board.h"

namespace {

class FlowerS3Board : public WifiBoard {
private:
    Button boot_button_{BOOT_BUTTON_GPIO, false, 3000};
    Button main_button_{MAIN_BUTTON_GPIO, false, 3000};
    Button restart_button_{RESTART_BUTTON_GPIO};
    flower::GreetingTimeSettings greeting_times_;
    flower::FlowerAudioManager audio_manager_;
    flower::HourlyChime hourly_chime_{greeting_times_, audio_manager_};
    flower::TimeConfigWeb time_config_web_{greeting_times_};

    void InitializeTools() { flower::InitializeAnnouncementTools(greeting_times_); }

    class FlowerAudioCodec : public NoAudioCodecSimplex {
    protected:
        int Read(int16_t* dest, int samples) override {
            const int count = NoAudioCodecSimplex::Read(dest, samples);
            microphone_filter_.Process(dest, count);
            return count;
        }

    private:
        flower::MicrophoneFilter microphone_filter_;

    public:
        FlowerAudioCodec()
            : NoAudioCodecSimplex(AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
                                  AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK,
                                  AUDIO_I2S_SPK_GPIO_DOUT, AUDIO_I2S_MIC_GPIO_SCK,
                                  AUDIO_I2S_MIC_GPIO_WS, AUDIO_I2S_MIC_GPIO_DIN) {
            static_assert(AUDIO_INPUT_SAMPLE_RATE == flower::MicrophoneFilter::kSampleRate);
            // Start quietly on a new device; AudioCodec::Start restores saved volume.
            output_volume_ = 20;
        }
    };

public:
    FlowerS3Board() {
        Button* buttons[] = {&boot_button_, &main_button_};
        for (auto* button : buttons) {
            button->OnClick([this]() {
                Application::GetInstance().Schedule([this]() {
                    auto& app = Application::GetInstance();
                    if (app.GetDeviceState() == kDeviceStateStarting) {
                        EnterWifiConfigMode();
                        return;
                    }
                    app.ToggleChatState();
                });
            });
            button->OnLongPress([this]() {
                Application::GetInstance().Schedule([this]() { EnterWifiConfigMode(); });
            });
            button->OnDoubleClick([this]() {
                Application::GetInstance().Schedule([this]() { audio_manager_.PlayPhrase(); });
            });
        }
        restart_button_.OnClick([]() {
            auto& app = Application::GetInstance();
            app.Schedule([]() { Application::GetInstance().Reboot(); });
        });
        InitializeTools();
    }

    void OnClockTick() override { hourly_chime_.Tick(); }
    std::string_view GetStartupSound() override { return audio_manager_.StartupSound(); }
    std::string_view GetSessionSound(bool starting) override {
        return audio_manager_.SessionSound(starting);
    }
    void OnSessionSoundStarted(bool starting) override {
        audio_manager_.CommitSessionSound(starting);
    }

    void SetNetworkEventCallback(NetworkEventCallback callback) override {
        WifiBoard::SetNetworkEventCallback(
            [this, callback = std::move(callback)](NetworkEvent event, const std::string& data) {
                if (event == NetworkEvent::Connected) {
                    time_config_web_.SetConnected(true);
                } else if (event == NetworkEvent::Disconnected ||
                           event == NetworkEvent::WifiConfigModeEnter) {
                    time_config_web_.SetConnected(false);
                }
                if (callback) {
                    callback(event, data);
                }
            });
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
