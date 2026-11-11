"""Execute Flower's actual standby policy and civil wake schedule on the host."""
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/flower-s3"


class FlowerPowerTest(unittest.TestCase):
    def test_deadlines_wake_schedule_and_no_catchup(self):
        source = r'''
#include "power_policy.h"
#include <cassert>
using namespace flower;
std::time_t date(int day, int hour, int minute=0, int second=0) {
    std::tm t = {}; t.tm_year=126; t.tm_mon=10; t.tm_mday=day;
    t.tm_hour=hour; t.tm_min=minute; t.tm_sec=second; return timegm(&t);
}
int main() {
    constexpr int64_t S=1000000;
    PowerPolicy p;
    assert(!p.Poll(0, false, false)); // boot/activation cannot sleep
    assert(!p.Poll(10*S, false, true));
    assert(!p.Poll(309*S, false, true));
    assert(p.Poll(310*S, false, true));
    assert(!p.Poll(311*S, true, false)); // button starts a multi-turn session
    assert(!p.Poll(9999*S, true, false)); // no timeout between turns
    assert(!p.Poll(10000*S, false, false)); // end cue starts the standby window
    assert(!p.Poll(10299*S, false, true));
    assert(!p.Poll(10300*S, false, false)); // a local clip spans the deadline
    assert(p.Poll(10310*S, false, true)); // local clip did NOT reset it
    assert(!p.Poll(10311*S, true, false));
    assert(!p.Poll(10312*S, false, true));
    assert(!p.Poll(10611*S, false, true));
    assert(p.Poll(10612*S, false, true)); // new session earns a fresh five minutes
    p.Expire(); assert(p.Poll(10613*S, false, true));

    GreetingSchedule settings{{8*60+30, 20*60+15}, {9*60+30, 22*60+15}};
    auto next = [&](std::time_t t, bool enabled=true, bool morning=true, bool night=true) {
        return NextAnnouncementWake(t, settings, enabled, morning, night);
    };
    assert(next(0)==0); // uncalibrated cold boot cannot invent an event
    assert(next(date(9,7),false)==0); // globally muted: no periodic hour wake
    assert(next(date(9,7))==date(9,8,30)); // skip ineligible 08:00
    assert(next(date(9,8,30))==date(9,9));
    assert(next(date(9,20,1))==date(9,20,15)); // non-hour goodnight
    assert(next(date(9,20,16))==date(10,8,30)); // no overnight hour wake
    assert(next(date(6,20,16))==date(7,9,30)); // Friday -> Saturday
    assert(next(date(8,22,16))==date(9,8,30)); // Sunday -> Monday
    assert(next(date(9,20,1),true,true,false)==date(10,8,30));
    settings.workday = {480,1200};
    assert(next(date(9,7))==date(9,8));
    ChimeConfig c{12,true,20,8,true,true,0,0};
    ChimeSchedule clock;
    auto morning=date(9,8);
    assert(clock.Poll(morning-2,c,true)==-1); // prewake seeds clock
    assert(clock.Poll(morning-1,c,true)==-1);
    assert(clock.Poll(morning,c,true)==ChimeSchedule::kGoodMorning);
    assert(clock.Poll(morning,c,true)==-1); // coalesced timer callbacks cannot duplicate
    assert(clock.Poll(morning-1,c,true)==-1);
    assert(clock.Poll(morning,c,true)==-1); // backward clock adjustment
    assert(clock.Poll(date(9,9),c,true)==-1); // clock jump cannot catch up
    clock.Poll(date(9,10)-1,c,true);
    assert(clock.Poll(date(9,10),c,false)==-1); // conversation wins
    assert(clock.Poll(date(9,10)+1,c,true)==-1); // busy event never catches up
    settings.workday={480,480};
    assert(next(date(9,23,1))==date(10,0)); // no quiet window
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test.cc").write_text(source)
            compiler = shlex.split(os.environ.get("CXX", "c++"))
            subprocess.run(compiler + ["-std=c++20", "-Wall", "-Wextra", "-Werror",
                                       f"-I{BOARD}", str(root / "test.cc"), "-o", str(root / "test")], check=True)
            subprocess.run([str(root / "test")], check=True)

    def test_board_transitions_with_wifi_audio_and_timer_doubles(self):
        fake = r'''
