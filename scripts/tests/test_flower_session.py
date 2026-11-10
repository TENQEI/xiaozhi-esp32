"""Compile the real asynchronous Application session handlers against host fakes."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_startup_wake_word_hint import definition

ROOT = Path(__file__).resolve().parents[2]


class FlowerSessionTest(unittest.TestCase):
    def test_start_finish_failure_cancel_disconnect_and_duplicate_close(self):
        source = (ROOT / 'main/application.cc').read_text()
        methods = '\n'.join(definition(source, signature) for signature in (
            'bool Application::PrepareForNetworkSleep()',
            'bool Application::BeginBufferedConversation()',
            'void Application::ConnectBufferedConversation()',
            'void Application::CancelBufferedConversation()',
            'void Application::FinishBufferedConnection(',
            'void Application::StartListeningAudio()',
            'void Application::ContinueWakeWordInvoke(',
            'void Application::ContinueOpenAudioChannel(',
            'void Application::BeginConversation(',
            'void Application::CancelSessionSound()',
            'void Application::CancelConversation()',
            'void Application::HandleAudioChannelClosed()',
        ))
        driver = r'''
#define ESP_LOGI(...) ((void)0)
#include <cassert>
#include <cstring>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
#include "main/audio/session_lifecycle.h"
constexpr int pdPASS=1;
inline std::vector<std::function<void()>> workers;
int xTaskCreate(void(*f)(void*),const char*,int,void* arg,int,void*){workers.push_back([=]{f(arg);});return pdPASS;}
void vTaskDelete(void*){}
void run_workers(){auto work=std::move(workers);workers.clear();for(auto& f:work)f();}
enum DeviceState {kDeviceStateIdle, kDeviceStateConnecting, kDeviceStateListening,
 kDeviceStateSpeaking, kDeviceStateNotifying, kDeviceStateUpgrading};
enum ListeningMode {kListeningModeAutoStop, kListeningModeManualStop};
struct NotifyPlayer {
 static constexpr size_t kMaxLocalAudioBytes = 128 * 1024;
 bool busy=false, fail=false; unsigned id=0, starts=0, stops=0;
 std::function<void(uint32_t,bool)> callback;
 bool IsBusy() {return busy;}
 bool StartLocal(std::string sound, uint32_t number, std::function<void(uint32_t,bool)> done) {
  assert(sound.starts_with("OggS"));
  if(fail) return false;
  busy=true; id=number; callback=std::move(done); ++starts; return true;
 }
 void Stop() {busy=false; ++stops;}
 void Finish(bool success=true) {busy=false; callback(id,success);}
};
inline bool listening_command_sent=false;
namespace Lang::Sounds { constexpr auto OGG_EXCLAMATION="error", OGG_POPUP="popup"; }
struct Audio {int packets=1;
 bool sleep_ready=false;bool PrepareForSleep(){return sleep_ready;}
 bool buffering=false, flushed=false, overflow=false;
 bool BeginMicrophoneBuffer(){buffering=true;voice=true;return true;}
 bool MicrophoneBufferOverflowed(){return overflow;}
 void EndMicrophoneBuffer(bool send){if(send)assert(listening_command_sent);buffering=false;flushed=send;}
 void PlaySound(std::string_view){}

 std::unique_ptr<int> PopWakeWordPacket(){return packets-- > 0 ? std::make_unique<int>(1) : nullptr;}
 bool idle=true, voice=true, wake=true; int resets=0;
 bool IsPlaybackIdle(){return idle;}
 void EnableVoiceProcessing(bool on){voice=on;}
 void EnableWakeWordDetection(bool on){wake=on;}
 void ResetDecoder(){++resets;}
};
struct Protocol {bool open=true, connect=true; int sent=0, wakes=0, suspends=0;
 void SuspendNetwork(){++suspends;}
 void SendStartListening(ListeningMode){listening_command_sent=true;}
 void CloseAudioChannel(){open=false;}
 bool IsAudioChannelOpened(){return open;}
 bool OpenAudioChannel(){return open=connect;}
 void SendAudio(std::unique_ptr<int>){++sent;}
 void SendWakeWordDetected(const std::string&){++wakes;}
};
enum class PowerSaveLevel {PERFORMANCE};
struct Display {void SetChatMessage(const char*,const char*){}};
struct Board {
 void SetPowerSaveLevel(PowerSaveLevel){}
 std::string start="OggSstart", end="OggSend"; int started=0, ended=0; Display display;
 static Board& GetInstance(){static Board b; return b;}
 std::string_view GetSessionSound(bool starting){return starting?start:end;}
 void OnSessionSoundStarted(bool starting){starting?++started:++ended;}
 Display* GetDisplay(){return &display;}
};
struct Application {
 bool buffered_open_in_progress_=false;
 bool buffered_conversation_=false;
 void FinishBufferedConnection(std::shared_ptr<Protocol>, bool);
 ListeningMode listening_mode_=kListeningModeAutoStop;
 bool PrepareForNetworkSleep();
 bool CanEnterSleepMode(){return !buffered_open_in_progress_ && state==kDeviceStateIdle && !protocol_->open && audio_service_.idle;}
 bool BeginBufferedConversation();
 void ConnectBufferedConversation();
 void CancelBufferedConversation();
 void StartListeningAudio();
 void ConfigureWakeWordForListening(){}
 void DismissAlert(){}
 void PlaySound(std::string_view){}
 void StopNotification(){state=kDeviceStateIdle;audio_service_.idle=true;}
 SessionLifecycle session_; bool session_sound_pending_=false, suppress_next_popup_=false;
 std::function<void()> session_sound_continuation_;
 uint32_t notification_playback_id_=0;
 NotifyPlayer notify_player_; Audio audio_service_;
 std::shared_ptr<Protocol> protocol_=std::make_shared<Protocol>();
 DeviceState state=kDeviceStateConnecting; std::string last_error_message_;
 std::vector<std::function<void()>> scheduled;
 bool play_popup_on_listening_=false; int listening=0;
 ListeningMode GetDefaultListeningMode(){return kListeningModeAutoStop;}
 void SetListeningMode(ListeningMode){state=kDeviceStateListening;++listening;}
 void ContinueWakeWordInvoke(const std::string&);
 void ContinueOpenAudioChannel(ListeningMode);
 int local_plays=0;
 DeviceState GetDeviceState(){return state;}
 bool SetDeviceState(DeviceState value){state=value;return true;}
 void Schedule(std::function<void()> f){scheduled.push_back(std::move(f));}
 void Drain(){auto work=std::move(scheduled);scheduled.clear();for(auto& f:work)f();}
 bool PlayLocalAudio(std::string_view sound){if(sound.empty())return false;
  ++local_plays;state=kDeviceStateNotifying;return true;}
 void BeginConversation(ListeningMode,std::function<void()>);
 void CancelSessionSound(); void CancelConversation(); void HandleAudioChannelClosed();
};
'''
        tests = r'''
int main(){
 Application sleep;sleep.state=kDeviceStateIdle;sleep.protocol_->open=false;
 assert(!sleep.PrepareForNetworkSleep() && sleep.protocol_->suspends==0);
 sleep.audio_service_.sleep_ready=true;
 assert(sleep.PrepareForNetworkSleep() && sleep.protocol_->suspends==1);
 sleep.buffered_open_in_progress_=true;
 assert(!sleep.PrepareForNetworkSleep() && sleep.protocol_->suspends==1);
 Application buffered;buffered.state=kDeviceStateIdle;
 assert(buffered.BeginBufferedConversation());
 assert(buffered.state==kDeviceStateConnecting && buffered.audio_service_.buffering);
 buffered.ConnectBufferedConversation();
 assert(buffered.state==kDeviceStateConnecting);run_workers();buffered.Drain();
 assert(buffered.state==kDeviceStateListening && !buffered.audio_service_.flushed);
 buffered.StartListeningAudio();
 assert(buffered.audio_service_.flushed && !buffered.buffered_conversation_);
 Application cancelled_buffer;cancelled_buffer.state=kDeviceStateIdle;
 assert(cancelled_buffer.BeginBufferedConversation());cancelled_buffer.CancelBufferedConversation();
 assert(!cancelled_buffer.audio_service_.voice && !cancelled_buffer.audio_service_.flushed);
 assert(cancelled_buffer.state==kDeviceStateIdle);
 cancelled_buffer.ConnectBufferedConversation();assert(cancelled_buffer.listening==0);
 Application full;full.state=kDeviceStateIdle;assert(full.BeginBufferedConversation());
 full.audio_service_.overflow=true;full.ConnectBufferedConversation();run_workers();full.Drain();
 assert(full.state==kDeviceStateIdle && !full.protocol_->open && !full.audio_service_.flushed);
 Application failed_buffer;failed_buffer.state=kDeviceStateIdle;
 assert(failed_buffer.BeginBufferedConversation());failed_buffer.protocol_->open=false;
 failed_buffer.protocol_->connect=false;failed_buffer.ConnectBufferedConversation();run_workers();failed_buffer.Drain();
 assert(failed_buffer.state==kDeviceStateIdle && !failed_buffer.audio_service_.voice);
 Application canceled_handshake;canceled_handshake.state=kDeviceStateIdle;
 assert(canceled_handshake.BeginBufferedConversation());canceled_handshake.ConnectBufferedConversation();
 canceled_handshake.CancelBufferedConversation();run_workers();canceled_handshake.Drain();
 assert(canceled_handshake.state==kDeviceStateIdle && !canceled_handshake.audio_service_.flushed);
 assert(!canceled_handshake.protocol_->open && !canceled_handshake.buffered_open_in_progress_);
 // The connection can disappear after OpenAudioChannel returns, before completion.
 Application lost_handshake;lost_handshake.state=kDeviceStateIdle;
 assert(lost_handshake.BeginBufferedConversation());lost_handshake.ConnectBufferedConversation();
 run_workers();lost_handshake.protocol_->open=false;lost_handshake.Drain();
 assert(lost_handshake.state==kDeviceStateIdle && !lost_handshake.audio_service_.flushed);
 assert(!lost_handshake.buffered_open_in_progress_);
 // A final encoded frame can fill the buffer after handshake completion.
 Application late_overflow;late_overflow.state=kDeviceStateIdle;
 assert(late_overflow.BeginBufferedConversation());late_overflow.ConnectBufferedConversation();
 run_workers();late_overflow.Drain();late_overflow.audio_service_.overflow=true;
 late_overflow.StartListeningAudio();
 assert(late_overflow.state==kDeviceStateIdle && !late_overflow.audio_service_.flushed);
 assert(!late_overflow.protocol_->open);
 // No new capture is admitted while a cancelled worker still owns the channel.
 assert(canceled_handshake.BeginBufferedConversation());canceled_handshake.ConnectBufferedConversation();
 canceled_handshake.CancelBufferedConversation();assert(!canceled_handshake.BeginBufferedConversation());
 run_workers();canceled_handshake.Drain();assert(canceled_handshake.BeginBufferedConversation());
 canceled_handshake.CancelBufferedConversation();
 auto& board=Board::GetInstance(); int ready=0;
 Application app;
 app.BeginConversation(kListeningModeAutoStop,[&]{++ready;app.state=kDeviceStateListening;});
 assert(ready==0 && app.session_sound_pending_ && !app.audio_service_.voice && !app.audio_service_.wake);
 app.notify_player_.Finish();assert(ready==0);app.Drain();
 assert(ready==1 && app.state==kDeviceStateListening && app.suppress_next_popup_);
 app.BeginConversation(kListeningModeAutoStop,[&]{++ready;});
 assert(ready==2 && app.notify_player_.starts==1); // no cue for another turn
 app.session_.RequestEnd();app.HandleAudioChannelClosed();
 assert(app.local_plays==1 && board.ended==1 && app.state==kDeviceStateNotifying);
 app.HandleAudioChannelClosed();assert(app.local_plays==1 && app.state==kDeviceStateNotifying);
 Application lost;
 lost.BeginConversation(kListeningModeAutoStop,[&]{++ready;});
 lost.protocol_->open=false;lost.HandleAudioChannelClosed();
 lost.notify_player_.Finish();lost.Drain();assert(ready==2 && !lost.local_plays);
 Application canceled;
 canceled.BeginConversation(kListeningModeAutoStop,[&]{++ready;});
 canceled.notify_player_.Finish(); // completion is queued, then user cancels
 canceled.CancelConversation();canceled.state=kDeviceStateIdle;canceled.Drain();
 assert(ready==2 && !canceled.session_sound_pending_ && canceled.notify_player_.stops==1);
 canceled.HandleAudioChannelClosed();assert(!canceled.local_plays);
 Application manual;
 manual.BeginConversation(kListeningModeManualStop,[&]{++ready;});
 assert(ready==3 && !manual.notify_player_.starts);
 manual.session_.RequestEnd();manual.HandleAudioChannelClosed();assert(!manual.local_plays);
 Application failed;failed.notify_player_.fail=true;
 failed.BeginConversation(kListeningModeAutoStop,[&]{++ready;});
 assert(ready==4 && !failed.session_sound_pending_ && !failed.suppress_next_popup_);
 Application decoded;
 decoded.BeginConversation(kListeningModeAutoStop,[&]{++ready;});
 decoded.notify_player_.Finish(false);decoded.Drain();assert(ready==5 && !decoded.suppress_next_popup_);
 Application error;
 error.BeginConversation(kListeningModeAutoStop,[&]{++ready;});
 error.session_.RequestEnd();error.CancelConversation();error.HandleAudioChannelClosed();
 assert(!error.local_plays);
 Application maintenance;maintenance.session_.Begin();maintenance.session_.RequestEnd();
 maintenance.state=kDeviceStateUpgrading;maintenance.HandleAudioChannelClosed();
 assert(!maintenance.local_plays && maintenance.state==kDeviceStateUpgrading);
 Application wake;wake.ContinueWakeWordInvoke("hello");
 assert(!wake.listening && !wake.protocol_->sent && !wake.protocol_->wakes);
 wake.notify_player_.Finish();wake.Drain();assert(wake.listening==1);
 assert(wake.protocol_->sent==CONFIG_SEND_WAKE_WORD_DATA && wake.protocol_->wakes==CONFIG_SEND_WAKE_WORD_DATA);
 Application no_connection;no_connection.protocol_->open=false;no_connection.protocol_->connect=false;
 no_connection.ContinueWakeWordInvoke("hello");
 assert(!no_connection.listening && !no_connection.notify_player_.starts && no_connection.state==kDeviceStateIdle);
 Application button;button.ContinueOpenAudioChannel(kListeningModeAutoStop);
 assert(!button.listening);button.notify_player_.Finish();button.Drain();assert(button.listening==1);
 board.start.clear();Application native;
 native.BeginConversation(kListeningModeAutoStop,[&]{++ready;});assert(ready==6 && !native.notify_player_.starts);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cc').write_text(driver + methods + tests)
            for send_wake_data in (0, 1):
                built = subprocess.run(['c++', '-std=c++23', f'-DCONFIG_SEND_WAKE_WORD_DATA={send_wake_data}', '-I', str(ROOT), str(path / 'test.cc'), '-o', str(path / 'test')], capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stderr)
                ran = subprocess.run([str(path / 'test')], capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stderr)
