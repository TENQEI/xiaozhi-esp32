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
                    #define ESP_LOGI(...) ((void)0)
                    #define ESP_LOGW(...) ((void)0)
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
                    inline std::optional<uint32_t> persisted, pending;
                    inline std::vector<uint32_t> persisted_blob, pending_blob;
                    inline int commits = 0;
                    inline int nvs_open(const char* ns, int, nvs_handle_t* handle) {
                        assert(std::strcmp(ns, "flower_time") == 0);
                        if (fail_open) return ESP_FAIL;
                        *handle = 1; return ESP_OK;
                    }
                    inline int nvs_get_u32(nvs_handle_t, const char*, uint32_t* out) {
                        if (!persisted) return ESP_FAIL;
                        *out = *persisted; return ESP_OK;
                    }
                    inline int nvs_set_u32(nvs_handle_t, const char*, uint32_t value) {
                        if (fail_set) return ESP_FAIL;
                        pending = value; return ESP_OK;
                    }
                    inline int nvs_get_blob(nvs_handle_t, const char*, void* out, size_t* size) {
                        if (persisted_blob.empty() || *size < persisted_blob.size() * 4) return ESP_FAIL;
                        *size = persisted_blob.size() * 4;
                        std::memcpy(out, persisted_blob.data(), *size); return ESP_OK;
                    }
                    inline int nvs_set_blob(nvs_handle_t, const char*, const void* value, size_t size) {
                        if (fail_set) return ESP_FAIL;
                        const auto* words = static_cast<const uint32_t*>(value);
                        pending_blob.assign(words, words + size / 4); return ESP_OK;
                    }
                    inline int nvs_commit(nvs_handle_t) {
                        if (fail_commit) return ESP_FAIL;
                        if (pending) persisted = pending;
                        if (!pending_blob.empty()) persisted_blob = pending_blob;
                        ++commits; return ESP_OK;
                    }
                    inline void nvs_close(nvs_handle_t) { pending.reset(); pending_blob.clear(); }
                ''',
                "esp_random.h": r'''
                    #pragma once
                    #include <cstring>
                    inline void esp_fill_random(void* out, size_t size) { std::memset(out, 42, size); }
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
            for name, content in headers.items():
                (build / name).write_text(content)
            source = build / "driver.cc"
            source.write_text(r'''
                #include "greeting_time_settings.h"
                #include "time_config_web.h"
                #include "chime_schedule.h"
                #include "nvs.h"
                #include "esp_netif.h"
                #include <thread>
                using namespace flower;
                int main() {
                    GreetingTimeSettings times;
                    assert(times.Get().morning == 480 && times.Get().night == 1200);
                    times.SetDefaults({540, 1260});
                    assert(times.Get().morning == 540);
                    assert(!times.Save({-1, 1200}) && !times.Save({0, 1440}));
                    assert(commits == 0);
                    persisted = PackTimes({510, 1215});
                    GreetingTimeSettings legacy;
                    assert(legacy.GetSchedule().mode == CalendarMode::Daily);
                    assert(legacy.GetSchedule().restday.morning == 510);
                    assert(commits == 0); // migration does not write during boot
                    persisted.reset();
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
                    persisted_blob = {99, 0, 0};
                    assert(GreetingTimeSettings().Get().morning == 480); // reject corrupt storage
                    persisted_blob = {0, UINT32_MAX, 0};
                    assert(GreetingTimeSettings().Get().morning == 480);
                    persisted_blob = {0, 0};
                    assert(GreetingTimeSettings().Get().morning == 480);
                    persisted_blob = backup;

                    TimeConfigWeb web(times);
                    fail_start = true; web.SetConnected(true); assert(routes.empty());
                    fail_start = false; fail_registration = true;
                    web.SetConnected(true); assert(routes.empty());
                    fail_registration = false; web.SetConnected(true);
                    assert(routes.size() == 3);
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
                    assert(get.response == R"({"mode":0,"work_morning":510,"work_night":1215,"rest_morning":510,"rest_night":1215,"calendar_year":2026})");
                    assert(get.response_headers["Cache-Control"] == "no-store");
                    std::string valid = R"({"mode":2,"work_morning":0,"work_night":1439,"rest_morning":540,"rest_night":1320})";
                    auto saved = Send(HTTP_POST, "/api/times", valid, token);
                    assert(saved.status == "200 OK");
                    assert(times.GetSchedule().mode == CalendarMode::ChinaHolidays);
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
                        R"({"mode":3,"work_morning":0,"work_night":1,"rest_morning":2,"rest_night":3})",
                        R"({"mode":true,"work_morning":0,"work_night":1,"rest_morning":2,"rest_night":3})",
                        R"({"mode":1,"work_morning":0,"work_night":1,"rest_morning":2,"rest_night":1440})",
                        R"({"mode":1,"work_morning":0,"work_night":1,"rest_morning":-1,"rest_night":3})",
                        R"({"mode":1,"work_morning":0,"work_night":1,"rest_morning":2.5,"rest_night":3})",
                        R"({"mode":1,"work_morning":0,"work_night":1,"rest_morning":2,"rest_morning":3})"}) {
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

                    // A reader sees one complete mode + both time pairs, never a mixed version.
                    GreetingSchedule first{CalendarMode::Daily, {1,2}, {3,4}};
                    GreetingSchedule second{CalendarMode::ChinaHolidays, {5,6}, {7,8}};
                    assert(times.SaveSchedule(first));
                    std::atomic<bool> done{false};
                    std::thread reader([&] {
                        while (!done.load()) {
                            auto value = times.GetSchedule();
                            assert((value.mode == first.mode && value.workday.morning == 1 &&
                                    value.workday.night == 2 && value.restday.morning == 3 && value.restday.night == 4) ||
                                   (value.mode == second.mode && value.workday.morning == 5 &&
                                    value.workday.night == 6 && value.restday.morning == 7 && value.restday.night == 8));
                        }
                    });
                    for (int i = 0; i < 1000; ++i) {
                        assert(times.SaveSchedule(i % 2 ? first : second));
                    }
                    done.store(true); reader.join();
                }
            ''')
            subprocess.run(compiler + ["-std=c++20", "-Wall", "-Wextra", "-Werror", "-pthread",
                                       f"-I{build}", f"-I{BOARD}", f"-I{ROOT / 'main'}", *flags,
                                       str(source), str(BOARD / "greeting_time_settings.cc"),
                                       str(BOARD / "time_config_web.cc"), *libs,
                                       "-o", str(build / "test")], check=True)
            subprocess.run([str(build / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
