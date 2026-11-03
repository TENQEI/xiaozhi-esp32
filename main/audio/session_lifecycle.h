#pragma once

// A conversation spans multiple Listening/Speaking turns. Only a locally
// requested normal close earns an end cue; an unexplained disconnect does not.
class SessionLifecycle {
public:
    bool Begin() {
        if (active_)
            return false;
        active_ = true;
        return true;
    }
    void RequestEnd() { closing_ = active_; }
    bool IsClosing() const { return closing_; }
    bool Closed() {
        const bool normal = active_ && closing_;
        Cancel();
        return normal;
    }
    void Cancel() { active_ = closing_ = false; }

private:
    bool active_ = false;
    bool closing_ = false;
};
