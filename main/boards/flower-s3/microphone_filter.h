#ifndef FLOWER_S3_MICROPHONE_FILTER_H_
#define FLOWER_S3_MICROPHONE_FILTER_H_

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace flower {

class MicrophoneFilter {
public:
    static constexpr int kSampleRate = 16000;

    void Process(int16_t* pcm, int samples) {
        for (int i = 0; i < samples; ++i) {
            const float input = pcm[i];
            // One-pole filters at 100 Hz and 4.2 kHz reject rumble and high hiss.
            dc_ += 0.0385f * (input - dc_);
            voice_ += 0.808f * (input - dc_ - voice_);

            // A soft expander reduces low-level noise without muting quiet syllables.
            const float magnitude = std::abs(voice_);
            envelope_ += (magnitude > envelope_ ? 0.031f : 0.00078f) *
                         (magnitude - envelope_);
            const float open = std::clamp((envelope_ - 48.0f) / 112.0f, 0.0f, 1.0f);
            const float target = 0.50f + 0.50f * open;
            gain_ += (target > gain_ ? 0.031f : 0.00078f) * (target - gain_);

            // Blend in a small amount of the presence band, roughly 650–3200 Hz.
            presence_low_ += 0.225f * (voice_ - presence_low_);
            presence_high_ += 0.715f * (voice_ - presence_low_ - presence_high_);
            const float output = (voice_ + 0.34f * presence_high_) * gain_;
            pcm[i] = static_cast<int16_t>(std::clamp(output, -32768.0f, 32767.0f));
        }
    }

private:
    float dc_ = 0.0f;
    float voice_ = 0.0f;
    float envelope_ = 0.0f;
    float gain_ = 0.5f;
    float presence_low_ = 0.0f;
    float presence_high_ = 0.0f;
};

}  // namespace flower

#endif  // FLOWER_S3_MICROPHONE_FILTER_H_
