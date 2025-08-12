# -------------------------------------------------------------------------------------------------------------------
# Implements communications with temperature sensors through the Cerbo GX.
#
# This implementation is generically useful for any temperature sensor in the system.
# However, a specific ricardocello configuration is coded below for convenience.
#
# See https://www.victronenergy.com/upload/documents/CCGX-Modbus-TCP-register-list-3.60.xlsx
# See settings_gx.py for Modbus Unit Ids for all devices in the system.
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

import time
import asyncio

from cerbo_gx import *


class Temperature(CerboGX):
    # Cerbo GX Temperature Sensor 20: Ruuvi Tag
    # Cerbo GX Temperature Sensor 24: Chargeverter
    # Cerbo GX Temperature Sensor 25: Rack

    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.TEMPERATURE_3):
        super().__init__(addr, uid=uid)

    async def degrees_c(self):
        # Returns the temperature in degrees C
        # /Temperature (3304)

        try:
            result = await self.read_int(3304)
        except self.errors:
            return -273.0
        return 0.01 * result

    async def main(self):
        # Unit Test Code

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        while True:
            v = await self.degrees_c()
            print(f'Temperature Device/Unit Id {self.unit_id}: [{v:.2f} deg C]')
            time.sleep(1.0)


class Ruuvi(Temperature):
    # Ruuvi tag in bedroom

    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.TEMPERATURE_1):
        super().__init__(addr, uid=uid)

    async def humidity_pct(self):
        # Returns the relative humidity in %
        # /Humidity (3306)

        try:
            result = await self.read(3306, 1)
        except self.errors:
            return 0.0
        return 0.1 * result[0]

    async def barometric_pressure_hpa(self):
        # Returns the barometric pressure in hPa
        # /Pressure (3308)

        try:
            result = await self.read(3308, 1)
        except self.errors:
            return 0.0
        return float(result[0])


class ChargeverterTemperature(Temperature):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.TEMPERATURE_2):
        super().__init__(addr, uid=uid)


class RackTemperature(Temperature):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.TEMPERATURE_3):
        super().__init__(addr, uid=uid)


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    rt = RackTemperature(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(rt.main())
