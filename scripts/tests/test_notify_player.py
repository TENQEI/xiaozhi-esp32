import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class NotifyPlayerTest(unittest.TestCase):
    def test_local_and_http_completion_cancellation_failure_and_owned_bytes(self):
        headers = {
            "freertos/FreeRTOS.h": """
                #pragma once
                #include <cstdint>
                using BaseType_t = int;
                using UBaseType_t = unsigned;
                constexpr int pdPASS = 1;
            """,
            "freertos/task.h": """
                #pragma once
                #include "FreeRTOS.h"
                using TaskHandle_t = void*;
                inline void (*pending_task)(void*) = nullptr;
                inline void* pending_arg = nullptr;
                inline bool task_creation_fails = false;
                inline BaseType_t xTaskCreate(void (*fn)(void*), const char*, uint32_t,
                                               void* arg, UBaseType_t, TaskHandle_t* handle) {
                    if (task_creation_fails) return 0;
                    pending_task = fn; pending_arg = arg; *handle = arg; return pdPASS;
                }
                inline void vTaskDelete(void*) {}
                inline void RunWorker() { auto fn = pending_task; pending_task = nullptr; fn(pending_arg); }
            """,
            "esp_log.h": """
                #pragma once
                #define ESP_LOGE(...) ((void)0)
                #define ESP_LOGW(...) ((void)0)
                #define ESP_LOGD(...) ((void)0)
                #define ESP_LOGI(...) ((void)0)
            """,
            "audio_service.h": """
                #pragma once
                #include <cstdint>
                #include <functional>
                #include <memory>
                #include <vector>
                struct AudioStreamPacket {
                    int sample_rate = 0, frame_duration = 0;
                    uint32_t playback_id = 0, media_position_ms = 0;
                    std::vector<uint8_t> payload;
                    float playback_gain = 1.0f;
                };
                class AudioService {
                public:
                    std::vector<AudioStreamPacket> packets;
                    std::function<bool(const AudioStreamPacket&)> on_push;
                    bool PushPacketToDecodeQueue(std::unique_ptr<AudioStreamPacket> p, bool) {
                        if (on_push && !on_push(*p)) return false;
                        packets.push_back(*p); return true;
                    }
                };
            """,
            "http.h": """
                #pragma once
                #include <algorithm>
                #include <cstring>
                #include <expected>
                #include <string>
                struct Error { std::string ToString() const { return "test error"; } };
                inline std::string http_audio;
                inline int http_status = 200, http_creations = 0;
                inline bool http_read_error = false;
                class Http {
                    size_t offset_ = 0;
                public:
                    void SetTimeout(int) {}
                    void SetHeader(const char*, const char*) {}
                    std::expected<void, Error> Open(const char*, const std::string&) { return {}; }
                    std::expected<int, Error> GetStatusCode() { return http_status; }
                    std::expected<size_t, Error> Read(char* data, size_t count) {
                        if (http_read_error) return std::unexpected(Error{});
                        count = std::min(count, http_audio.size() - offset_);
                        std::memcpy(data, http_audio.data() + offset_, count); offset_ += count;
                        return count;
                    }
                    void Close() {}
                };
            """,
            "board.h": """
                #pragma once
                #include <memory>
                #include "http.h"
                struct Network {
                    std::unique_ptr<Http> CreateHttp(int) { ++http_creations; return std::make_unique<Http>(); }
                };
                class Board {
                    Network network_;
                public:
                    static Board& GetInstance() { static Board b; return b; }
                    Network* GetNetwork() { return &network_; }
                    float GetLocalPlaybackGain() const { return 1.5848932f; }
                };
            """,
        }
        driver = r'''
            #include "notify_player.h"
            #include "http.h"
            #include <cassert>
            #include <fstream>
            #include <iterator>
            int main(int argc, char** argv) {
                assert(argc == 2);
                std::ifstream input(argv[1], std::ios::binary);
                const std::string sound{std::istreambuf_iterator<char>(input), {}};
                assert(sound.size() > 4);
                AudioService audio;
                NotifyPlayer player(audio);
                int calls = 0; bool result = false; uint32_t completed = 0;
                auto done = [&](uint32_t id, bool ok) { ++calls; result = ok; completed = id; };
                assert(!player.StartLocal("bad", 1, done));
                assert(!player.StartLocal(sound, 0, done));
                assert(!player.StartLocal("OggS" + std::string(128 * 1024, 'x'), 1, done));
                auto owned = sound;
                assert(player.StartLocal(owned, 7, done));
                owned.assign(owned.size(), 'x');
                assert(player.IsActive(7) && player.IsBusy());
                assert(!player.StartLocal(sound, 8, done));
                RunWorker();
                assert(!audio.packets.empty() && calls == 0 && http_creations == 0);
                for (const auto& p : audio.packets) {
                    assert(p.playback_id == 7 && p.playback_gain == 1.5848932f);
                }
                player.OnPlaybackDrained();
                assert(calls == 1 && result && completed == 7 && !player.IsBusy());
                player.OnPlaybackDrained(); assert(calls == 1);

                audio.packets.clear();
                audio.on_push = [&](const AudioStreamPacket&) { player.Stop(); return false; };
                assert(player.StartLocal(sound, 9, done)); RunWorker();
                assert(!player.IsBusy() && calls == 1 && audio.packets.empty());
                audio.on_push = {};
                assert(player.StartLocal(sound.substr(0, sound.size() - 1), 10, done));
                RunWorker(); assert(calls == 2 && !result && !player.IsBusy());
                player.Stop();

                task_creation_fails = true;
                assert(!player.StartLocal(sound, 11, done)); assert(!player.IsBusy());
                task_creation_fails = false;
                audio.on_push = [&](const AudioStreamPacket&) { player.OnPlaybackDrained(); return true; };
                assert(player.StartLocal(sound, 12, done)); RunWorker();
                assert(calls == 3 && result && completed == 12 && !player.IsBusy());

                // Preserve the existing HTTP notification and subtitle path.
                http_audio = sound;
                std::string subtitle;
                audio.on_push = [&](const AudioStreamPacket& p) {
                    assert(p.playback_gain == 1.0f);
                    player.OnPlaybackProgress(p.playback_id, p.media_position_ms);
                    return true;
                };
                assert(!player.Start("file:///test", {}, 13, {}, done));
                assert(player.Start("https://test/audio.ogg", {{0, "hello"}}, 13,
                                    [&](uint32_t, const std::string& s) { subtitle = s; }, done));
                RunWorker(); assert(subtitle == "hello" && http_creations == 1 && calls == 3);
                player.OnPlaybackDrained(); assert(calls == 4 && result && completed == 13);
                http_status = 404;
                assert(player.Start("http://test/missing.ogg", {}, 14, {}, done));
                RunWorker(); assert(calls == 5 && !result && !player.IsBusy());
                http_status = 200; http_read_error = true;
                assert(player.Start("http://test/error.ogg", {}, 15, {}, done));
                RunWorker(); assert(calls == 6 && !result && !player.IsBusy());
            }
        '''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in headers.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            source = root / "driver.cc"
            source.write_text(driver)
            exe = root / "test"
            command = shlex.split(os.environ.get("CXX", "c++")) + [
                "-std=c++23", f"-I{root}", f"-I{ROOT / 'main/notify'}",
                f"-I{ROOT / 'main/audio/demuxer'}", str(source),
                str(ROOT / "main/notify/notify_player.cc"),
                str(ROOT / "main/audio/demuxer/ogg_demuxer.cc"), "-o", str(exe)]
            subprocess.run(command, check=True)
            subprocess.run([str(exe), str(ROOT / "main/assets/locales/zh-CN/1.ogg")], check=True)


if __name__ == "__main__":
    unittest.main()
