"""Run the actual microphone buffer lifecycle and encoded-packet routing."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_startup_wake_word_hint import definition
ROOT = Path(__file__).resolve().parents[2]

class FlowerCaptureTest(unittest.TestCase):
    def test_bounded_capture_cancel_generation_and_ordered_drain(self):
        source = (ROOT / "main/audio/audio_service.cc").read_text()
        methods = "\n".join(definition(source, s) for s in (
            "bool AudioService::BeginMicrophoneBuffer(",
            "bool AudioService::MicrophoneBufferOverflowed()",
            "void AudioService::ReleaseMicrophoneAfterCue()",
            "void AudioService::EndMicrophoneBuffer(",
            "std::unique_ptr<AudioStreamPacket> AudioService::PopPacketFromSendQueue()"))
        start = source.index("if (task.capture_generation != capture_generation_)")
        end = source.index("\n                        }\n                        if (callbacks_.on_send_queue_available)", start)
        route = source[start:end]
        driver = r'''
#include <cassert>
#include <condition_variable>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include "main/audio/fixed_queue.h"
constexpr int MAX_SEND_PACKETS_IN_QUEUE=2;
constexpr int AUDIO_CODEC_DMA_DESC_NUM=6,AUDIO_CODEC_DMA_FRAME_NUM=240;
struct AudioStreamPacket {int id=0;};
struct AudioService {
 std::mutex audio_queue_mutex_;std::condition_variable audio_queue_cv_;
 FixedQueue<int,2> audio_encode_queue_;
 FixedQueue<std::unique_ptr<AudioStreamPacket>,5> audio_send_queue_;
 bool buffering_microphone_=false,draining_microphone_=false,microphone_buffer_overflowed_=false;
 bool discard_cue_input_=false; std::chrono::steady_clock::time_point cue_tail_until_{};
 struct Codec {int output_sample_rate(){return 24000;}} codec_impl;
 Codec* codec_=&codec_impl;
 std::chrono::steady_clock::time_point last_output_time_{};
 uint32_t capture_generation_=0;bool voice=false,initialize=true;
 struct {std::function<void()> on_send_queue_available;} callbacks_;
 void EnableVoiceProcessing(bool enabled){voice=enabled && initialize;}
 bool IsAudioProcessorRunning(){return voice;}
 void ReleaseMicrophoneAfterCue();
 bool BeginMicrophoneBuffer(bool cue=false);bool MicrophoneBufferOverflowed();
 void EndMicrophoneBuffer(bool);std::unique_ptr<AudioStreamPacket> PopPacketFromSendQueue();
 void Encode(int id,uint32_t generation){
  struct {uint32_t capture_generation;} task{generation};
  auto packet=std::make_unique<AudioStreamPacket>();packet->id=id;
''' + route + r'''
 }
};
'''
        tests=r'''
int main(){
 AudioService audio;int callbacks=0;audio.callbacks_.on_send_queue_available=[&]{++callbacks;};
 assert(audio.BeginMicrophoneBuffer(true));auto generation=audio.capture_generation_;
 assert(audio.discard_cue_input_);
 audio.last_output_time_=std::chrono::steady_clock::now();
 audio.ReleaseMicrophoneAfterCue();
 assert(!audio.discard_cue_input_);
 assert(audio.cue_tail_until_-audio.last_output_time_==std::chrono::milliseconds(60));
 for(int i=1;i<=5;++i)audio.Encode(i,generation);
 assert(!audio.PopPacketFromSendQueue() && !audio.MicrophoneBufferOverflowed());
 audio.Encode(6,generation);assert(audio.MicrophoneBufferOverflowed());
 audio.EnableVoiceProcessing(false);audio.EndMicrophoneBuffer(false);
 audio.Encode(7,generation);assert(!audio.PopPacketFromSendQueue());
 assert(audio.BeginMicrophoneBuffer());generation=audio.capture_generation_;
 audio.Encode(1,generation);audio.Encode(2,generation);audio.Encode(3,generation);
 audio.EndMicrophoneBuffer(true);assert(callbacks==1);
 assert(audio.PopPacketFromSendQueue()->id==1);
 audio.Encode(4,generation);assert(audio.PopPacketFromSendQueue()->id==2);
 assert(audio.PopPacketFromSendQueue()->id==3);assert(audio.PopPacketFromSendQueue()->id==4);
 assert(!audio.draining_microphone_ && !audio.PopPacketFromSendQueue());
 audio.Encode(5,generation);audio.Encode(6,generation);audio.Encode(7,generation);
 assert(audio.PopPacketFromSendQueue()->id==6);assert(audio.PopPacketFromSendQueue()->id==7);
 AudioService failed;failed.initialize=false;assert(!failed.BeginMicrophoneBuffer());
 assert(!failed.buffering_microphone_ && !failed.PopPacketFromSendQueue());
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/"esp_system.h").write_text('#pragma once\n#include <cstdlib>\n[[noreturn]] inline void esp_system_abort(const char*){std::abort();}\n')
            (path/"test.cc").write_text(driver+methods+tests)
            subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror","-I",str(path),"-I",str(ROOT),str(path/"test.cc"),"-o",str(path/"test")],check=True)
            subprocess.run([str(path/"test")],check=True)
