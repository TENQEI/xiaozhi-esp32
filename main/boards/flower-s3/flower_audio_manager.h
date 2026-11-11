#ifndef FLOWER_AUDIO_MANAGER_H_
#define FLOWER_AUDIO_MANAGER_H_

#include <array>
#include <string_view>

namespace flower {

class FlowerAudioManager {
public:
    bool PlayClock(int index);
    bool PlayGreeting(bool morning);
    void PlayPhrase();
    std::string_view StartupSound() const;
    std::string_view WifiConfigSound() const;
    std::string_view SessionSound(bool starting);
    void CommitSessionSound(bool starting);
    bool AutomaticEnabled() const;
    bool GreetingEnabled(bool morning) const;

private:
    int previous_phrase_ = -1;
    std::array<int, 2> previous_session_{-1, -1};
    std::array<int, 2> pending_session_{-1, -1};
};

}  // namespace flower
#endif
