"""Run the real random phrase player with clock, assets and application doubles."""

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/flower-s3"


class FlowerRandomPlayerTest(unittest.TestCase):
    def test_grouped_playback_boundaries_unsynced_legacy_and_invalid_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            compiler = shlex.split(os.environ.get("CXX", "c++"))
            flags = shlex.split(os.environ.get("FLOWER_CJSON_CFLAGS", "-I/usr/include/cjson"))
            libs = shlex.split(os.environ.get("FLOWER_CJSON_LIBS", "-lcjson"))
            probe = subprocess.run(compiler + ["-x", "c++", "-", *flags, *libs,
                                               "-o", str(build / "probe")],
                                   input="#include <cJSON.h>\nint main(){cJSON_Delete(cJSON_CreateObject());}",
                                   text=True, capture_output=True)
            if probe.returncode:
                cjson = ROOT / "managed_components/espressif__cjson/cJSON"
                cc = shlex.split(os.environ.get("CC", "cc"))
                if not (cjson / "cJSON.c").is_file() or not shutil.which(cc[0]):
                    self.skipTest("requires cJSON development files or the ESP-IDF cJSON component")
                flags = [f"-I{cjson}"]
                obj = build / "cjson.o"
                subprocess.run(cc + ["-std=c99", *flags, "-c", str(cjson / "cJSON.c"),
                                     "-o", str(obj)], check=True)
                libs = [str(obj), "-lm"]
            headers = {
                "esp_log.h": "#pragma once\n#define ESP_LOGI(...) ((void)0)\n#define ESP_LOGW(...) ((void)0)\n",
                "esp_random.h": r'''
                    #pragma once
                    #include <cstdint>
                    inline uint32_t random_value = 0;
                    inline uint32_t esp_random() { return random_value; }
                ''',
                "assets.h": r'''
                    #pragma once
                    #include <cassert>
                    #include <string>
                    inline std::string manifest;
                    class Assets {
                    public:
                        static Assets& GetInstance() { static Assets instance; return instance; }
                        bool GetAssetData(const std::string& name, void*& data, size_t& size) {
                            assert(name == "flower_random.json");
                            data = manifest.data(); size = manifest.size(); return !manifest.empty();
                        }
                    };
                ''',
                "application.h": r'''
                    #pragma once
                    #include <string>
                    constexpr int kDeviceStateIdle=0;
                    inline bool playback_idle=true, start_playback=true;
                    inline int state=0, play_calls=0;
                    inline std::string last_asset;
                    class AudioService {
                    public:
                        bool IsPlaybackIdle() { return playback_idle; }
                    };
                    class Application {
                        AudioService audio_;
                    public:
                        static Application& GetInstance() { static Application app; return app; }
                        int GetDeviceState() { return state; }
                        AudioService& GetAudioService() { return audio_; }
                        bool PlayLocalNotification(const std::string& name) {
                            ++play_calls; last_asset=name; return start_playback;
                        }
                    };
                ''',
            }
            for name, data in headers.items():
                (build / name).write_text(data)
            source = build / "driver.cc"
            source.write_text(r'''
                #include "random_phrase.h"
                #include "application.h"
                #include "assets.h"
                #include "esp_random.h"
                #include <cassert>
                #include <cstdio>
                #include <cstdlib>
                inline std::time_t fake_now=0;
                extern "C" std::time_t time(std::time_t* out) noexcept {
                    if(out) { *out=fake_now; }
                    return fake_now;
                }
                using namespace flower;
                int main() {
                    constexpr std::time_t day=1762041600;
                    const std::string grouped=R"({"version":2,"count":16,"common":4,"morning":4,"afternoon":4,"evening":4})";
                    manifest=grouped;
                    RandomPhrasePlayer player;
                    int previous=-1;
                    setenv("TZ","CST-8",1); tzset(); // must not add TZ to OTA's civil clock
                    for (int second : {6*3600-1,6*3600,12*3600-1,12*3600,18*3600-1,18*3600,86399,0}) {
                        fake_now=day+second;
                        int hour=second/3600, start=hour<6 || hour>=18?12:hour<12?4:8;
                        for (int i=0;i<32;++i) {
                            random_value=i; int before=play_calls;
                            player.Play(); assert(play_calls==before+1);
                            int selected=-1; assert(std::sscanf(last_asset.c_str(),"flower_random_%d.ogg",&selected)==1);
                            assert(selected<4 || (selected>=start && selected<start+4));
                            assert(selected!=previous); previous=selected;
                        }
                    }
                    fake_now=0; // uncalibrated: common only
                    for (int i=0;i<16;++i) {
                        random_value=i; player.Play();
                        int selected=-1; std::sscanf(last_asset.c_str(),"flower_random_%d.ogg",&selected);
                        assert(selected>=0 && selected<4);
                    }
                    int before=play_calls;
                    state=1; player.Play(); assert(play_calls==before); state=0;
                    playback_idle=false; player.Play(); assert(play_calls==before); playback_idle=true;
                    // Playback failure must not become the last successful clip.
                    manifest=R"({"version":2,"count":2,"common":2,"morning":0,"afternoon":0,"evening":0})";
                    RandomPhrasePlayer failures;
                    random_value=0; failures.Play(); assert(last_asset=="flower_random_00.ogg");
                    start_playback=false; failures.Play(); assert(last_asset=="flower_random_01.ogg");
                    start_playback=true; failures.Play(); assert(last_asset=="flower_random_01.ogg");
                    for (std::string legacy : {R"({"version":1,"count":2})",
                                              R"({"version":2,"count":2,"common":0,"morning":2,"afternoon":0,"evening":0})"}) {
                        manifest=legacy; fake_now=day+6*3600;
                        RandomPhrasePlayer two;
                        random_value=0; two.Play(); assert(last_asset=="flower_random_00.ogg");
                        two.Play(); assert(last_asset=="flower_random_01.ogg");
                    }
                    for (std::string empty : {std::string{}, std::string(1025,'x'), std::string("{}"),
                        std::string(R"({"version":2,"count":4,"common":0,"morning":4,"afternoon":0,"evening":0})")}) {
                        manifest=empty; fake_now=0; RandomPhrasePlayer common_only;
                        before=play_calls; common_only.Play(); assert(play_calls==before);
                    }
                    for (const char* invalid : {
                        "null", "[]", R"({"version":3,"count":1})", R"({"version":1,"count":65})",
                        R"({"version":2,"count":4,"common":4})",
                        R"({"version":2,"count":4,"common":3,"morning":0,"afternoon":0,"evening":0})",
                        R"({"version":2,"count":4,"common":4,"morning":true,"afternoon":0,"evening":0})",
                        R"({"version":2,"count":4,"common":4,"morning":-1,"afternoon":0,"evening":1})",
                        R"({"version":2,"count":4,"common":4,"morning":0.5,"afternoon":0,"evening":0})"}) {
                        manifest=invalid; fake_now=day+6*3600; RandomPhrasePlayer bad;
                        before=play_calls; bad.Play(); assert(play_calls==before);
                    }
                }
            ''')
            subprocess.run(compiler + ["-std=c++20", "-Wall", "-Wextra", "-Werror",
                                       f"-I{build}", f"-I{BOARD}", f"-I{ROOT / 'main'}", *flags,
                                       str(source), str(BOARD / "random_phrase.cc"), *libs,
                                       "-o", str(build / "test")], check=True)
            subprocess.run([str(build / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
