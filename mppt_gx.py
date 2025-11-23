# -------------------------------------------------------------------------------------------------------------------
# Implements a class to talk to the SmartSolar MPPTs through the Cerbo GX device on CANbus.
#
# This implementation is very specific to the MPPTs in ricardocello configuration, namely
# a 250/70 and a 250/100 both on CANbus enumerated in that order.
# Additiona and modifications will need to be made for other MPPT configurations.
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


class SmartSolarMPPT(CerboGX):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, unit_id=settings_gx.VECAN_MPPT_1):
        self.UNIT_ID = unit_id
        super().__init__(addr, uid=unit_id)

        self.dc = None
        self.mode = 'None'
        self.efficiency_pct = 0.0

    async def read_pv_dc_values(self):
        # Reads the PV and DC power, voltage, and current and returns them
        # as nested tuples: (pv_w, pv_v, pv_a), (dc_w, dc_v, dc_a)
        # Also computes the PV efficiency and stores it internally.

        try:
            result = await self.read(771, 7)
        except self.errors:
            return 0, 0, 0

        dc_volts = result[0] / 100.0
        dc_amps = self.make_signed(result[1]) / 10.0

        pv_volts = result[5] / 100.0
        pv_amps = self.make_signed(result[6]) / 10.0

        self.dc = ((pv_volts * pv_amps), pv_volts, pv_amps), ((dc_volts * dc_amps), dc_volts, dc_amps)
        self.mode = await self.get_mppt_mode()

        (pv_w, pv_v, pv_a), (dc_w, dc_v, dc_a) = self.dc

        if pv_w > 5.0:
            self.efficiency_pct = 100.0 * dc_w / pv_w
        else:
            self.efficiency_pct = 0.0

        self.efficiency_pct = min(100.0, self.efficiency_pct)

        return self.dc

    async def dc_power_watts(self):
        # Returns the DC (battery) power in watts, volts, amps
        # /Dc/0/Voltage (771)
        # /Dc/0/Current (772)

        try:
            result = await self.read(771, 2)
        except self.errors:
            return 0, 0, 0

        volts = result[0] / 100.0
        amps = self.make_signed(result[1]) / 10.0
        return (volts * amps), volts, amps

    async def pv_power_watts(self):
        # Returns the DC (battery) power in watts, volts, amps
        # /Pv/V (776)
        # /Pv/A (777)

        try:
            result = await self.read(776, 2)
        except self.errors:
            return 0, 0, 0

        volts = result[0] / 100.0
        amps = self.make_signed(result[1]) / 10.0
        return (volts * amps), volts, amps

    async def set_charger_off_on(self, off_on):
        # Enables or disables the charger.
        # /Mode (774)

        await self.write_int(774, 1 if off_on else 4)

    async def get_charger_off_on(self):
        # Gets the state of the charger, returning True if enabled.
        # /Mode (774)

        v = await self.read_uint(774)
        return v == 1

    async def yield_today_kwh(self):
        # Returns the yield in kWh for today
        # /History/Daily/0/Yield (784)

        try:
            result = await self.read_uint(784)
        except self.errors:
            return 0

        return result / 10.0

    async def get_mppt_mode(self):
        # Gets the mode of the MPPT as a string.
        # /MppOperationMode (791)

        v = await self.read_uint(791)
        if v == 0:
            return 'Off'
        elif v == 1:
            return 'Limited'
        elif v == 2:
            return 'Active'
        elif v == 255:
            return 'Not Available'
        else:
            return 'Unknown'


