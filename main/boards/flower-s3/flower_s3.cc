#include <esp_log.h>
#include <esp_pm.h>
#include <wifi_manager.h>
#include <algorithm>
#include "announcement_mcp_tools.h"
#include "application.h"
#include "assets/lang_config.h"
#include "button.h"
#include "codecs/no_audio_codec.h"
#include "config.h"
#include "hourly_chime.h"
#include "led/gpio_led.h"
#include "microphone_filter.h"
#include "power_policy.h"
#include "wifi_board.h"

namespace {

class FlowerS3Board : public WifiBoard {
private:
    Button boot_button_{BOOT_BUTTON_GPIO, false, 3000, 0, true};
    Button main_button_{MAIN_BUTTON_GPIO, false, 3000, 0, true};
    Button restart_button_{RESTART_BUTTON_GPIO, false, 3000, 0, true};
    flower::GreetingTimeSettings greeting_times_;
    flower::FlowerAudioManager audio_manager_;
    flower::HourlyChime hourly_chime_{greeting_times_, audio_manager_};

    flower::PowerPolicy power_;
    bool offline_ = false;
    bool reconnecting_ = false;
    bool button_pending_ = false;
    bool config_pending_ = false;
    bool light_sleep_ = false;
    int64_t connection_deadline_ = 0;
    int64_t wake_deadline_ = 0;
    esp_timer_handle_t wake_timer_ = nullptr;

    void SetLightSleep(bool enabled) {
        if (light_sleep_ == enabled)
            return;
        esp_pm_config_t config = {};
        config.max_freq_mhz = CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ;
        config.min_freq_mhz = enabled ? 40 : CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ;
        config.light_sleep_enable = enabled;
        ESP_ERROR_CHECK(esp_pm_configure(&config));
        light_sleep_ = enabled;
        ESP_LOGI("FlowerPower", "%s", enabled ? "Offline auto Light-sleep enabled" : "CPU awake");
    }

    void ArmWakeTimer() {
        const auto now = std::time(nullptr);
        const auto monotonic = esp_timer_get_time();
        const auto next = flower::NextAnnouncementWake(
            now, greeting_times_.GetSchedule(),
            audio_manager_.AutomaticEnabled() && greeting_times_.AnnouncementsEnabled(),
            audio_manager_.GreetingEnabled(true), audio_manager_.GreetingEnabled(false));
        // Wake two seconds early so ChimeSchedule can distinguish normal passage
        // of time from a clock jump, then tick through the actual boundary.
        int64_t deadline = next ? monotonic + std::max<int64_t>(1, next - now - 2) * 1000000 : 0;
        if (hourly_chime_.NextPhraseUs() != 0 &&
            (deadline == 0 || hourly_chime_.NextPhraseUs() < deadline))
            deadline = std::max(monotonic + 1000000, hourly_chime_.NextPhraseUs());
        if (deadline == 0) {
            esp_timer_stop(wake_timer_);
            wake_deadline_ = 0;
        } else if (wake_deadline_ == 0 || deadline < wake_deadline_ - 500000 ||
                   wake_deadline_ <= monotonic) {
            esp_timer_stop(wake_timer_);
            ESP_ERROR_CHECK(esp_timer_start_once(wake_timer_, deadline - monotonic));
            wake_deadline_ = deadline;
        }
    }

