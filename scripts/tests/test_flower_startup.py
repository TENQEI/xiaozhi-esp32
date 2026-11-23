"""Run real activation and local-playback gates for the board's one-time ready clip."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from test_startup_wake_word_hint import definition

ROOT = Path(__file__).resolve().parents[2]


class FlowerStartupSoundTest(unittest.TestCase):
    def test_ready_sound_once_recovery_busy_interrupt_and_native_fallback(self):
        source = (ROOT / 'main/application.cc').read_text()
        methods = '\n'.join(definition(source, signature) for signature in (
            'void Application::HandleActivationDoneEvent()',
            'void Application::PlayReadySound(',
            'bool Application::PlayLocalAudio(',
        ))
        driver = r'''
#include <cassert>
#include <cstring>
#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
#define ESP_LOGI(...) ((void)0)
namespace SystemInfo { inline void PrintHeapStats() {} }
namespace Lang {
namespace Strings { constexpr const char* VERSION="Version: "; }
namespace Sounds { constexpr std::string_view OGG_SUCCESS="OggSnative"; }
}
enum State { kDeviceStateIdle, kDeviceStateConnecting, kDeviceStateNotifying };
enum class PowerSaveLevel { LOW_POWER };
struct Display {
 int notifications=0;
 void ShowNotification(const char*) {++notifications;}
 void SetChatMessage(const char*,const char*) {}
};
struct Board {
 std::string_view startup="OggSready";
 Display display;
 static Board& GetInstance() {static Board board;return board;}
 Display* GetDisplay() {return &display;}
 void SetPowerSaveLevel(PowerSaveLevel) {}
 std::string_view GetStartupSound() {return startup;}
};
struct Ota {
 bool HasServerTime() {return true;}
 std::string GetCurrentVersion() {return "test";}
};
struct AudioService {
 bool idle=true;
 int native_calls=0;
 bool IsPlaybackIdle() {return idle;}
 void PlaySound(std::string_view sound) {assert(sound==Lang::Sounds::OGG_SUCCESS);++native_calls;}
};
struct NotifyPlayer {
 static constexpr size_t kMaxLocalAudioBytes=128*1024;
 bool busy=false;
 bool IsBusy() {return busy;}
};
struct Application {
 State state=kDeviceStateIdle;
 bool has_server_time_=false, startup_completed_=false, pending_startup_wake_word_hint_=false;
 std::string last_error_message_;
 AudioService audio_service_;
 NotifyPlayer notify_player_;
 std::unique_ptr<Ota> ota_=std::make_unique<Ota>();
 std::vector<std::function<void()>> tasks;
 int local_calls=0;
 State GetDeviceState() {return state;}
 void SetDeviceState(State next) {state=next;}
 void Schedule(std::function<void()> task) {tasks.push_back(std::move(task));}
 bool StartNotification(std::string, std::vector<int>,std::string sound) {
  assert(sound=="OggSready");++local_calls;state=kDeviceStateNotifying;return true;
 }
 void HandleActivationDoneEvent();
 void PlayReadySound(bool);
 bool PlayLocalAudio(std::string_view);
 void Activate() {ota_=std::make_unique<Ota>();HandleActivationDoneEvent();}
 void Drain() {auto pending=std::move(tasks);tasks.clear();for(auto& task:pending)task();}
};
'''
        assertions = r'''
int main() {
 auto& board=Board::GetInstance();
 Application ready;
 ready.Activate();
 assert(ready.local_calls==0 && ready.startup_completed_ && ready.pending_startup_wake_word_hint_);
 ready.Drain();
 assert(ready.local_calls==1 && ready.state==kDeviceStateNotifying && ready.audio_service_.native_calls==0);
 ready.state=kDeviceStateIdle;
 ready.Activate();ready.Drain();
 assert(ready.local_calls==1 && ready.audio_service_.native_calls==0); // reconnect never repeats
 Application failed;
 failed.last_error_message_="network failed";failed.Activate();failed.Drain();
 assert(!failed.startup_completed_ && !failed.pending_startup_wake_word_hint_ && failed.local_calls==0);
 failed.last_error_message_.clear();failed.Activate();failed.Drain();
 assert(failed.startup_completed_ && failed.local_calls==1); // first successful recovery
 Application error_race;
 error_race.Activate();error_race.last_error_message_="late error";error_race.Drain();
 assert(error_race.local_calls==0 && error_race.audio_service_.native_calls==0);
 Application interrupted;
 interrupted.Activate();interrupted.state=kDeviceStateConnecting;interrupted.Drain();
 assert(interrupted.local_calls==0 && interrupted.state==kDeviceStateConnecting);
 Application busy;
 busy.Activate();busy.notify_player_.busy=true;busy.Drain();assert(busy.local_calls==0);
 busy.notify_player_.busy=false;busy.Activate();busy.Drain();assert(busy.local_calls==0);
 Application playback;
 playback.audio_service_.idle=false;playback.Activate();playback.Drain();assert(playback.local_calls==0);
 board.startup="";
 Application native;
 native.Activate();native.Drain();native.Activate();native.Drain();
 assert(native.local_calls==0 && native.audio_service_.native_calls==2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            test = path / 'startup.cc'
            test.write_text(driver + methods + assertions)
            compiler = shlex.split(os.environ.get('CXX', 'c++'))
            subprocess.run(compiler + ['-std=c++20', '-Wall', '-Wextra', '-Werror',
                                      str(test), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