#pragma once
#include <cassert>
#include <cstdint>
#include <functional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
#include "greeting_schedule.h"
using gpio_num_t=int;
constexpr int BOOT_BUTTON_GPIO=0,MAIN_BUTTON_GPIO=1,RESTART_BUTTON_GPIO=2;
constexpr int AUDIO_INPUT_SAMPLE_RATE=16000,AUDIO_OUTPUT_SAMPLE_RATE=24000;
constexpr int AUDIO_I2S_SPK_GPIO_BCLK=7,AUDIO_I2S_SPK_GPIO_LRCK=8,AUDIO_I2S_SPK_GPIO_DOUT=9;
constexpr int AUDIO_I2S_MIC_GPIO_SCK=5,AUDIO_I2S_MIC_GPIO_WS=4,AUDIO_I2S_MIC_GPIO_DIN=6;
constexpr int BUILTIN_LED_GPIO=21,BUILTIN_LED_OUTPUT_INVERT=1;
#define CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ 240
#define CONFIG_PM_LIGHT_SLEEP_CALLBACKS 1
#define CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG 1
#define ESP_LOGI(...) ((void)0)
#define ESP_ERROR_CHECK(x) assert((x)==0)
inline int64_t monotonic=0;
int64_t esp_timer_get_time(){return monotonic;}
struct Timer {std::function<void()> callback; int64_t delay=0;};
using esp_timer_handle_t=Timer*;
struct esp_timer_create_args_t {void(*callback)(void*)=nullptr;void* arg=nullptr;const char* name=nullptr;};
inline Timer* usb_timer=nullptr;inline Timer* trace_timer=nullptr;
int esp_timer_create(esp_timer_create_args_t* t,Timer** out){
 auto callback=t->callback;auto arg=t->arg;*out=new Timer{[=]{callback(arg);},0};
 if(std::string_view(t->name)=="flower_usb")usb_timer=*out;
 if(std::string_view(t->name)=="flower_trace")trace_timer=*out;
 return 0;
}
int esp_timer_stop(Timer* t){if(t)t->delay=0;return 0;}
int esp_timer_start_once(Timer* t,int64_t delay){assert(!t->delay);t->delay=delay;return 0;}
void fire(Timer* t){assert(t->delay);t->delay=0;t->callback();}
struct esp_pm_config_t {int max_freq_mhz=0,min_freq_mhz=0;bool light_sleep_enable=false;};
inline bool sleeping=false;
int esp_pm_configure(esp_pm_config_t* c){sleeping=c->light_sleep_enable;return 0;}
using esp_err_t=int;
constexpr esp_err_t ESP_OK=0;
struct esp_pm_sleep_cbs_register_config_t {
 esp_err_t(*exit_cb)(int64_t,void*)=nullptr;void* exit_cb_user_arg=nullptr;
};
inline esp_pm_sleep_cbs_register_config_t pm_callbacks;
int esp_pm_light_sleep_register_cbs(esp_pm_sleep_cbs_register_config_t* c){pm_callbacks=*c;return 0;}
using esp_pm_lock_handle_t=int*;
constexpr int ESP_PM_NO_LIGHT_SLEEP=0;
inline int no_sleep_count=0;
int esp_pm_lock_create(int,int,const char*,int** out){*out=&no_sleep_count;return 0;}
int esp_pm_lock_acquire(int* lock){++*lock;return 0;}
int esp_pm_lock_release(int* lock){--*lock;return 0;}
struct usb_serial_jtag_pull_override_vals_t {};
inline bool usb_disconnected=false;
void usb_serial_jtag_ll_phy_enable_pull_override(usb_serial_jtag_pull_override_vals_t*){usb_disconnected=true;}
void usb_serial_jtag_ll_phy_disable_pull_override(){usb_disconnected=false;}
enum class PowerSaveLevel {LOW_POWER,PERFORMANCE};
enum class NetworkEvent {Connected,Disconnected,WifiConfigModeEnter,Scanning};
using NetworkEventCallback=std::function<void(NetworkEvent,const std::string&)>;
struct Led {virtual ~Led()=default;};
struct GpioLed:Led {GpioLed(int,int){} void TurnOff(){}};
struct AudioCodec {virtual ~AudioCodec()=default;};
struct NoAudioCodecSimplex:AudioCodec {int output_volume_=0;
 template<class... T>NoAudioCodecSimplex(T...){} virtual int Read(int16_t*,int n){return n;}};
