#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace flower {

// All transitions run on the application task. Time is monotonic microseconds.
class CountdownTimer {
public:
    enum class State { kIdle, kRunning, kRinging };
    enum class Action { kCancel, kReplace };

    static constexpr int kMaxSeconds = 3600;
    static constexpr int64_t kSecondUs = 1000000;

    State Poll(int64_t now) {
        if (state_ == State::kRunning && now >= deadline_) {
            state_ = State::kRinging;
            ClearConfirmation();
        }
        if (pending_.token && now >= pending_.expires_at)
            ClearConfirmation();
        return state_;
    }

    State GetState() const { return state_; }
    int64_t Deadline() const { return state_ == State::kRunning ? deadline_ : 0; }
    int RemainingSeconds(int64_t now) const {
        const auto remaining = Deadline() - now;
        return remaining > 0 ? static_cast<int>((remaining + kSecondUs - 1) / kSecondUs) : 0;
    }

    bool Start(int seconds, int64_t now) {
        if (Poll(now) != State::kIdle || !ValidDuration(seconds))
            return false;
        SetDeadline(seconds, now);
        return true;
    }

    uint32_t Request(Action action, int seconds, int64_t now) {
        if (Poll(now) != State::kRunning || (action == Action::kReplace && !ValidDuration(seconds)))
            return 0;
        if (pending_.token && pending_.action == action && pending_.seconds == seconds)
            return pending_.token;
        if (++last_token_ == 0)
            ++last_token_;
        pending_ = {last_token_, action, seconds, now + 30 * kSecondUs};
        return last_token_;
    }

    void ObservePrompt(std::string_view text) {
        if (!pending_.token)
            return;
        const auto phrase = pending_.action == Action::kCancel ? "确认取消" : "确认替换";
        if (text.find(phrase) != std::string_view::npos)
            pending_.prompt_seen = true;
    }

    void PromptPlayed(int64_t now) {
        Poll(now);
        if (pending_.token && pending_.prompt_seen)
            pending_.prompt_played = true;
    }

    void Recognize(std::string_view transcript, int64_t now) {
        Poll(now);
        if (!pending_.token || !pending_.prompt_played || transcript.size() > 128)
            return;
        // Match the whole transcript so phrases such as “不要确认取消” cannot approve.
        constexpr std::string_view punctuation[] = {" ",  "\t", "\r", "\n", "。", "，",
                                                    "！", "？", ".",  ",",  "!",  "?"};
        bool stripped = true;
        while (stripped && !transcript.empty()) {
            stripped = false;
            for (auto mark : punctuation) {
                if (transcript.starts_with(mark)) {
                    transcript.remove_prefix(mark.size());
                    stripped = true;
                }
                if (transcript.ends_with(mark)) {
                    transcript.remove_suffix(mark.size());
                    stripped = true;
                }
            }
        }
        pending_.approved =
            transcript == "确认" || transcript == "是" || transcript == "是的" ||
            transcript == "对" || transcript == "对的" || transcript == "好的" ||
            transcript == "好" || transcript == "可以" ||
            (pending_.action == Action::kCancel &&
             (transcript == "确认取消" || transcript == "取消吧" || transcript == "取消计时")) ||
            (pending_.action == Action::kReplace &&
             (transcript == "确认替换" || transcript == "换吧" || transcript == "重新计时吧"));
        if (!pending_.approved)
            ClearConfirmation();
    }

    bool Confirm(uint32_t token, int64_t now, Action& action) {
        if (Poll(now) != State::kRunning || !token || token != pending_.token || !pending_.approved)
            return false;
        action = pending_.action;
        const int seconds = pending_.seconds;
        ClearConfirmation();
        if (action == Action::kReplace)
            SetDeadline(seconds, now);
        else
            state_ = State::kIdle;
        return true;
    }

    void ClearConfirmation() { pending_ = {}; }

    bool Silence() {
        if (state_ != State::kRinging)
            return false;
        state_ = State::kIdle;
        return true;
    }

private:
    static bool ValidDuration(int seconds) { return seconds >= 1 && seconds <= kMaxSeconds; }

    void SetDeadline(int seconds, int64_t now) {
        deadline_ = now + seconds * kSecondUs;
        state_ = State::kRunning;
    }

    struct Confirmation {
        uint32_t token = 0;
        Action action = Action::kCancel;
        int seconds = 0;
        int64_t expires_at = 0;
        bool prompt_seen = false;
        bool prompt_played = false;
        bool approved = false;
    };

    State state_ = State::kIdle;
    int64_t deadline_ = 0;
    uint32_t last_token_ = 0;
    Confirmation pending_;
};

}  // namespace flower
