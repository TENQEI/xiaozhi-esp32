#ifndef FLOWER_GREETING_TIME_SETTINGS_H_
#define FLOWER_GREETING_TIME_SETTINGS_H_

#include <mutex>
#include "greeting_schedule.h"

namespace flower {

// Device MCP owns these settings. Flash I/O never holds the snapshot mutex.
// The two schedules remain in their original NVS blob; the switch has its own key.
class GreetingTimeSettings {
public:
    GreetingTimeSettings();
    GreetingTimes Get() const;
    void SetDefaults(GreetingTimes times);
    bool Save(GreetingTimes times);
    GreetingSchedule GetSchedule() const;
    bool SaveSchedule(const GreetingSchedule& schedule);
    bool AnnouncementsEnabled() const;
    bool SaveAnnouncementsEnabled(bool enabled);

private:
    mutable std::mutex mutex_;
    GreetingSchedule schedule_;
    bool overridden_ = false;
    bool announcements_enabled_ = true;
    std::mutex announcement_write_mutex_;
};

}  // namespace flower
#endif  // FLOWER_GREETING_TIME_SETTINGS_H_