struct Button {inline static std::function<void()> click[3],double_click[3],long_press[3];int pin;
 Button(int p,bool,int,int,bool power):pin(p){assert(power);}
 void OnClick(std::function<void()> f){click[pin]=f;}
 void OnDoubleClick(std::function<void()> f){double_click[pin]=f;}
 void OnLongPress(std::function<void()> f){long_press[pin]=f;}};
struct WifiManager {bool connected=true,config=false;int starts=0,stops=0;
 static WifiManager& GetInstance(){static WifiManager m;return m;}
 bool IsConnected(){return connected;}
 void StartStation(){++starts;}
 void StopStation(){++stops;connected=false;}};
enum DeviceState {kDeviceStateStarting,kDeviceStateIdle,kDeviceStateConnecting,kDeviceStateListening,kDeviceStateSpeaking,kDeviceStateNotifying};
struct AudioService {bool idle=true; bool IsPlaybackIdle(){return idle;}};
struct Application {DeviceState state=kDeviceStateIdle;bool buffered=false,opening=false;int toggles=0,captures=0;
 AudioService audio;std::vector<std::function<void()>> tasks;
 static Application& GetInstance(){static Application a;return a;}
 void Schedule(std::function<void()> f){tasks.push_back(f);}
 void Drain(){auto t=std::move(tasks);tasks.clear();for(auto& f:t)f();}
 DeviceState GetDeviceState(){return state;}
 void ToggleChatState(){++toggles;state=kDeviceStateListening;}
 bool BeginBufferedConversation(){if(!audio.idle)return false;buffered=true;++captures;state=kDeviceStateConnecting;return true;}
 void ConnectBufferedConversation(){buffered=false;state=kDeviceStateListening;}
 void CancelBufferedConversation(){buffered=false;state=kDeviceStateIdle;}
 bool HasBufferedConversation(){return buffered;}
 bool IsConnectionOpening(){return opening;}
 AudioService& GetAudioService(){return audio;}
 bool CanEnterSleepMode(){return state==kDeviceStateIdle && audio.idle;}
 bool PrepareForNetworkSleep(){return CanEnterSleepMode();}
 void PlaySound(std::string_view){} void Reboot(){}
};
namespace Lang::Sounds {constexpr auto OGG_EXCLAMATION="error";}
namespace flower {
struct GreetingTimeSettings {GreetingSchedule GetSchedule(){return {};}
 bool AnnouncementsEnabled(){return true;}};
struct FlowerAudioManager {
 bool AutomaticEnabled(){return true;} bool GreetingEnabled(bool){return true;}
 std::string_view StartupSound(){return {};}
 std::string_view WifiConfigSound(){return {};}
 std::string_view SessionSound(bool){return {};}
 void CommitSessionSound(bool){}
 void PlayPhrase(){Application::GetInstance().state=kDeviceStateNotifying;}
};
struct HourlyChime {HourlyChime(GreetingTimeSettings&,FlowerAudioManager&){}
 void Tick(){} void ResetPhraseTimer(){} int64_t NextPhraseUs(){return 0;}};
void InitializeAnnouncementTools(GreetingTimeSettings&){}
}
struct WifiBoard {Timer* connect_timer_=nullptr;virtual ~WifiBoard()=default;
 virtual bool UsesWakeWord()const{return true;}
 virtual PowerSaveLevel LocalPlaybackPowerLevel()const{return PowerSaveLevel::PERFORMANCE;}
 virtual void TraceWakeEvent(const char*){}
 virtual void OnClockTick(){} virtual void OnApplicationEvent(){}
 virtual std::string_view GetStartupSound(){return {};}
 virtual std::string_view GetWifiConfigSound(){return {};}
 virtual float GetLocalPlaybackGain()const{return 1;}
 virtual std::string_view GetSessionSound(bool){return {};}
 virtual void OnSessionSoundStarted(bool){}
 NetworkEventCallback network_callback;
 virtual void SetNetworkEventCallback(NetworkEventCallback cb){network_callback=std::move(cb);}
 virtual AudioCodec* GetAudioCodec(){return nullptr;} virtual Led* GetLed(){return nullptr;}
 void SetPowerSaveLevel(PowerSaveLevel){} void EnterWifiConfigMode(){WifiManager::GetInstance().config=true;}
 bool IsInWifiConfigMode(){return WifiManager::GetInstance().config;}
};
#define DECLARE_BOARD(T) WifiBoard* make_board(){return new T;}
'''
        test = r'''
