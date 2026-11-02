#ifndef FLOWER_GREETING_TIME_SETTINGS_H_
#define FLOWER_GREETING_TIME_SETTINGS_H_

#include <atomic>
#include <cstdint>

namespace flower {

struct GreetingTimes {
    int morning = 8 * 60;
    int night = 20 * 60;
};

inline bool ValidTimes(GreetingTimes times) {
    return times.morning >= 0 && times.morning < 1440 && times.night >= 0 && times.night < 1440;
}

inline uint32_t PackTimes(GreetingTimes times) {
    return (static_cast<uint32_t>(times.morning) << 16) | static_cast<uint32_t>(times.night);
}

inline GreetingTimes UnpackTimes(uint32_t packed) {
    return {static_cast<int>(packed >> 16), static_cast<int>(packed & 0xffff)};
}

// HTTP owns writes; the application task reads a single atomic snapshot.
// One NVS value persists the pair, so a failed save never applies half a change.
class GreetingTimeSettings {
public:
    GreetingTimeSettings();
    GreetingTimes Get() const;
    void SetDefaults(GreetingTimes times);
    bool Save(GreetingTimes times);

private:
    static constexpr uint32_t kUnset = UINT32_MAX;
    std::atomic<uint32_t> override_{kUnset};
    std::atomic<uint32_t> defaults_{PackTimes({})};
};

}  // namespace flower
#endif  // FLOWER_GREETING_TIME_SETTINGS_H_
