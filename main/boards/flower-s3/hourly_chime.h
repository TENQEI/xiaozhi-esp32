#ifndef FLOWER_HOURLY_CHIME_H_
#define FLOWER_HOURLY_CHIME_H_

#include "chime_schedule.h"
#include "flower_audio_manager.h"
#include "greeting_time_settings.h"

namespace flower {

class HourlyChime {
public:
    HourlyChime(GreetingTimeSettings& times, FlowerAudioManager& audio)
        : times_(times), audio_(audio) {}
    void Tick();
    int64_t NextPhraseUs() const { return next_phrase_us_; }
    void ResetPhraseTimer() { next_phrase_us_ = 0; }

private:
    GreetingTimeSettings& times_;
    FlowerAudioManager& audio_;
    ChimeConfig config_;
    ChimeSchedule schedule_;
    int64_t next_phrase_us_ = 0;
};

}  // namespace flower
#endif  // FLOWER_HOURLY_CHIME_H_
