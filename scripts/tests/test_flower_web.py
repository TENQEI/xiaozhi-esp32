"""Exercise the real time settings and HTTP handlers with NVS/network doubles."""

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/flower-s3"


class FlowerWebTest(unittest.TestCase):
    def test_http_validation_persistence_live_settings_and_failures(self):
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
                "esp_netif.h": r'''
                    #pragma once
                    #include "esp_err.h"
                    #include <cstdint>
                    struct esp_ip4_addr_t { uint32_t addr; };
                    struct esp_netif_ip_info_t { esp_ip4_addr_t ip; };
                    inline uint32_t station_ip = 12;
                    inline void* esp_netif_get_handle_from_ifkey(const char*) { return &station_ip; }
                    inline int esp_netif_get_ip_info(void*, esp_netif_ip_info_t* info) {
                        info->ip.addr = station_ip; return ESP_OK;
                    }
                    #define IPSTR "%d.%d.%d.%d"
                    #define IP2STR(ip) 192,168,50,static_cast<int>((ip)->addr)
                ''',
                "esp_http_server.h": r'''
                    #pragma once
                    #include "esp_err.h"
                    #include <algorithm>
                    #include <cassert>
                    #include <cstring>
                    #include <map>
                    #include <string>
                    #include <vector>
                    enum httpd_method_t { HTTP_GET, HTTP_POST };
                    struct httpd_req_t {
                        void* user_ctx = nullptr;
                        httpd_method_t method = HTTP_GET;
                        const char* uri = "/";
                        size_t content_len = 0, offset = 0;
                        std::map<std::string,std::string> headers, response_headers;
                        std::string body, response, status = "200 OK", content_type;
                        int chunk = 7;
                    };
                    using httpd_handle_t = void*;
                    struct httpd_config_t {
                        unsigned server_port = 80, ctrl_port = 32768, stack_size = 4096;
                        unsigned max_open_sockets = 7, max_uri_handlers = 8;
                        bool lru_purge_enable = false;
                        unsigned recv_wait_timeout = 5, send_wait_timeout = 5;
                    };
                    #define HTTPD_DEFAULT_CONFIG() httpd_config_t{}
                    constexpr int HTTPD_RESP_USE_STRLEN = -1;
                    struct httpd_uri_t {
                        const char* uri;
                        httpd_method_t method;
                        esp_err_t (*handler)(httpd_req_t*);
                        void* user_ctx;
                    };
                    inline std::vector<httpd_uri_t> routes;
                    inline bool fail_start = false, fail_registration = false;
                    inline int server_starts = 0;
                    inline int httpd_start(httpd_handle_t* handle, const httpd_config_t* config) {
                        assert(config->server_port == 8080 && config->ctrl_port != 32768);
                        if (fail_start) return ESP_FAIL;
                        ++server_starts; *handle = &server_starts; return ESP_OK;
                    }
                    inline int httpd_stop(httpd_handle_t) { routes.clear(); return ESP_OK; }
                    inline int httpd_register_uri_handler(httpd_handle_t, const httpd_uri_t* uri) {
                        if (fail_registration) return ESP_FAIL;
                        routes.push_back(*uri); return ESP_OK;
                    }
                    inline int httpd_req_get_hdr_value_str(httpd_req_t* req, const char* key,
                                                           char* value, size_t capacity) {
                        auto it = req->headers.find(key);
                        if (it == req->headers.end() || it->second.size() >= capacity) return ESP_FAIL;
                        std::strcpy(value, it->second.c_str()); return ESP_OK;
                    }
                    inline int httpd_resp_set_hdr(httpd_req_t* req, const char* key, const char* value) {
                        req->response_headers[key] = value; return ESP_OK;
                    }
                    inline int httpd_resp_set_status(httpd_req_t* req, const char* status) {
                        req->status = status; return ESP_OK;
                    }
                    inline int httpd_resp_set_type(httpd_req_t* req, const char* type) {
                        req->content_type = type; return ESP_OK;
                    }
                    inline int httpd_resp_send(httpd_req_t* req, const char* data, int size) {
                        req->response.assign(data, size < 0 ? std::strlen(data) : size); return ESP_OK;
                    }
                    inline int httpd_req_recv(httpd_req_t* req, char* data, size_t size) {
                        if (req->chunk <= 0) return req->chunk;
                        size = std::min({size, req->body.size() - req->offset, size_t(req->chunk)});
                        std::memcpy(data, req->body.data() + req->offset, size);
                        req->offset += size; return static_cast<int>(size);
                    }
                    inline httpd_req_t Send(httpd_method_t method, const char* uri, std::string body = "",
                                            std::string token = "", const char* host = "192.168.50.12:8080",
                                            const char* type = "application/json", int chunk = 7,
                                            int length = -1) {
                        httpd_req_t req;
                        req.method = method; req.uri = uri; req.body = body;
                        req.content_len = length < 0 ? body.size() : length; req.chunk = chunk;
                        req.headers = {{"Host",host},{"X-Flower-Token",token},{"Content-Type",type}};
                        for (auto& route : routes) {
                            if (route.method == method && std::strcmp(route.uri, uri) == 0) {
                                req.user_ctx = route.user_ctx; route.handler(&req); return req;
                            }
                        }
                        assert(false); return req;
                    }
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
                #include "time_config_web.h"
                #include "chime_schedule.h"
                #include "announcement_mcp_tools.h"
                #include "mcp_server.h"
                #include "hourly_chime.h"
                #include "nvs.h"
                #include "esp_netif.h"
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

                    TimeConfigWeb web(times);
                    fail_start = true; web.SetConnected(true); assert(routes.empty());
                    fail_start = false; fail_registration = true;
                    web.SetConnected(true); assert(routes.empty());
                    fail_registration = false; web.SetConnected(true);
                    assert(routes.size() == 5);
                    const int started = server_starts;
                    web.SetConnected(true); assert(server_starts == started);
                    auto page = Send(HTTP_GET, "/");
                    assert(page.status == "200 OK" && page.content_type == "text/html; charset=utf-8");
                    assert(page.response.find("@@TOKEN@@") == std::string::npos);
                    auto at = page.response.find("const token='"); assert(at != std::string::npos);
                    std::string token = page.response.substr(at + 13, 32);
                    assert(token.size() == 32);
                    for (size_t i = 0; i < token.size(); i += 2) assert(token.substr(i, 2) == "2a");
                    auto get = Send(HTTP_GET, "/api/times");
                    assert(get.response == R"({"work_morning":510,"work_night":1215,"rest_morning":510,"rest_night":1215})");
                    assert(get.response_headers["Cache-Control"] == "no-store");
                    std::string valid = R"({"work_morning":0,"work_night":1439,"rest_morning":540,"rest_night":1320})";
                    auto saved = Send(HTTP_POST, "/api/times", valid, token);
                    assert(saved.status == "200 OK");
                    assert(times.GetSchedule().restday.morning == 540);
                    assert(GreetingTimeSettings().Get().night == 1439);
                    assert(GreetingTimeSettings().GetSchedule().restday.night == 1320);
                    // Live snapshot reaches the real scheduling policy without rebooting.
                    ChimeConfig config{0, true, 0, 0, true, true};
                    auto live = times.Get(); config.quiet_start = live.night / 60;
                    config.quiet_start_minute = live.night % 60;
                    ChimeSchedule schedule;
                    constexpr std::time_t day = 1762041600;
                    schedule.Poll(day + 1439 * 60 - 1, config, true);
                    assert(schedule.Poll(day + 1439 * 60, config, true) == ChimeSchedule::kGoodNight);
                    const int before = commits;
                    for (std::string bad : std::vector<std::string>{
                        "", "null", "[]", "{}", R"({"morning":480})",
                        R"({"morning":480,"night":1440})", R"({"morning":-1,"night":0})",
                        R"({"morning":true,"night":1})", R"({"morning":"08:00","night":1})",
                        R"({"morning":1.5,"night":0})", R"({"morning":1e99,"night":0})",
                        R"({"morning":{},"night":0})", std::string(63, '[') + std::string(63, ']'),
                        R"({"morning":1,"night":0,"extra":1})",
                        R"({"morning":1,"morning":2})", valid + " trailing"}) {
                        assert(Send(HTTP_POST, "/api/times", bad, token).status == "400 Bad Request");
                    }
                    for (std::string bad : std::vector<std::string>{
                        R"({"work_morning":true,"work_night":1,"rest_morning":2,"rest_night":3})",
                        R"({"work_morning":0,"work_night":1,"rest_morning":2,"rest_night":1440})",
                        R"({"work_morning":0,"work_night":1,"rest_morning":-1,"rest_night":3})",
                        R"({"work_morning":0,"work_night":1,"rest_morning":2.5,"rest_night":3})",
                        R"({"work_morning":0,"work_night":1,"rest_morning":2,"rest_morning":3})"}) {
                        assert(Send(HTTP_POST, "/api/times", bad, token).status == "400 Bad Request");
                    }
                    assert(Send(HTTP_POST, "/api/times", valid + '\0' + "x", token).status == "400 Bad Request");
                    assert(Send(HTTP_POST, "/api/times", std::string(193, 'x'), token).status == "400 Bad Request");
                    assert(Send(HTTP_POST, "/api/times", valid, "bad").status == "403 Forbidden");
                    assert(Send(HTTP_POST, "/api/times", valid, token, "evil.test:8080").status == "403 Forbidden");
                    assert(Send(HTTP_POST, "/api/times", valid, token, "192.168.50.12:8080", "text/plain").status == "403 Forbidden");
                    assert(Send(HTTP_POST, "/api/times", valid, token, "192.168.50.12:8080", "application/json", -1).status == "408 Request Timeout");
                    assert(Send(HTTP_POST, "/api/times", valid, token, "192.168.50.12:8080", "application/json", 7, 100).status == "408 Request Timeout");
                    assert(commits == before);
                    assert(times.Get().morning == 0 && times.Get().night == 1439);
                    fail_commit = true;
                    assert(Send(HTTP_POST, "/api/times", valid, token).status == "500 Internal Server Error");
                    fail_commit = false;
                    assert(times.Get().morning == 0 && times.Get().night == 1439);
                    web.SetConnected(false);
                    assert(Send(HTTP_GET, "/").status == "403 Forbidden");
                    web.SetConnected(true); station_ip = 13;
                    assert(Send(HTTP_GET, "/").status == "403 Forbidden");
                    assert(Send(HTTP_GET, "/", "", "", "192.168.50.13:8080").status == "200 OK");

                    // MCP and HTTP share the same persisted master switch.
                    InitializeAnnouncementTools(times);
                    auto& tools=McpServer::GetInstance().tools;
                    assert(tools.size()==2 && !tools[0]->user_only() && !tools[1]->user_only());
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
                    assert(Send(HTTP_GET,"/api/announcements","","","192.168.50.13:8080").response==R"({"enabled":false})");
                    int writes=commits;assert(set(false));assert(commits==writes);
                    for (int error=0;error<3;++error){
                        fail_open=error==0;fail_set=error==1;fail_commit=error==2;
                        assert(!set(true));
                        fail_open=fail_set=fail_commit=false;
                        assert(!times.AnnouncementsEnabled() && !GreetingTimeSettings().AnnouncementsEnabled());
                    }
                    assert(Send(HTTP_POST,"/api/announcements",R"({"enabled":true})",token,"192.168.50.13:8080").status=="200 OK");
                    auto status=tools[0]->Call(PropertyList());assert(status);
                    assert(status->find("true")!=std::string::npos && GreetingTimeSettings().AnnouncementsEnabled());
                    for(const auto* bad : {"{}","null",R"({"enabled":0})",R"({"enabled":"false"})",R"({"enabled":true,"extra":1})",R"({"enabled":true,"enabled":false})"}){
                        assert(Send(HTTP_POST,"/api/announcements",bad,token,"192.168.50.13:8080").status=="400 Bad Request");
                    }
                    assert(Send(HTTP_POST,"/api/announcements",R"({"enabled":false})","bad","192.168.50.13:8080").status=="403 Forbidden");
                    fail_commit=true;
                    assert(Send(HTTP_POST,"/api/announcements",R"({"enabled":false})",token,"192.168.50.13:8080").status=="500 Internal Server Error");
                    fail_commit=false;assert(times.AnnouncementsEnabled());
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
                                       str(BOARD / "time_config_web.cc"),
                                       str(BOARD / "announcement_mcp_tools.cc"),
                                       str(BOARD / "hourly_chime.cc"), *libs,
                                       "-o", str(build / "test")], check=True)
            subprocess.run([str(build / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
