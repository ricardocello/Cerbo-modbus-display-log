# -------------------------------------------------------------------------------------------------------------------
# Implements a class to keep track of statistics for a time varying quantity.
# -------------------------------------------------------------------------------------------------------------------
# Copyright 2023 ricardocello
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
# associated documentation files (the “Software”), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
# AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# -------------------------------------------------------------------------------------------------------------------

import math


class Statistics:
    def __init__(self, name=''):
        self.name = name
        self.min = math.inf
        self.max = -math.inf
        self.min_abs = math.inf
        self.max_abs = -math.inf
        self.sum = 0.0
        self.sum_abs = 0.0
        self.sum_squared = 0.0
        self.count = 0

    def next_value(self, value):
        # Adds the value to the statistics
        a = abs(value)
        s = a * a
        self.min = min(value, self.min)
        self.max = max(value, self.max)
        self.min_abs = min(a, self.min_abs)
        self.max_abs = max(a, self.max_abs)
        self.sum += value
        self.sum_abs += a
        self.sum_squared += s
        self.count += 1

    def next_stats(self, stats):
        # Combines the statistics from another object
        self.min = min(stats.min, self.min)
        self.max = max(stats.max, self.max)
        self.min_abs = min(stats.min_abs, self.min_abs)
        self.max_abs = max(stats.max_abs, self.max_abs)
        self.sum += stats.sum
        self.sum_abs += stats.sum_abs
        self.sum_squared += stats.sum_squared
        self.count += stats.count

    def clear(self):
        # Clears out all statistics
        self.min = math.inf
        self.max = -math.inf
        self.min_abs = math.inf
        self.max_abs = -math.inf
        self.sum = 0.0
        self.sum_abs = 0.0
        self.sum_squared = 0.0
        self.count = 0

    def mean(self):
        return 0.0 if self.count == 0 else self.sum / self.count

    def mean_abs(self):
        return 0.0 if self.count == 0 else self.sum_abs / self.count

    def mean_rss(self):
        return 0.0 if self.count == 0 else math.sqrt(self.sum_squared) / self.count

    def max_string(self, fmt='6.0f', units=''):
        return f'{self.max:{fmt}} {units}'

    def min_mean_max_string(self, fmt='6.0f', units=''):
        return f'[{self.min:{fmt}} {self.mean():{fmt}} {self.max:{fmt}}] {units}'

    def min_mean_max_abs_string(self, fmt='6.0f', units=''):
        return f'[{self.min_abs:{fmt}} {self.mean_abs():{fmt}} {self.max_abs:{fmt}}] {units}'
