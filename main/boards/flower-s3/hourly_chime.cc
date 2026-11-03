#include "hourly_chime.h"
#include "application.h"

namespace flower {

void HourlyChime::Tick() {
    auto& app = Application::GetInstance();
    const auto now = std::time(nullptr);
    const auto times = TimesForDate(times_.GetSchedule(), now);
    config_ = {12,
               audio_.AutomaticEnabled() && times_.AnnouncementsEnabled(),
               times.night / 60,
               times.morning / 60,
               audio_.GreetingEnabled(true),
               audio_.GreetingEnabled(false),
               times.night % 60,
               times.morning % 60};
    const int index = schedule_.Poll(now, config_, app.GetDeviceState() == kDeviceStateIdle);
    if (index >= 0) {
        audio_.PlayClock(index);
    } else if (index == ChimeSchedule::kGoodMorning || index == ChimeSchedule::kGoodNight) {
        audio_.PlayGreeting(index == ChimeSchedule::kGoodMorning);
    }
}

}  // namespace flower