    void HandleButton() {
        button_pending_ = false;
        auto& app = Application::GetInstance();
        SetLightSleep(false);
        hourly_chime_.ResetPhraseTimer();
        if (reconnecting_ || app.HasBufferedConversation()) {
            reconnecting_ = false;
            app.CancelBufferedConversation();
            power_.Expire();
            return;
        }
        if (app.GetDeviceState() == kDeviceStateStarting) {
            EnterWifiConfigMode();
            return;
        }
        if (app.GetDeviceState() != kDeviceStateIdle &&
            app.GetDeviceState() != kDeviceStateNotifying) {
            app.ToggleChatState();
            return;
        }
        WifiBoard::SetPowerSaveLevel(PowerSaveLevel::PERFORMANCE);
        if (!offline_ && WifiManager::GetInstance().IsConnected()) {
            app.ToggleChatState();  // Preserve the existing online session-start cue.
            return;
        }
        if (!app.BeginBufferedConversation()) {
            button_pending_ = true;
            return;
        }
        button_pending_ = false;
        reconnecting_ = true;
        connection_deadline_ = esp_timer_get_time() + 8LL * 1000000;
        // StartStation is asynchronous. Keep recording while association/DHCP run.
        if (offline_ || !WifiManager::GetInstance().IsConnected()) {
            offline_ = false;
            WifiManager::GetInstance().StartStation();
        }
    }

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
            button->OnClick(
                [this]() { Application::GetInstance().Schedule([this]() { HandleButton(); }); });
            button->OnLongPress([this]() {
                Application::GetInstance().Schedule([this]() {
                    SetLightSleep(false);
                    offline_ = false;
                    reconnecting_ = false;
                    auto& app = Application::GetInstance();
                    app.CancelBufferedConversation();
                    button_pending_ = false;
                    if (app.IsConnectionOpening()) {
                        config_pending_ = true;
                        return;
                    }
                    EnterWifiConfigMode();
                });
            });
            button->OnDoubleClick([this]() {
                Application::GetInstance().Schedule([this]() {
                    SetLightSleep(false);
                    hourly_chime_.ResetPhraseTimer();
                    audio_manager_.PlayPhrase();
                });
            });
        }
        restart_button_.OnClick([]() {
            auto& app = Application::GetInstance();
            app.Schedule([]() { Application::GetInstance().Reboot(); });
        });
        esp_timer_create_args_t timer = {};
        timer.callback = [](void* arg) {
            auto* self = static_cast<FlowerS3Board*>(arg);
            Application::GetInstance().Schedule([self]() {
                self->wake_deadline_ = 0;
                self->hourly_chime_.Tick();
            });
        };
        timer.arg = this;
        timer.name = "flower_wake";
        ESP_ERROR_CHECK(esp_timer_create(&timer, &wake_timer_));
        InitializeTools();
    }

    bool UsesWakeWord() const override { return false; }
    PowerSaveLevel LocalPlaybackPowerLevel() const override { return PowerSaveLevel::LOW_POWER; }
    void OnClockTick() override { hourly_chime_.Tick(); }

    void OnApplicationEvent() override {
        auto& app = Application::GetInstance();
        const auto now = esp_timer_get_time();
        if (config_pending_ && !app.IsConnectionOpening()) {
            config_pending_ = false;
            EnterWifiConfigMode();
        }
        if (button_pending_ && app.GetDeviceState() == kDeviceStateIdle &&
            app.GetAudioService().IsPlaybackIdle())
            HandleButton();
        if (reconnecting_) {
            if (!app.HasBufferedConversation()) {
                reconnecting_ = false;
            } else if (now >= connection_deadline_) {
                reconnecting_ = false;
                app.CancelBufferedConversation();
                power_.Expire();
                app.PlaySound(Lang::Sounds::OGG_EXCLAMATION);
            } else if (WifiManager::GetInstance().IsConnected()) {
                reconnecting_ = false;
                app.ConnectBufferedConversation();
            }
        }
        const auto state = app.GetDeviceState();
        const bool conversation = state == kDeviceStateConnecting ||
                                  state == kDeviceStateListening || state == kDeviceStateSpeaking ||
                                  app.HasBufferedConversation();
        const bool idle = state == kDeviceStateIdle && app.CanEnterSleepMode();
        const bool expired = power_.Poll(now, conversation, idle);
        if (!idle || IsInWifiConfigMode()) {
            SetLightSleep(false);
            return;
        }
        if (expired && !offline_ && app.PrepareForNetworkSleep()) {
            offline_ = true;  // Suppress the intentional disconnect notification.
            esp_timer_stop(connect_timer_);
            WifiManager::GetInstance().StopStation();
            ESP_LOGI("FlowerPower", "Five-minute standby expired; WiFi stopped");
        }
        if (offline_ && app.PrepareForNetworkSleep()) {
            hourly_chime_.Tick();
            if (app.GetDeviceState() != kDeviceStateIdle) {
                SetLightSleep(false);
                return;
            }
            ArmWakeTimer();
            static_cast<GpioLed*>(GetLed())->TurnOff();
            SetLightSleep(true);
        } else if (!offline_) {
            WifiBoard::SetPowerSaveLevel(PowerSaveLevel::LOW_POWER);
        }
    }
    std::string_view GetStartupSound() override { return audio_manager_.StartupSound(); }
    std::string_view GetWifiConfigSound() override { return audio_manager_.WifiConfigSound(); }
    float GetLocalPlaybackGain() const override { return 1.5848932f; }  // +4 dB
    std::string_view GetSessionSound(bool starting) override {
        return audio_manager_.SessionSound(starting);
    }
    void OnSessionSoundStarted(bool starting) override {
        audio_manager_.CommitSessionSound(starting);
    }

    void SetNetworkEventCallback(NetworkEventCallback callback) override {
        WifiBoard::SetNetworkEventCallback(
            [this, callback = std::move(callback)](NetworkEvent event, const std::string& data) {
                Application::GetInstance().Schedule([this, callback, event, data]() {
                    if ((offline_ || reconnecting_ ||
                         Application::GetInstance().IsConnectionOpening()) &&
                        (event == NetworkEvent::Disconnected || event == NetworkEvent::Scanning))
                        return;
                    if (callback)
                        callback(event, data);
                });
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
