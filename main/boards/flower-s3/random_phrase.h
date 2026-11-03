#ifndef FLOWER_RANDOM_PHRASE_H_
#define FLOWER_RANDOM_PHRASE_H_

#include <array>
#include <cstdint>
#include <ctime>

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

// The packed asset order is common, morning, afternoon, evening. Index identity
// remains global, so excluding the last clip still works across time boundaries.
using PhraseCounts = std::array<int, 4>;

inline int PhraseCount(const PhraseCounts& counts) {
    int total = 0;
    for (int count : counts) {
        if (count < 0 || count > 64) {
            return -1;
        }
        total += count;
    }
    return total <= 64 ? total : -1;
}

inline int PhraseHour(std::time_t now) {
    // OTA already shifts this clock to local civil time. Do not add TZ again.
    return now >= 1704067200 ? static_cast<int>((now / 3600) % 24) : -1;
}

inline int RandomPhraseIndexForHour(uint32_t random, const PhraseCounts& counts, int hour,
                                    int previous) {
    if (PhraseCount(counts) < 0) {
        return -1;
    }
    const int group = hour < 0 || hour > 23 ? 0 : hour < 6 || hour >= 18 ? 3 : hour < 12 ? 1 : 2;
    int offset = 0;
    for (int i = 0; i < group; ++i) {
        offset += counts[i];
    }
    const int common = counts[0];
    const int timed = group == 0 ? 0 : counts[group];
    const int previous_in_pool = previous >= 0 && previous < common ? previous
                                 : previous >= offset && previous < offset + timed
                                     ? common + previous - offset
                                     : -1;
    const int index = RandomPhraseIndex(random, common + timed, previous_in_pool);
    return index < 0 || index < common ? index : offset + index - common;
}

}  // namespace flower
#endif  // FLOWER_RANDOM_PHRASE_H_
