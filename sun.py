# -------------------------------------------------------------------------------------------------------------------
# Implements a class to determine ssunrise and sunset times.
#
# Based on the algorithm found here:
# https://edwilliams.org/sunrise_sunset_algorithm.htm
# https://web.archive.org/web/20161202180207/http://williams.best.vwh.net/sunrise_sunset_algorithm.htm
# -------------------------------------------------------------------------------------------------------------------
import math
from datetime import datetime
from zoneinfo import ZoneInfo


class Sun:
    def __init__(self):
        self.latitude = 38.297138    # arbitrary funeral home coordinates
        self.longitude = -77.483956
        self.tz = ZoneInfo('US/Eastern')

        self.current_date = datetime.now(self.tz)
        self.dst_active = self.current_date.dst().total_seconds() != 0

    def set_lat_long(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude

    def set_date(self, day, month, year):
        self.current_date = datetime(day=day, month=month, year=year)
        localized_dt = self.current_date.replace(tzinfo=self.tz)
        self.dst_active = localized_dt.dst().total_seconds() != 0

    def sunrise_time(self):
        return self.calc_sun_time(sunrise=True)

    def sunset_time(self):
        return self.calc_sun_time(sunrise=False)

    def calc_sun_time(self, sunrise=True, zenith=90.8):
        # Returns the sunrise or sunset time in hour and minute in local time,
        # adjusting for Daylight Saving Time

        to_rad = math.pi / 180
        to_deg = 180 / math.pi

        # Calculate the day of the year
        n1 = math.floor(275 * self.current_date.month / 9)
        n2 = math.floor((self.current_date.month + 9) / 12)
        n3 = (1 + math.floor((self.current_date.year - 4 * math.floor(self.current_date.year / 4) + 2) / 3))
        n = n1 - (n2 * n3) + self.current_date.day - 30

        # Convert the longitude to hour value and calculate an approximate time
        lng_hour = self.longitude / 15
        if sunrise:
            approx_t = n + ((6 - lng_hour) / 24)
        else:  # sunset
            approx_t = n + ((18 - lng_hour) / 24)

        # Calculate the Sun's mean anomaly
        m = (0.9856 * approx_t) - 3.289

        # Calculate the Sun's true longitude
        tl = m + (1.916 * math.sin(to_rad * m)) + (0.020 * math.sin(to_rad * 2 * m)) + 282.634
        tl = self.force_range(tl, 360)  # NOTE: L adjusted into the range [0,360)

        # Calculate the Sun's right ascension
        ra = to_deg * math.atan(0.91764 * math.tan(to_rad * tl))
        ra = self.force_range(ra, 360)  # NOTE: RA adjusted into the range [0,360)

        # Right ascension value needs to be in the same quadrant as L
        l_quadrant = math.floor(tl / 90) * 90
        ra_quadrant = math.floor(ra / 90) * 90
        ra += (l_quadrant - ra_quadrant)

        # Right ascension value needs to be converted into hours
        ra /= 15

        # Calculate the Sun's declination
        sin_dec = 0.39782 * math.sin(to_rad * tl)
        cos_dec = math.cos(math.asin(sin_dec))

        # Calculate the Sun's local hour angle
        cos_h = (math.cos(to_rad * zenith) - (sin_dec * math.sin(to_rad * self.latitude))) / \
                (cos_dec * math.cos(to_rad * self.latitude))

        # If the sun never rises on this location (on the specified date)
        if cos_h > 1:
            return None

        # If the sun never sets on this location (on the specified date)
        if cos_h < -1:
            return None

        # Finish calculating H and convert into hours
        if sunrise:
            h = 360 - to_deg * math.acos(cos_h)
        else:  # setting
            h = to_deg * math.acos(cos_h)
        h /= 15

        # Calculate local mean time of rising/setting
        t = h + ra - (0.06571 * approx_t) - 6.622
        t = self.force_range(t, 24)
        if self.dst_active:
            t += 1

        # Return hour and minute
        hr = self.force_range(int(t), 24)
        minute = int(round((t - int(t)) * 60, 0))
        return hr, minute

    @staticmethod
    def force_range(v, maxv):
        if v < 0:
            return v + maxv
        elif v >= maxv:
            return v - maxv
        return v


if __name__ == "__main__":
    # Execute main() if this file is executed directly

    sun = Sun()
    sunrise_h, sunrise_m = sun.sunrise_time()
    sunset_h, sunset_m = sun.sunset_time()

    print(f'Sunrise {sunrise_h:02}:{sunrise_m:02}')
    print(f'Sunset {sunset_h:02}:{sunset_m:02}')

    tz = ZoneInfo('US/Eastern')
    today = datetime.now(tz)
    print(today)
