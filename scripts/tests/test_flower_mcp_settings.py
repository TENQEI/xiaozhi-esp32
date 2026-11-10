"""Exercise real persisted time settings and device MCP tools with host doubles."""

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/flower-s3"


class FlowerMcpSettingsTest(unittest.TestCase):
    def test_mcp_times_switch_persistence_live_settings_and_failures(self):
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            flags = shlex.split(os.environ.get("FLOWER_CJSON_CFLAGS", "-I/usr/include/cjson"))
            libs = shlex.split(os.environ.get("FLOWER_CJSON_LIBS", "-lcjson"))
            probe = subprocess.run(
                compiler + ["-x", "c++", "-", *flags, *libs, "-o", str(build / "probe")],
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
                "esp_err.h": r'''
                    #pragma once
                    using esp_err_t = int;
                    constexpr int ESP_OK = 0, ESP_FAIL = -1;
                    inline const char* esp_err_to_name(int) { return "test failure"; }
                ''',
                "esp_log.h": r'''
                    #pragma once
                    #define ESP_LOGI(tag, ...) ((void)(tag))
                    #define ESP_LOGW(tag, ...) ((void)(tag))
                ''',
                "nvs.h": r'''
                    #pragma once
                    #include "esp_err.h"
                    #include <cassert>
                    #include <cstdint>
                    #include <cstring>
                    #include <optional>
                    #include <vector>
                    using nvs_handle_t = unsigned;
                    constexpr int NVS_READONLY = 0, NVS_READWRITE = 1;
                    inline bool fail_open = false, fail_set = false, fail_commit = false;
                    inline std::optional<uint32_t> persisted, pending, persisted_enabled, pending_enabled;
                    inline std::vector<uint32_t> persisted_blob, legacy_blob, pending_blob;
                    inline int commits = 0;
                    inline int nvs_open(const char* ns, int, nvs_handle_t* handle) {
                        assert(std::strcmp(ns, "flower_time") == 0);
                        if (fail_open) return ESP_FAIL;
                        *handle = 1; return ESP_OK;
                    }
                    inline int nvs_get_u32(nvs_handle_t, const char* key, uint32_t* out) {
                        const auto& value = std::strcmp(key, "announce_on") == 0 ? persisted_enabled : persisted;
                        if (!value) return ESP_FAIL;
                        *out = *value; return ESP_OK;
                    }
                    inline int nvs_set_u32(nvs_handle_t, const char* key, uint32_t value) {
                        if (fail_set) return ESP_FAIL;
                        (std::strcmp(key, "announce_on") == 0 ? pending_enabled : pending) = value; return ESP_OK;
                    }
                    inline int nvs_get_blob(nvs_handle_t, const char* key, void* out, size_t* size) {
                        auto& blob = std::strcmp(key, "schedule_v3") == 0 ? persisted_blob : legacy_blob;
                        if (blob.empty() || *size < blob.size() * 4) return ESP_FAIL;
                        *size = blob.size() * 4;
                        std::memcpy(out, blob.data(), *size); return ESP_OK;
                    }
                    inline int nvs_set_blob(nvs_handle_t, const char* key, const void* value, size_t size) {
                        assert(std::strcmp(key, "schedule_v3") == 0);
                        if (fail_set) return ESP_FAIL;
                        const auto* words = static_cast<const uint32_t*>(value);
                        pending_blob.assign(words, words + size / 4); return ESP_OK;
                    }
                    inline int nvs_commit(nvs_handle_t) {
                        if (fail_commit) return ESP_FAIL;
                        if (pending) persisted = pending;
                        if (pending_enabled) persisted_enabled = pending_enabled;
                        if (!pending_blob.empty()) persisted_blob = pending_blob;
                        ++commits; return ESP_OK;
                    }
                    inline void nvs_close(nvs_handle_t) { pending.reset(); pending_enabled.reset(); pending_blob.clear(); }
                ''',
                "esp_random.h": r'''
                    #pragma once
                    #include <cstring>
                    inline void esp_fill_random(void* out, size_t size) { std::memset(out, 42, size); }
                    inline unsigned phrase_random = 0;
                    inline unsigned esp_random() { return phrase_random; }
                ''',

            }
            headers["esp_system.h"] = '#pragma once\n#include <cstdlib>\n[[noreturn]] inline void esp_system_abort(const char*){std::abort();}\n'
            (build / "mbedtls").mkdir()
            (build / "mbedtls/base64.h").write_text('#pragma once\n#include <cstddef>\ninline int mbedtls_base64_encode(unsigned char*,size_t,size_t*,const unsigned char*,size_t){return -1;}\n')
            # Use the production Property/PropertyList/McpTool implementations;
            # only replace the registry and platform dependencies.
            headers["mcp_server.h"] = (ROOT / "main/mcp_server.h").read_text().split('class McpServer {')[0] + r'''
                class McpServer {
                public:
                    std::vector<std::unique_ptr<McpTool>> tools;
                    static McpServer& GetInstance(){static McpServer server;return server;}
                    void AddTool(const std::string& name,const std::string& description,
                                 const PropertyList& properties,ToolCallback callback){
                        tools.push_back(std::make_unique<McpTool>(name,description,properties,std::move(callback)));
                    }
                };
                #endif
            '''
            headers["esp_timer.h"] = r'''
                #pragma once
                #include <cstdint>
                inline int64_t monotonic_us = 0;
                inline int64_t esp_timer_get_time() { return monotonic_us; }
            '''
            headers["application.h"] = r'''
                #pragma once
                constexpr int kDeviceStateIdle=0;
                inline bool device_idle = true, playback_idle = true;
                class AudioService {public:
                    bool IsPlaybackIdle(){return playback_idle;}
                };
                class Application {public:
                    AudioService audio;
                    AudioService& GetAudioService(){return audio;}
                    static Application& GetInstance(){static Application app;return app;}
                    int GetDeviceState(){return device_idle ? kDeviceStateIdle : 1;}
                };
            '''
            for name, content in headers.items():
                (build / name).write_text(content)
            source = build / "driver.cc"
            source.write_text(r'''
                #include "greeting_time_settings.h"
                #include "chime_schedule.h"
                #include "announcement_mcp_tools.h"
                #include "mcp_server.h"
                #include "hourly_chime.h"
                #include "nvs.h"
                #include "esp_random.h"
                #include "esp_timer.h"
                #include "application.h"
                #include <thread>
                using namespace flower;
                int clocks=0,greetings=0,phrases=0;
                std::time_t now=0;
                extern "C" std::time_t time(std::time_t* value)
#ifndef __APPLE__
                    noexcept
#endif
                {if(value)*value=now;return now;}
                bool FlowerAudioManager::AutomaticEnabled() const{return true;}
                bool FlowerAudioManager::GreetingEnabled(bool) const{return true;}
                bool FlowerAudioManager::PlayClock(int){++clocks;return true;}
                bool FlowerAudioManager::PlayGreeting(bool){++greetings;return true;}
                void FlowerAudioManager::PlayPhrase(){++phrases;}
                int main() {
                    constexpr std::time_t day = 1762041600;
                    GreetingTimeSettings times;
                    assert(times.Get().morning == 480 && times.Get().night == 1200);
                    times.SetDefaults({540, 1260});
                    assert(times.Get().morning == 540);
                    assert(!times.Save({-1, 1200}) && !times.Save({0, 1440}));
                    assert(commits == 0);
                    assert(times.AnnouncementsEnabled());
                    persisted_enabled=2;assert(GreetingTimeSettings().AnnouncementsEnabled());
                    persisted_enabled.reset();
                    persisted = PackTimes({510, 1215});
                    GreetingTimeSettings legacy;
                    assert(legacy.GetSchedule().restday.morning == 510);
                    assert(commits == 0); // migration does not write during boot
                    persisted.reset();
                    for (uint32_t mode : {0, 1, 2}) {
                        legacy_blob = {mode, PackTimes({510,1215}), PackTimes({570,1320})};
                        GreetingTimeSettings migrated;
                        assert(migrated.GetSchedule().workday.morning == 510);
                        assert(migrated.GetSchedule().restday.morning == (mode == 0 ? 510 : 570));
                    }
                    legacy_blob.clear();
                    assert(commits == 0);
                    assert(times.Save({510, 1215}));
                    times.SetDefaults({480, 1200});
                    assert(times.Get().morning == 510); // saved override wins
                    GreetingTimeSettings reboot;
                    assert(reboot.Get().morning == 510 && reboot.Get().night == 1215);
                    fail_open = true; assert(!times.Save({0, 1})); fail_open = false;
                    fail_set = true; assert(!times.Save({0, 1})); fail_set = false;
                    fail_commit = true; assert(!times.Save({0, 1})); fail_commit = false;
                    assert(times.Get().morning == 510);
                    assert(GreetingTimeSettings().Get().morning == 510);
                    auto backup = persisted_blob;
                    persisted_blob = {UINT32_MAX, 0};
                    assert(GreetingTimeSettings().Get().morning == 480); // reject corrupt storage
                    persisted_blob = {0, UINT32_MAX};
                    assert(GreetingTimeSettings().Get().morning == 480);
                    persisted_blob = {0};
                    assert(GreetingTimeSettings().Get().morning == 480);
                    persisted_blob = backup;

                    InitializeAnnouncementTools(times);
                    auto& tools=McpServer::GetInstance().tools;
                    assert(tools.size()==4 && !tools[0]->user_only() && !tools[1]->user_only() && !tools[2]->user_only() && !tools[3]->user_only());
                    assert(tools[0]->name()=="self.flower.get_announcements");
                    assert(tools[1]->name()=="self.flower.set_announcements_enabled");
                    auto schema=tools[1]->to_json();
                    assert(schema.find("enabled")!=std::string::npos);
                    CJsonUniquePtr declared(cJSON_Parse(schema.c_str()));
                    auto* input=cJSON_GetObjectItem(declared.get(),"inputSchema");
                    auto* properties=cJSON_GetObjectItem(input,"properties");
                    auto* field=cJSON_GetObjectItem(properties,"enabled");
                    assert(std::strcmp(cJSON_GetObjectItem(field,"type")->valuestring,"boolean")==0);
                    assert(std::strcmp(cJSON_GetArrayItem(cJSON_GetObjectItem(input,"required"),0)->valuestring,"enabled")==0);
                    auto set=[&](bool value){
                        auto args=tools[1]->properties();for(auto& property:args)assert(property.set_value<bool>(value));
                        return tools[1]->Call(args);
                    };
                    assert(times.AnnouncementsEnabled());
                    assert(set(false));assert(!times.AnnouncementsEnabled());
                    assert(!GreetingTimeSettings().AnnouncementsEnabled());
                    int writes=commits;assert(set(false));assert(commits==writes);
                    for (int error=0;error<3;++error){
                        fail_open=error==0;fail_set=error==1;fail_commit=error==2;
                        assert(!set(true));
                        fail_open=fail_set=fail_commit=false;
                        assert(!times.AnnouncementsEnabled() && !GreetingTimeSettings().AnnouncementsEnabled());
                    }
                    assert(set(true));
                    auto status=tools[0]->Call(PropertyList());assert(status);
                    assert(status->find("true")!=std::string::npos && GreetingTimeSettings().AnnouncementsEnabled());
                    assert(tools[2]->name()=="self.flower.get_greeting_times");
                    assert(tools[3]->name()=="self.flower.set_greeting_times");
                    auto get_times=[&]{return tools[2]->Call(PropertyList());};
                    auto save_times=[&](std::string morning,std::string night,std::string scope="all"){
                        auto args=tools[3]->properties();
                        for(auto& property:args){
                            const auto value=property.name()=="morning"?morning:property.name()=="night"?night:scope;
                            assert(property.set_value<std::string>(value));
                        }
                        return tools[3]->Call(args);
                    };
                    auto time_schema=tools[3]->to_json();
                    assert(time_schema.find("maxLength")!=std::string::npos);
                    CJsonUniquePtr times_schema(cJSON_Parse(time_schema.c_str()));
                    auto* time_input=cJSON_GetObjectItem(times_schema.get(),"inputSchema");
                    auto* time_properties=cJSON_GetObjectItem(time_input,"properties");
                    auto* time_scope=cJSON_GetObjectItem(time_properties,"scope");
                    assert(std::strcmp(cJSON_GetObjectItem(time_scope,"default")->valuestring,"all")==0);
                    assert(cJSON_GetArraySize(cJSON_GetObjectItem(time_input,"required"))==2);
                    assert(tools[3]->properties()["morning"].Validate(std::string("008:00")).size()>0);
                    assert(get_times()->find("08:30")!=std::string::npos);
                    assert(save_times("08:15","20:30"));
                    assert(times.GetSchedule().restday.morning==495);
                    assert(GreetingTimeSettings().GetSchedule().restday.night==1230);
                    assert(save_times("09:45","22:15","restday"));
                    assert(times.GetSchedule().workday.morning==495);
                    assert(times.GetSchedule().restday.morning==585);
                    assert(save_times("07:30","21:15","workday"));
                    assert(times.GetSchedule().workday.morning==450);
                    assert(times.GetSchedule().restday.night==1335);
                    assert(get_times()->find("22:15")!=std::string::npos);
                    auto saved_times=times.GetSchedule();int saved_commits=commits;
                    for(const char* bad:{"","8:00","24:00","23:60","00:-1","aa:bb","12.30"}){
                        assert(!save_times(bad,"20:00"));assert(!save_times("08:00",bad));
                    }
                    assert(!save_times("08:00","20:00","daily"));
                    assert(commits==saved_commits);
                    assert(times.GetSchedule().workday.morning==saved_times.workday.morning);
                    for(int error=0;error<3;++error){
                        fail_open=error==0;fail_set=error==1;fail_commit=error==2;
                        assert(!save_times("00:00","23:59"));
                        fail_open=fail_set=fail_commit=false;
                        assert(times.GetSchedule().restday.morning==saved_times.restday.morning);
                        assert(GreetingTimeSettings().GetSchedule().workday.morning==saved_times.workday.morning);
                    }
                    assert(save_times("00:00","23:59"));
                    assert(times.GetSchedule().workday.morning==0 && times.GetSchedule().restday.night==1439);
                    assert(save_times("12:00","12:00","workday"));
                    assert(times.GetSchedule().workday.morning==times.GetSchedule().workday.night);
                    // Time changes preserve the master switch and existing NVS keys.
                    auto kept=times.GetSchedule();assert(set(false));
                    assert(times.GetSchedule().workday.morning==kept.workday.morning);
                    assert(times.SaveSchedule({{480,1200},{480,1200}}));
                    assert(!times.AnnouncementsEnabled() && !GreetingTimeSettings().AnnouncementsEnabled());
                    FlowerAudioManager audio;HourlyChime automatic(times,audio);
                    for(int minute : {480,540,1200}){
                        now=day+minute*60-1;automatic.Tick();++now;automatic.Tick();
                    }
                    assert(clocks==0 && greetings==0); // off covers morning, hour, night
                    assert(set(true));automatic.Tick();assert(clocks==0 && greetings==0); // no catch-up
                    now=day+1440*60+480*60-1;automatic.Tick();++now;automatic.Tick();
                    assert(greetings==1 && clocks==0);
                    now=day+1440*60+540*60-1;automatic.Tick();++now;automatic.Tick();assert(clocks==1);
                    now=day+1440*60+1200*60-1;automatic.Tick();++now;automatic.Tick();assert(greetings==2);

                    // One switch gates the three scheduled cues and random chatter.
                    HourlyChime chatter(times, audio);
                    auto tick = [&](int minute, int elapsed) {
                        now = day + 2 * 86400 + minute * 60 + 15;
                        monotonic_us = static_cast<int64_t>(elapsed) * 1000000;
                        chatter.Tick();
                    };
                    now = 0;
                    chatter.Tick();
                    tick(490, 0);
                    tick(510, 1799);
                    assert(phrases == 0);
                    tick(520, 1800);
                    assert(phrases == 1);
                    assert(set(false));
                    tick(530, 1801);
                    tick(590, 6000);
                    assert(phrases == 1);
                    assert(set(true));
                    tick(600, 6001);
                    device_idle = false;
                    tick(620, 7801);
                    assert(phrases == 1);
                    device_idle = true;
                    tick(621, 7802);
                    playback_idle = false;
                    tick(650, 9602);
                    assert(phrases == 1);
                    playback_idle = true;
                    tick(651, 9603);
                    tick(1200, 11403);
                    assert(phrases == 1);
                    tick(490, 11404);
                    tick(519, 13203);
                    assert(phrases == 1);
                    tick(520, 13204);
                    assert(phrases == 2);

                    // The maximum draw is 90 minutes; a manual play resets the timer.
                    phrase_random = 3600;
                    tick(521, 13205);
                    chatter.ResetPhraseTimer();
                    tick(525, 14000);
                    tick(615, 19399);
                    assert(phrases == 2);
                    tick(615, 19400);
                    assert(phrases == 3);

                    // An imminent evening greeting reserves its playback window.
                    phrase_random = 0;
                    tick(1150, 19401);
                    tick(1199, 21201);
                    assert(phrases == 3);

                    // A reader sees both time pairs together, never a mixed version.
                    GreetingSchedule first{{1,2}, {3,4}};
                    GreetingSchedule second{{5,6}, {7,8}};
                    assert(times.SaveSchedule(first));
                    std::atomic<bool> done{false};
                    std::thread reader([&] {
                        while (!done.load()) {
                            auto value = times.GetSchedule();
                            assert((value.workday.morning == 1 &&
                                    value.workday.night == 2 && value.restday.morning == 3 && value.restday.night == 4) ||
                                   (value.workday.morning == 5 &&
                                    value.workday.night == 6 && value.restday.morning == 7 && value.restday.night == 8));
                        }
                    });
                    for (int i = 0; i < 1000; ++i) {
                        assert(times.SaveSchedule(i % 2 ? first : second));
                    }
                    done.store(true); reader.join();
                }
            ''')
            subprocess.run(compiler + ["-std=c++23", "-Wall", "-Wextra", "-Werror", "-pthread",
                                       f"-I{build}", f"-I{BOARD}", f"-I{ROOT / 'main'}", *flags,
                                       str(source), str(BOARD / "greeting_time_settings.cc"),
                                       str(BOARD / "announcement_mcp_tools.cc"),
                                       str(BOARD / "hourly_chime.cc"), *libs,
                                       "-o", str(build / "test")], check=True)
            subprocess.run([str(build / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
