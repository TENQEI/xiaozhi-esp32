#ifndef FLOWER_HOURLY_CHIME_H_
#define FLOWER_HOURLY_CHIME_H_

#include "chime_schedule.h"
#include "greeting_time_settings.h"

namespace flower {

class HourlyChime {
public:
    explicit HourlyChime(GreetingTimeSettings& times) : times_(times) {}
    void Tick();

private:
    GreetingTimeSettings& times_;
    bool loaded_ = false;
    ChimeConfig config_;
    ChimeSchedule schedule_;
    void LoadConfig();
    bool Play(int index);
};

}  // namespace flower
#endif  // FLOWER_HOURLY_CHIME_H_
