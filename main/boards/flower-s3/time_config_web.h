#ifndef FLOWER_TIME_CONFIG_WEB_H_
#define FLOWER_TIME_CONFIG_WEB_H_

#include "greeting_time_settings.h"

#include <esp_http_server.h>
#include <atomic>
#include <string>

namespace flower {

class TimeConfigWeb {
public:
    explicit TimeConfigWeb(GreetingTimeSettings& times) : times_(times) {}
    // Called by the board's network callback. Never changes application state.
    void SetConnected(bool connected);

private:
    GreetingTimeSettings& times_;
    httpd_handle_t server_ = nullptr;
    std::atomic<bool> connected_{false};
    std::string token_;

    bool Start();
    bool IsLocalRequest(httpd_req_t* request) const;
    static esp_err_t Handle(httpd_req_t* request);
    esp_err_t Serve(httpd_req_t* request);
};

}  // namespace flower
#endif  // FLOWER_TIME_CONFIG_WEB_H_
