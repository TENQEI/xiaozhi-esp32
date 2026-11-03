#include "time_config_web.h"

#include "cjson_utils.h"

#include <esp_log.h>
#include <esp_netif.h>
#include <esp_random.h>
#include <cstdio>
#include <cstring>
#include <utility>

namespace flower {
namespace {
constexpr char kTag[] = "FlowerWeb";
constexpr int kPort = 8080;
constexpr char kPage[] = R"HTML(<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>报时与早晚安设置</title>
<style>
body{font:17px system-ui,sans-serif;max-width:460px;margin:48px auto;padding:0 24px;color:#222;background:#f7f7f4}
form{background:white;border-radius:16px;padding:24px}label{display:flex;justify-content:space-between;align-items:center;margin:18px 0}
input,button{font:inherit;padding:10px;border:1px solid #aaa;border-radius:8px}button{width:100%;background:#235b45;color:white;border:0;margin-top:16px}
fieldset{border:1px solid #ddd;border-radius:8px;margin:16px 0;padding:0 12px}
button:disabled{opacity:.5}p{line-height:1.6}#status{min-height:3em;white-space:pre-line}
</style>
<h1>报时与早晚安设置</h1>
<p>使用设备校时后的本地时间。晚安后进入免打扰，早安时结束免打扰。</p>
<label>启用报时与早晚安 <input id="announcements" type="checkbox" disabled></label>
<p id="announcement_status" role="status" aria-live="polite">正在读取开关…</p>
<p>关闭后停止整点报时、早安和晚安；保留时间设置，手动定型文和对话不受影响。</p>
<form id="form">
<p>按星期自动切换：工作日为周一至周五，双休为周六、周日。</p>
<fieldset><legend>工作日（周一至周五）</legend>
<label>早安 <input id="work_morning" type="time" step="60" required disabled></label>
<label>晚安 <input id="work_night" type="time" step="60" required disabled></label></fieldset>
<fieldset><legend>双休（周六、周日）</legend>
<label>早安 <input id="rest_morning" type="time" step="60" required disabled></label>
<label>晚安 <input id="rest_night" type="time" step="60" required disabled></label></fieldset>
<button id="save" disabled>保存时间</button>
</form>
<p id="status" role="status" aria-live="polite">正在读取…</p>
<p>保存后立即生效，重启后保留。一套时间中的早晚安相同，表示当天关闭免打扰和自动早晚安。需要已有对应音频；本页可修改自动播报总开关及时间，不修改音频。</p>
<script>
'use strict';
const token='@@TOKEN@@';
const keys=['work_morning','work_night','rest_morning','rest_night'];
const inputs=Object.fromEntries(keys.map(k=>[k,document.getElementById(k)]));
const button=document.getElementById('save'),status=document.getElementById('status');
const format=n=>String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
const minutes=s=>{const p=s.split(':').map(Number);return p[0]*60+p[1]};
async function request(options,url='/api/times'){
  const r=await fetch(url,{cache:'no-store',...options});
  if(!r.ok)throw new Error(await r.text());
  return r.json();
}
const announcements=document.getElementById('announcements'),announcementStatus=document.getElementById('announcement_status');
request(undefined,'/api/announcements').then(s=>{
  announcements.checked=s.enabled;announcements.disabled=false;
  announcementStatus.textContent=s.enabled?'报时与早晚安已打开。':'报时与早晚安已关闭。';
}).catch(()=>announcementStatus.textContent='读取报时开关失败，请刷新页面。');
announcements.addEventListener('change',async()=>{
  const enabled=announcements.checked;announcements.disabled=true;
  try{
    const saved=await request({method:'POST',headers:{'Content-Type':'application/json','X-Flower-Token':token},body:JSON.stringify({enabled})},'/api/announcements');
    announcements.checked=saved.enabled;
    announcementStatus.textContent=saved.enabled?'已打开报时与早晚安，下次到点生效，不补播。':'已关闭报时与早晚安，时间设置保留。';
  }catch{announcements.checked=!enabled;announcementStatus.textContent='未确认开关保存成功，请刷新页面核对。'}
  finally{announcements.disabled=false}
});
request().then(t=>{
  for(const k of keys){inputs[k].value=format(t[k]);inputs[k].disabled=false}
  button.disabled=false;status.textContent='已读取当前设置。';
}).catch(()=>status.textContent='读取失败，请确认设备已连接 Wi-Fi，然后刷新页面。');
document.getElementById('form').addEventListener('submit',async e=>{
  e.preventDefault();button.disabled=true;status.textContent='正在保存…';
  const times={};
  for(const k of keys)times[k]=minutes(inputs[k].value);
  try{
    const saved=await request({method:'POST',headers:{'Content-Type':'application/json','X-Flower-Token':token},body:JSON.stringify(times)});
    for(const k of keys)inputs[k].value=format(saved[k]);
    status.textContent='已保存。工作日和双休按星期自动切换，下次到达对应时间时播放，不补播已过去的时间。';
  }catch{status.textContent='未确认保存成功，请刷新页面核对后重试。'}
  finally{button.disabled=false}
});
</script></html>)HTML";

esp_err_t Reply(httpd_req_t* request, const char* status, const char* message) {
    httpd_resp_set_status(request, status);
    httpd_resp_set_type(request, "text/plain; charset=utf-8");
    return httpd_resp_send(request, message, HTTPD_RESP_USE_STRLEN);
}
}  // namespace

void TimeConfigWeb::SetConnected(bool connected) {
    connected_.store(connected);
    if (connected) {
        Start();
    }
}

bool TimeConfigWeb::Start() {
    if (server_) {
        return true;
    }
    uint8_t random[16];
    esp_fill_random(random, sizeof(random));
    token_.clear();
    for (uint8_t byte : random) {
        char hex[3];
        std::snprintf(hex, sizeof(hex), "%02x", byte);
        token_ += hex;
    }
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = kPort;
    config.ctrl_port = 32770;  // Separate from the Wi-Fi provisioning server.
    config.stack_size = 6144;
    config.max_open_sockets = 2;
    config.max_uri_handlers = 5;
    config.lru_purge_enable = true;
    config.recv_wait_timeout = 3;
    config.send_wait_timeout = 3;
    if (httpd_start(&server_, &config) != ESP_OK) {
        server_ = nullptr;
        ESP_LOGW(kTag, "Cannot start time settings server");
        return false;
    }
    for (const auto& route :
         {std::pair{"/", HTTP_GET}, std::pair{"/api/times", HTTP_GET},
          std::pair{"/api/times", HTTP_POST}, std::pair{"/api/announcements", HTTP_GET},
          std::pair{"/api/announcements", HTTP_POST}}) {
        httpd_uri_t uri = {};
        uri.uri = route.first;
        uri.method = route.second;
        uri.handler = Handle;
        uri.user_ctx = this;
        if (httpd_register_uri_handler(server_, &uri) != ESP_OK) {
            httpd_stop(server_);
            server_ = nullptr;
            return false;
        }
    }
    esp_netif_ip_info_t info = {};
    auto* netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (netif && esp_netif_get_ip_info(netif, &info) == ESP_OK) {
        ESP_LOGI(kTag, "Time settings: http://" IPSTR ":%d/", IP2STR(&info.ip), kPort);
    }
    return true;
}

bool TimeConfigWeb::IsLocalRequest(httpd_req_t* request) const {
    if (!connected_.load()) {
        return false;
    }
    esp_netif_ip_info_t info = {};
    auto* netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (!netif || esp_netif_get_ip_info(netif, &info) != ESP_OK || info.ip.addr == 0) {
        return false;
    }
    char expected[32];
    std::snprintf(expected, sizeof(expected), IPSTR ":%d", IP2STR(&info.ip), kPort);
    char host[64];
    return httpd_req_get_hdr_value_str(request, "Host", host, sizeof(host)) == ESP_OK &&
           std::strcmp(host, expected) == 0;
}

esp_err_t TimeConfigWeb::Handle(httpd_req_t* request) {
    return static_cast<TimeConfigWeb*>(request->user_ctx)->Serve(request);
}

esp_err_t TimeConfigWeb::Serve(httpd_req_t* request) {
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    httpd_resp_set_hdr(request, "X-Content-Type-Options", "nosniff");
    httpd_resp_set_hdr(request, "X-Frame-Options", "DENY");
    // Only the station IP is accepted, preventing arbitrary DNS names from
    // reaching this LAN endpoint. The AP provisioning service stays separate.
    if (!IsLocalRequest(request)) {
        Reply(request, "403 Forbidden", "请通过设备当前 Wi-Fi IP 地址访问。");
        return ESP_FAIL;  // Close a rejected request with an unread body.
    }
    if (request->method == HTTP_GET && std::strcmp(request->uri, "/") == 0) {
        std::string page(kPage);
        page.replace(page.find("@@TOKEN@@"), std::strlen("@@TOKEN@@"), token_);
        httpd_resp_set_type(request, "text/html; charset=utf-8");
        return httpd_resp_send(request, page.data(), page.size());
    }
    if (request->method == HTTP_POST) {
        char token[40];
        char content_type[64];
        if (httpd_req_get_hdr_value_str(request, "X-Flower-Token", token, sizeof(token)) !=
                ESP_OK ||
            token_ != token ||
            httpd_req_get_hdr_value_str(request, "Content-Type", content_type,
                                        sizeof(content_type)) != ESP_OK ||
            std::strcmp(content_type, "application/json") != 0) {
            Reply(request, "403 Forbidden", "请刷新设置页面后重试。");
            return ESP_FAIL;
        }
        if (request->content_len == 0 || request->content_len > 192) {
            Reply(request, "400 Bad Request", "时间设置格式无效。");
            return ESP_FAIL;
        }
        std::string body(request->content_len, '\0');
        size_t received = 0;
        while (received < body.size()) {
            const int count =
                httpd_req_recv(request, body.data() + received, body.size() - received);
            if (count <= 0) {
                Reply(request, "408 Request Timeout", "接收超时，请重试。");
                return ESP_FAIL;
            }
            received += count;
        }
        // This schema is flat. Reject nesting before the recursive JSON parser
        // so even a small malicious body cannot exhaust the HTTP task's stack.
        const bool flat = body.find('{') == body.rfind('{') && body.find('[') == std::string::npos;
        CJsonUniquePtr root(
            flat && body.find('\0') == std::string::npos
                ? cJSON_ParseWithLengthOpts(body.c_str(), body.size() + 1, nullptr, true)
                : nullptr);
        if (std::strcmp(request->uri, "/api/announcements") == 0) {
            const auto* enabled = cJSON_GetObjectItemCaseSensitive(root.get(), "enabled");
            if (!root || !cJSON_IsObject(root.get()) || cJSON_GetArraySize(root.get()) != 1 ||
                !cJSON_IsBool(enabled)) {
                return Reply(request, "400 Bad Request", "开关设置格式无效。");
            }
            if (!times_.SaveAnnouncementsEnabled(cJSON_IsTrue(enabled))) {
                return Reply(request, "500 Internal Server Error", "保存失败，原设置保持有效。");
            }
        } else {
            auto integer = [&root](const char* key, int maximum) -> int {
                const auto* item = cJSON_GetObjectItemCaseSensitive(root.get(), key);
                return cJSON_IsNumber(item) && item->valuedouble == item->valueint &&
                               item->valueint >= 0 && item->valueint <= maximum
                           ? item->valueint
                           : -1;
            };
            GreetingSchedule schedule{{integer("work_morning", 1439), integer("work_night", 1439)},
                                      {integer("rest_morning", 1439), integer("rest_night", 1439)}};
            if (!root || !cJSON_IsObject(root.get()) || cJSON_GetArraySize(root.get()) != 4 ||
                !ValidSchedule(schedule)) {
                return Reply(request, "400 Bad Request", "时间设置格式无效。");
            }
            if (!times_.SaveSchedule(schedule)) {
                return Reply(request, "500 Internal Server Error", "保存失败，原设置保持有效。");
            }
        }
    }
    if (std::strcmp(request->uri, "/api/announcements") == 0) {
        httpd_resp_set_type(request, "application/json");
        return httpd_resp_send(
            request, times_.AnnouncementsEnabled() ? "{\"enabled\":true}" : "{\"enabled\":false}",
            HTTPD_RESP_USE_STRLEN);
    }
    const auto schedule = times_.GetSchedule();
    char json[192];
    std::snprintf(json, sizeof(json),
                  "{\"work_morning\":%d,\"work_night\":%d,\"rest_morning\":%d,\"rest_night\":%d}",
                  schedule.workday.morning, schedule.workday.night, schedule.restday.morning,
                  schedule.restday.night);
    httpd_resp_set_type(request, "application/json");
    return httpd_resp_send(request, json, HTTPD_RESP_USE_STRLEN);
}

}  // namespace flower
