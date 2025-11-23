# -------------------------------------------------------------------------------------------------------------------
# Implements communications with a Generator through the Cerbo GX.
#
# This implementation is used for grid start/stop using the Adam DeLay method of
# using a two-wire cable from the Cerbo GX Relay #1 to the Main Quattro AUX1 relay,
# and installing the General Flag and Programmable relay assistants to ignore AC Input 1.
# The generator Grid/Stop features on the Cerbo GX are then used to manage grid power.
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


class Generator(CerboGX):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=settings_gx.GENERATOR):
        super().__init__(addr, uid=uid)

    async def manual_start(self):
        # Starts the generator (grid power)
        # /ManualStart (3500)
        await self.write_uint(3500, 1)

    async def manual_stop(self):
        # Stops the generator (grid power)
        # /ManualStart (3500)
        await self.write_uint(3500, 0)

    async def set_autostart(self, onOff):
        # Sets the autostart capability.
        # /AutoStartEnabled (3509)
        await self.write_uint(3509, 1 if onOff else 0)

    async def start_condition(self):
        # Returns the reason for starting
        # /RunningByConditionCode (3501)

        state = await self.read_uint(3501)
        if state == 0:
            return 'Stopped'
        elif state == 1:
            return 'Manual'
        elif state == 2:
            return 'Test Run'
        elif state == 3:
            return 'Loss of Comms'
        elif state == 4:
            return 'SoC'
        elif state == 5:
            return 'AC Load'
        elif state == 6:
            return 'Battery Current'
        elif state == 7:
            return 'Battery Voltage'
        elif state == 8:
            return 'Inverter Temperature'
        elif state == 9:
            return 'Inverter Overload'
        elif state == 10:
            return 'Stop On AC1'
        return f'Unknown {state}'

    async def main(self):
        # Unit test code

        r = await self.manual_start()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        time.sleep(10)
        await self.manual_stop()


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    a = Generator(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(a.main())