class AllMPPT:
    # This class manages all the MPPTs as a group for a specific configuration.

    # ----- ANSI Colors -----
    RED = '\x1b[31m'
    GREEN = '\x1b[32m'
    BLUE = '\x1b[34m'
    NORM = '\x1b[0m'
    HOME = '\x1b[H'
    CLEAR = '\x1b[2J'

    def __init__(self, addr=settings_gx.GX_IP_ADDRESS,
                 unit_id_list=((0, 'SmartSolar 250/70 '), (1, 'SmartSolar 250/100'))):
        # Create MPPT objects
        self.mppt = []
        for u in unit_id_list:
            mp = SmartSolarMPPT(addr=addr, unit_id=u[0])
            self.mppt.append((u[0], u[1], mp))  # tuple: index, name, object

    async def connect(self):
        # Connect to the Cerbo GX
        for m in self.mppt:
            r = await m[2].connect()
            if r:
                print(f'# Unable to connect to Cerbo GX')
                return 1
        return 0

    async def disconnect(self):
        # Disconnects from the Cerbo GX
        for m in self.mppt:
            await m[2].disconnect()
        return 0

    def smartsolar(self, index):
        return self.mppt[index][2]

    async def get_mppt_modes(self):
        r = []
        for m in self.mppt:
            r.append(await m[2].get_mppt_mode())
        return r

    async def total_dc_power(self):
        total_w = 0.0
        for m in self.mppt:
            w, v, a = await m[2].dc_power_watts()
            total_w += w
        return total_w

    async def total_dc_current(self):
        total_a = 0.0
        for m in self.mppt:
            w, v, a = await m[2].dc_power_watts()
            total_a += a
        return total_a
    async def read_pv_dc_values(self):
        # Gets the PV and DC values from all the MPPTs.
        pv_w = [0.0]              # (total, 250/70 W, 250/100 W)
        pv_v = []                 # (250/70 V, 250/100 V)
        pv_a = []                 # (250/70 A, 250/100 A)
        dc_w = [0.0]              # (total, 250/70 W, 250/100 W)
        dc_v = []                 # (250/70 V, 250/100 V)
        dc_a = [0.0]              # (total, 250/70 A, 250/100 A)
        pv_yield_today = [0.0]    # (total, 250/70 kWh, 250/100 kWh)
        eff = [0.0]               # (total, 250/70 %, 250/100 %)

        for m in self.mppt:
            ((a_pv_w, a_pv_v, a_pv_a), (a_dc_w, a_dc_v, a_dc_a)) = await m[2].read_pv_dc_values()
            pv_w.append(a_pv_w)
            pv_w[0] += a_pv_w
            pv_v.append(a_pv_v)
            pv_a.append(a_pv_a)
            dc_w.append(a_dc_w)
            dc_w[0] += a_dc_w
            dc_v.append(a_dc_v)
            dc_a.append(a_dc_a)
            dc_a[0] += a_dc_a

            pv_yield = await m[2].yield_today_kwh()
            pv_yield_today.append(pv_yield)
            pv_yield_today[0] += pv_yield

            a_eff = m[2].efficiency_pct
            eff.append(a_eff)

        if pv_w[0] > 5.0:
            eff[0] = 100.0 * dc_w[0] / pv_w[0]
        else:
            eff[0] = 0.0

        eff[0] = min(100.0, eff[0])
        return pv_w, pv_v, pv_a, dc_w, dc_v, dc_a, pv_yield_today, eff

    async def show_status(self, in_place=True):
        if in_place:
            print(f'{self.HOME}{self.GREEN}Name                 Mode           Eff%    '
                  f'PV W    PV V     PV A     DC W    DC V    DC A{self.NORM}')

        pv_w, pv_v, pv_a, dc_w, dc_v, dc_a, pv_yield_today, eff = await self.read_pv_dc_values()

        for m in self.mppt:
            index = m[0]
            mp = m[2]
            if in_place:
                print(f'{m[1]:20} {mp.mode:10} {mp.efficiency_pct:7.1f}% '
                      f'{pv_w[index+1]:7.1f} {pv_v[index]:7.2f} {pv_a[index]:7.1f}'
                      f'   {dc_w[index+1]:7.1f} {dc_v[index]:7.2f} {dc_a[index+1]:7.1f}')
            else:
                print(f'[{m[1]}: {pv_w[index+1]:.1f} PV W | Eff {mp.efficiency_pct:.1f}% | Mode {mp.mode}]')

        if in_place:
            print(f'{self.GREEN}Total                           {eff[0]:7.1f}%  '
                  f'{pv_w[0]:6.1f}                   '
                  f'{dc_w[0]:7.1f}         {dc_a[0]:7.1f}{self.NORM}')
        else:
            print(f'[DC Output: {dc_w[0]:.1f} W | {dc_a[0]:.1f} A]\n')

    async def main(self):
        # Unit Test Code: Show status display
        if await self.connect():
            return

        in_place = True
        while True:
            if in_place:
                print(f'{self.CLEAR}')

            await self.show_status(in_place)
            time.sleep(1.0)


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    all_mppt = AllMPPT(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(all_mppt.main())
