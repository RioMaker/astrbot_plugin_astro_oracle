"""本地预览的无大气 V 星等近似；不把地平线遮挡或显示曝光当作星等。"""

import math

SUN_SOURCE = "https://www.aoc.nrao.edu/~smyers/courses/astro01/L23.html"
MOON_SOURCE = "https://articles.adsabs.harvard.edu/pdf/1991PASP..103.1033K"


def sun_magnitude(distance_au):
    return -26.74 + 5 * math.log10(distance_au)


def moon_magnitude(phase_angle_deg, distance_km):
    """Krisciunas/Schaefer 1991 式9，附观测距离的平方反比修正。"""
    angle = abs(phase_angle_deg)
    return -12.73 + 0.026 * angle + 4e-9 * angle**4 + 5 * math.log10(distance_km / 384400)


def luminary_photometry(astrometric, sun, key):
    if key == "sun":
        return {
            "magnitude": sun_magnitude(float(astrometric.distance().au)),
            "magnitude_source": SUN_SOURCE,
            "magnitude_quality": "无大气距离模型估算",
        }
    phase = float(astrometric.phase_angle(sun).degrees)
    return {
        "magnitude": moon_magnitude(phase, float(astrometric.distance().km)),
        "magnitude_source": MOON_SOURCE,
        "magnitude_quality": "无大气相位与距离模型估算",
        "phase_angle_deg": phase,
        "illuminated_fraction": float(astrometric.fraction_illuminated(sun)),
        "model_limits": "未计地照、月面差异、食或冲日增亮；极薄月牙仅粗略外推",
    }
