# -------------------------------------------------------------------------------------------------------------------
# Implements communications with the Grid Meter through the Cerbo GX.
#
# This code assumes a split-phase system, and will need modifications to support three-phase systems.
# L3 is specifically ignored everywhere in this code for convenience.
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

import settings_gx
from cerbo_gx import *


class GridMeter(CerboGX):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS):
        super().__init__(addr, uid=settings_gx.GRID_METER)

    async def power_watts(self):
        # Returns measured grid power (Total, L1, L2)
        # /Ac/L1/Power (2600)
        # /Ac/L2/Power (2601)

        try:
            result = await self.read(2600, 2)
        except self.errors:
            return 0, 0, 0

        l1 = self.make_signed(result[0])
        l2 = self.make_signed(result[1])
        return (l1+l2), l1, l2

    async def power_factor(self):
        # Returns measured grid power factor (L1, L2)
        # /Ac/L1/PowerFactor (2645)
        # /Ac/L2/PowerFactor (2646)

        try:
            result = await self.read(2645, 2)
        except self.errors:
            return 0, 0, 0

        l1 = 0.001 * self.make_signed(result[0])
        l2 = 0.001 * self.make_signed(result[1])
        return l1, l2

    async def voltage(self):
        # Returns measured grid voltage (Mean, L1, L2)
        # /Ac/L1/Voltage (2616)
        # /Ac/L2/Voltage (2618)

        try:
            result = await self.read(2616, 3)
        except self.errors:
            return 0, 0, 0

        l1_volts = 0.1 * self.make_signed(result[0])
        l2_volts = 0.1 * self.make_signed(result[2])
        return (l1_volts+l2_volts), l1_volts, l2_volts

    async def current_amps(self):
        # Returns measured grid current (Total, L1, L2)
        # /Ac/L1/Current (2617)
        # /Ac/L2/Currenr (2619)

        try:
            result = await self.read(2617, 3)
        except self.errors:
            return 0, 0, 0

        l1_amps = 0.1 * self.make_signed(result[0])
        l2_amps = 0.1 * self.make_signed(result[2])
        return (l1_amps+l2_amps), l1_amps, l2_amps

    async def frequency_hz(self):
        # Returns measured grid frequency (Hz)
        # /Ac/Frequency (2644)

        try:
            result = await self.read_uint(2644)
        except self.errors:
            return 0.0
        return result / 100.0

    async def main(self):
        # Unit Test Code: Connect and display grid meter power at 10 Hz

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        while True:
            power = (await self.power_watts())[0]
            power_factor = (await self.power_factor())
            voltage = (await self.voltage())[0]
            print(f'Grid: [{power} W] [{voltage:.2f} V] [{power_factor[0]:.3f} {power_factor[1]:.3f} PF]')
            time.sleep(0.1)


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    g = GridMeter(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(g.main())
