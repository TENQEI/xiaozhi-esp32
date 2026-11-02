#ifndef FLOWER_RANDOM_PHRASE_H_
#define FLOWER_RANDOM_PHRASE_H_

#include <cstdint>

namespace flower {

// Exclude the previous selection without retries; one clip necessarily repeats.
inline int RandomPhraseIndex(uint32_t random, int count, int previous) {
    if (count < 1 || count > 64) {
        return -1;
    }
    if (count == 1) {
        return 0;
    }
    if (previous < 0 || previous >= count) {
        return static_cast<int>(random % count);
    }
    const int index = static_cast<int>(random % (count - 1));
    return index >= previous ? index + 1 : index;
}

class RandomPhrasePlayer {
public:
    // Application-task only. Explicit button playback ignores automatic quiet hours.
    void Play();

private:
    bool loaded_ = false;
    int count_ = 0;
    int previous_ = -1;
    void LoadConfig();
};

}  // namespace flower
#endif  // FLOWER_RANDOM_PHRASE_H_
