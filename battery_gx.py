# -------------------------------------------------------------------------------------------------------------------
# Implements communications with the battery rack via CANBus through the Cerbo GX.
# This code has only been specifically tested with EG4-LL v1 batteries using the Victron protocol over VE.Can.
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


class Battery(CerboGX):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS):
        super().__init__(addr, uid=settings_gx.CANBUS_BMS)

    async def degrees_c(self):
        # Returns battery internal temperature
        # /Dc/0/Temperature (262)

        try:
            result = await self.read_int(262)
        except self.errors:
            return 0.0
        return 0.1 * result

    async def voltage(self):
        # Returns BMS battery voltage
        # /Dc/0/Voltage (259)

        try:
            result = await self.read_int(259)
        except self.errors:
            return 0.0
        return 0.01 * result

    async def current_amps(self):
        # Returns BMS battery current in amps
        # /Dc/0/Current (261)

        try:
            result = await self.read_int(261)
        except self.errors:
            return 0.0
        return 0.1 * result

    async def state_of_charge(self):
        # Returns Battery SoC
        # /Soc (266)

        try:
            result = await self.read_int(266)
        except self.errors:
            return 0.0
        return 0.1 * result

    async def max_charge_current(self):
        # Returns the maximum charge current reported by the BMS
        # /Info/MaxChargeCurrent (307)

        try:
            result = await self.read_uint(307)
        except self.errors:
            return 0.0
        return 0.1 * result

    async def cell_voltages(self):
        # Returns the difference between the cell with the maximum voltage and the cell with minimum voltage,
        # and also returns the min and max cell voltages.
        # /System/MinCellVoltage (1290)
        # /System/MaxCellVoltage (1291)

        try:
            result = await self.read(1290, 2)
        except self.errors:
            return 0.0

        lo_v = 0.01 * result[0]
        hi_v = 0.01 * result[1]
        return lo_v, hi_v

    async def number_of_modules_online(self):
        # Returns the number of online EG4-LL v1 modules
        # /System/NrOfModulesOnline (1303)

        return await self.read_uint(1303)

    async def modules_blocking_charge(self):
        # Returns the number of EG4-LL v1 modules blocking charging
        # /System/NrOfModulesBlockingCharge (1304)

        return await self.read_uint(1304)

    async def modules_blocking_discharge(self):
        # Returns the number of EG4-LL modules blocking discharging
        # /System/NrOfModulesBlockingDischarge (1305)

        return await self.read_uint(1305)

    async def blocking_modules(self):
        # Returns the number of online EG4-LL v1 modules,
        # the number of modules blocking charging,
        # and the number of modules blocking discharging.
        #
        # /System/NrOfModulesOnline (1303)
        # /System/NrOfModulesBlockingCharge (1304)
        # /System/NrOfModulesBlockingDischarge (1305)

        return await self.read(1303, 3)

    async def main(self):
        # Unit Test Code

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        while True:
            v = await self.voltage()
            a = await self.current_amps()
            lo_v, hi_v = await self.cell_voltages()
            print(f'Battery: [{v:.2f} V] [{a:.1f} A] [Min Cell Voltage {lo_v:.2f} V] '
                  f'[Max Cell Voltage {hi_v:.2f} V]')
            time.sleep(1.0)


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    b = Battery(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(b.main())