int main(){
 auto* b=make_board();auto& a=Application::GetInstance();auto& w=WifiManager::GetInstance();
 assert(!b->UsesWakeWord());assert(b->LocalPlaybackPowerLevel()==PowerSaveLevel::LOW_POWER);
 b->OnApplicationEvent();monotonic=299000000;b->OnApplicationEvent();assert(!sleeping && w.connected);
 monotonic=300000000;b->OnApplicationEvent();assert(sleeping && !w.connected && w.stops==1);
 Button::double_click[1]();a.Drain();b->OnApplicationEvent();
 assert(!sleeping && a.state==kDeviceStateNotifying && a.captures==0 && w.starts==0);
 assert(!usb_disconnected && usb_timer->delay==0); // Policy armed but no actual sleep yet.
 a.state=kDeviceStateIdle;b->OnApplicationEvent();assert(sleeping);
 assert(pm_callbacks.exit_cb(1000000,pm_callbacks.exit_cb_user_arg)==ESP_OK);
 Button::click[1]();a.Drain();b->OnApplicationEvent();
 assert(!sleeping && a.buffered && w.starts==1 && a.captures==1);
 assert(usb_disconnected && usb_timer->delay==100000 && no_sleep_count==1);
 fire(usb_timer);a.Drain();
 assert(!usb_disconnected && no_sleep_count==0 && trace_timer->delay==800000);
 w.connected=true;b->OnApplicationEvent();assert(a.state==kDeviceStateListening);
 monotonic+=999000000;b->OnApplicationEvent();assert(!sleeping && w.stops==1);
 a.state=kDeviceStateIdle;b->OnApplicationEvent();
 monotonic+=299000000;b->OnApplicationEvent();assert(w.connected);
 a.state=kDeviceStateNotifying;monotonic+=2000000;b->OnApplicationEvent();assert(w.connected);
 a.state=kDeviceStateIdle;b->OnApplicationEvent();assert(sleeping && w.stops==2);
 // A second wake is allowed even if the previous trace is still pending.
 assert(pm_callbacks.exit_cb(1000000,pm_callbacks.exit_cb_user_arg)==ESP_OK);
 Button::click[1]();a.Drain();b->OnApplicationEvent();assert(a.buffered && usb_disconnected);
 fire(usb_timer);a.Drain();assert(!usb_disconnected && trace_timer->delay==800000);
 fire(trace_timer);a.Drain();
 monotonic+=8000000;b->OnApplicationEvent();assert(!a.buffered && sleeping);
 Button::click[1]();a.Drain();b->OnApplicationEvent();assert(a.buffered);
 Button::click[1]();a.Drain();b->OnApplicationEvent();assert(!a.buffered && sleeping);
 // A queued single click waiting for playback must not run again after cancellation.
 a.audio.idle=false;Button::click[1]();a.Drain();assert(!a.buffered);
 a.audio.idle=true;b->OnApplicationEvent();assert(a.buffered);
 Button::click[1]();a.Drain();b->OnApplicationEvent();assert(!a.buffered);
 b->OnApplicationEvent();assert(!a.buffered && sleeping);
 // Transient association events cannot abort a live server handshake.
 int forwarded=0;b->SetNetworkEventCallback([&](NetworkEvent,const std::string&){++forwarded;});
 a.opening=true;a.state=kDeviceStateConnecting;
 b->network_callback(NetworkEvent::Disconnected,"");a.Drain();assert(forwarded==0);
 b->network_callback(NetworkEvent::Connected,"");a.Drain();assert(forwarded==1);
 a.opening=false;a.state=kDeviceStateIdle;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fake.h").write_text(fake)
            for name in ("announcement_mcp_tools.h", "application.h", "button.h", "codecs/no_audio_codec.h",
                         "config.h", "hourly_chime.h", "led/gpio_led.h", "wifi_board.h",
                         "assets/lang_config.h", "wifi_manager.h", "esp_pm.h", "esp_log.h", "sdkconfig.h", "hal/usb_serial_jtag_ll.h"):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('#include "fake.h"\n')
            (root / "test.cc").write_text('#include "fake.h"\n' + (BOARD / "flower_s3.cc").read_text() + test)
            compiler = shlex.split(os.environ.get("CXX", "c++"))
            subprocess.run(compiler + ["-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{root}",
                                       f"-I{BOARD}", str(root / "test.cc"), "-o", str(root / "test")], check=True)
            subprocess.run([str(root / "test")], check=True)
