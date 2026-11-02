#ifndef FLOWER_GREETING_TIME_SETTINGS_H_
#define FLOWER_GREETING_TIME_SETTINGS_H_

#include <mutex>
#include "greeting_schedule.h"

namespace flower {

// HTTP owns writes. The mutex protects only a small in-memory copy; flash I/O
// never holds it. One NVS blob commits both schedules together.
class GreetingTimeSettings {
public:
    GreetingTimeSettings();
    GreetingTimes Get() const;
    void SetDefaults(GreetingTimes times);
    bool Save(GreetingTimes times);
    GreetingSchedule GetSchedule() const;
    bool SaveSchedule(const GreetingSchedule& schedule);

private:
    mutable std::mutex mutex_;
    GreetingSchedule schedule_;
    bool overridden_ = false;
};

}  // namespace flower
#endif  // FLOWER_GREETING_TIME_SETTINGS_H_
