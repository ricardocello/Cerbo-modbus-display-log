# -------------------------------------------------------------------------------------------------------------------
# Implements communications with Energy Meters measuring AC Loads through the Cerbo GX.
#
# This implementation is generically useful for any acload measurement device (energy meter) in the system.
# However, a specific ricardocello configuration is coded below for convenience.
# These are emulated VM-3P75CT devices, but real ones should work as well if the role is AC Load.
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


class ACLoad(CerboGX):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.ACLOAD_METER_1):
        super().__init__(addr, uid=uid)

    async def power_watts(self):
        # Returns power in watts (total, L1, L2)
        # /Ac/L1/Power (3900)
        # /Ac/L2/Power (3901)
        try:
            result = await self.read(3900, 2)
        except self.errors:
            return 0, 0, 0

        l1_power = self.make_signed(result[0])
        l2_power = self.make_signed(result[1])
        return (l1_power + l2_power), l1_power, l2_power

    async def main(self):
        # Unit test code

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        while True:
            w = await self.power_watts()
            print(f'Addition Power: [{w[0]} {w[1]} {w[2]} W]')
            time.sleep(1.0)


class AdditionEnergyMeter(ACLoad):
    # Cerbo GX Emulated VM-3P75CT 42: Addition Energy Meter
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.ACLOAD_METER_1):
        super().__init__(addr, uid=uid)


class HouseEnergyMeter(ACLoad):
    # Cerbo GX Emulated VM-3P75CT 43: House Energy Meter
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.ACLOAD_METER_2):
        super().__init__(addr, uid=uid)


class WellAndSepticMeters(ACLoad):
    # Cerbo GX Emulated VM-3P75CT 45: Well and Septic Pumps using Shelly EM-50
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.ACLOAD_METER_3):
        super().__init__(addr, uid=uid)


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    a = AdditionEnergyMeter(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(a.main())
