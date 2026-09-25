// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <algorithm>
#include <cmath>

// Visual angular speed, deliberately NOT the fan's literal mechanical RPM.
inline double VisualSpeed(bool ready, unsigned percent, bool rpmValid, unsigned rpm) {
    if (!ready || percent == 0) return 0;
    if (rpmValid) return rpm == 0 ? 0 : std::clamp(rpm * 0.035, 54.0, 288.0);
    return 72.0 + (std::clamp(percent, 30u, 100u) - 30u) * 2.4;
}
struct Rotor {
    double angle = 0, velocity = 0;
    void Step(double seconds, double target) {
        if (!std::isfinite(seconds) || !std::isfinite(target) || seconds <= 0 || target < 0) return;
        // Exact integration of exponential acceleration: independent of frame rate.
        constexpr double response = 5.0;
        double decay = std::exp(-response * seconds);
        angle = std::fmod(angle + target * seconds + (velocity - target) * (1 - decay) / response, 360.0);
        if (angle < 0) angle += 360.0;
        velocity = target + (velocity - target) * decay;
    }
    void Stop() { velocity = 0; } // Preserve orientation; never snap back to zero degrees.
};
inline bool TestAnimation() {
    if (VisualSpeed(false,100,false,0) != 0 || VisualSpeed(true,0,false,0) != 0 ||
        VisualSpeed(true,80,true,0) != 0 || VisualSpeed(true,30,false,0) != 72 ||
        VisualSpeed(true,100,false,0) != 240 || VisualSpeed(true,300,false,0) != 240) return false;
    Rotor a,b;
    for (int i=0;i<180;++i) a.Step(1.0/60,240);
    for (int i=0;i<90;++i) b.Step(1.0/30,240);
    if (std::abs(a.angle-b.angle)>1e-7 || std::abs(a.velocity-b.velocity)>1e-7) return false;
    double before=a.angle; a.Stop();
    if (a.angle != before || a.velocity != 0) return false;
    a.Step(1.0/60,72);
    if (!(a.velocity>0 && a.velocity<72)) return false;
    before=a.angle; a.Step(-1,100);
    return a.angle==before;
}
