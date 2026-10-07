"""Brightness decision with hysteresis; physical position requires a separate sensor."""
import math

class BrightnessControl:
    def __init__(self, threshold=50, hysteresis=4, bright_raises=True):
        self.configure(threshold, hysteresis, bright_raises)
        self.smoothed = None
        self.light = 'unknown'

    def configure(self, threshold, hysteresis, bright_raises):
        threshold, hysteresis = float(threshold), float(hysteresis)
        if not (math.isfinite(threshold) and math.isfinite(hysteresis)):
            raise ValueError('数値が不正です')
        if not 5 <= threshold <= 95 or not 1 <= hysteresis <= min(threshold, 100-threshold):
            raise ValueError('しきい値は5〜95%、切替幅は1%以上にしてください')
        if type(bright_raises) is not bool: raise ValueError('反転設定が不正です')
        self.threshold, self.hysteresis, self.bright_raises = threshold, hysteresis, bright_raises
        self.light = 'unknown'

    def update(self, brightness):
        value = float(brightness)
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('明るさが不正です')
        self.smoothed = value if self.smoothed is None else self.smoothed*.7 + value*.3
        if self.smoothed >= self.threshold+self.hysteresis: self.light = 'bright'
        elif self.smoothed <= self.threshold-self.hysteresis: self.light = 'dark'
        return self.decision

    @property
    def decision(self):
        if self.light == 'unknown': return 'hold'
        raises = (self.light == 'bright') == self.bright_raises
        return 'up' if raises else 'down'
