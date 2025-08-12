# -------------------------------------------------------------------------------------------------------------------
# Implements communications with SmartShunts on VE.Direct through the Cerbo GX.
# Note that shunts acting as a battery monitor use the com.victronenergy.battery interfaces.
# Other shunts show up as different devices depending on their use (as defined by the role).
# The ricardocello-specific chargeverter shunt show below has the com.victronenergy.dcsource interface.
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


class MainShunt(CerboGX):
    # SmartShunt Unit Id 226 (Device Id 279): Main Shunt (VE.Direct port #1)

    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=226):
        super().__init__(addr, uid=uid)

    async def dc_info(self):
        # Returns the current power, voltage, current (negative if charging), and SoC.
        #
        # /Dc/0/Power (258)
        # /Dc/0/Voltage (259)
        # /Dc/0/Current (261)
        # /Soc (266)
        try:
            result = await self.read(258, 9)
        except self.errors:
            return 0, 0, 0, 0
        watts = self.make_signed(result[0])
        volts = result[1] / 100.0
        amps = self.make_signed(result[3]) / 10.0
        soc_pct = result[8] / 10.0
        return watts, volts, amps, soc_pct

    async def power_watts(self):
        # Returns SmartShunt battery voltage
        # /Dc/0/Power (258)
        try:
            result = await self.read_int(258)
        except self.errors:
            return 0.0
        return float(result)

    async def voltage(self):
        # Returns SmartShunt battery voltage
        # /Dc/0/Voltage (259)
        try:
            result = await self.read_int(259)
        except self.errors:
            return 0.0
        return 0.01 * result

    async def current_amps(self):
        # Returns SmartShunt battery current in amps
        # /Dc/0/Current (261)
        try:
            result = await self.read_int(261)
        except self.errors:
            return 0.0
        return 0.1 * result

    async def state_of_charge(self):
        # Returns SmartShunt SoC
        # /Soc (266)
        try:
            result = await self.read_int(266)
        except self.errors:
            return 0.0
        return 0.1 * result

    async def main(self):
        # Unit Test Code: Display the voltage, current, and State of Charge

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        while True:
            v = await self.voltage()
            a = await self.current_amps()
            soc = await self.state_of_charge()

            print(f'Main Shunt: [{v:.2f} V] [{a:.1f} A] [SoC {soc:.1f} %]')
            time.sleep(1.0)


class ChargeverterShunt(CerboGX):
    # SmartShunt Unit Id 224 (Device Id 278): Chargeverter Shunt (VE.Direct port #2)
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=224):
        super().__init__(addr, uid=uid)

    async def dc_info(self):
        # Returns the current power, voltage, and current (negative if charging).
        # com.victronenergy.dcsource
        # /Dc/0/Voltage (4200)
        # /Dc/0/Current (4201)
        try:
            result = await self.read(4200, 2)
        except self.errors:
            return 0, 0, 0
        volts = result[0] / 100.0
        amps = self.make_signed(result[1]) / 10.0
        watts = volts * amps
        return watts, volts, amps


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    b = MainShunt(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(b.main())
