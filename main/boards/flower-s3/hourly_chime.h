#ifndef FLOWER_HOURLY_CHIME_H_
#define FLOWER_HOURLY_CHIME_H_

#include "chime_schedule.h"

namespace flower {

class HourlyChime {
public:
    void Tick();

private:
    bool loaded_ = false;
    ChimeConfig config_;
    ChimeSchedule schedule_;
    void LoadConfig();
    bool Play(int index);
};

}  // namespace flower
#endif  // FLOWER_HOURLY_CHIME_H_
