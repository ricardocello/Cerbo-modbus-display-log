# -------------------------------------------------------------------------------------------------------------------
# Implements a class to read/write the Cerbo GX System settings.
#
# All AC-related functions return tuples of (Total, L1, L2) wattage for convenience.
# ESS settings can be controlled here as well.
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
from cerbo_gx import *


class PowerTable:
    # Conveniently stores all the power values for grid, consumption, battery, and pv

    def __init__(self):
        self.ac_grid = (0, 0, 0)                  # (Total, L1, L2)
        self.ac_generator = (0, 0, 0)
        self.ac_consumption = (0, 0, 0)
        self.ac_input_consumption = (0, 0, 0)
        self.ac_output_consumption = (0, 0, 0)

        self.dc_battery = 0
        self.dc_pv = 0
        self.dc_charger = 0
        self.dc_system = 0
        self.ve_charge_power = 0

        self.is_charging = False
        self.quattro_ac_power = 0
        self.quattro_dc_power = 0
        self.efficiency_pct = 0.0

        self.mode = None  # Charger or Inverter

    def calculate_efficiency(self):
        # Calculates the charging or inverting efficiency based on the power values stored in the table.
        # Sets self.is_charging and self.efficiency_pct.

        # Charging or inverting (inverter can only be doing at a time)
        self.is_charging = (self.ac_grid[0] - self.ac_consumption[0]) > 0

        # Charger Efficiency
        if self.is_charging:
            self.mode = 'Charger'
            self.quattro_ac_power = self.ac_grid[0] - self.ac_consumption[0]        # to charger
            self.quattro_dc_power = self.dc_battery - self.dc_pv + self.dc_system   # from charger to battery

            try:
                self.efficiency_pct = 100.0 * self.quattro_dc_power / self.quattro_ac_power
            except ZeroDivisionError:
                self.efficiency_pct = 0.0

        # Inverter Efficiency
        else:
            self.mode = 'Inverter'
            self.quattro_dc_power = -self.dc_battery + self.dc_pv - self.dc_system   # to inverter
            self.quattro_ac_power = self.ac_consumption[0] - self.ac_grid[0]         # from inverter to loads and grid

            try:
                self.efficiency_pct = 100.0 * self.quattro_ac_power / self.quattro_dc_power
            except ZeroDivisionError:
                self.efficiency_pct = 0.0

        if self.efficiency_pct < 0.0 or self.efficiency_pct > 100.0:
            self.efficiency_pct = 0.0

    def show(self):
        # Displays the Power Table

        # ----- ANSI Colors -----
        red = '\x1b[31m'
        green = '\x1b[32m'
        yellow = '\x1b[33m'
        blue = '\x1b[34m'
        magenta = '\x1b[35m'
        normal = '\x1b[0m'
        clear_home = '\x1b[2J\x1b[H'

        def triple(pwr):
            color1 = green if pwr[0] > 0 else red
            color2 = green if pwr[1] > 0 else red
            color3 = green if pwr[2] > 0 else red
            return f'{color1}{pwr[0]:6d} W   {color2}{pwr[1]:6d} W   {color3}{pwr[2]:6d} W{normal}'

        def single(pwr):
            color = green if pwr > 0 else red
            return f'{color}{pwr:6d} W{normal}'

        def percentage(pct):
            if pct == 0.0:
                color = red
            elif pct < 80.0:
                color = magenta
            elif pct < 90.0:
                color = yellow
            else:
                color = green
            return f'{color}{pct:6.1f} %{normal}'

        batt_charging = 'Charging' if self.dc_battery > 0.0 else ''
        solar = 'Solar' if self.dc_pv > 0.0 else ''
        quattro_charging = ' Charging' if self.is_charging else 'Inverting'

        print(f'{clear_home}{blue}ESS Power Table')
        print(f'Value                   Total         L1         L2{normal}')
        print(f'AC Grid Power:         {triple(self.ac_grid)}')
        print(f'AC Generator Power:    {triple(self.ac_generator)}')
        print(f'AC Input Consumption:  {triple(self.ac_output_consumption)}')
        print(f'AC Output Consumption: {triple(self.ac_input_consumption)}')
        print(f'AC Total Consumption:  {triple(self.ac_consumption)}\n')

        print(f'DC Battery:            {single(self.dc_battery)}   {batt_charging}')
        print(f'DC PV:                 {single(self.dc_pv)}      {solar}')
        print(f'DC Charger:            {single(self.dc_charger)}')
        print(f'DC System:             {single(self.dc_system)}')
        print(f'VE.Bus Charge Power:   {single(self.ve_charge_power)}\n')

        print(f'Quattro AC Power:      {single(self.quattro_ac_power)}  {quattro_charging}')
        print(f'Quattro DC Power:      {single(self.quattro_dc_power)}')
        mode = 'Charger ' if self.is_charging else 'Inverter'
        print(f'{mode} Efficiency:   {percentage(self.efficiency_pct)}')
        print('')


class System(CerboGX):
    # System Device

    def __init__(self, addr=settings_gx.GX_IP_ADDRESS):
        super().__init__(addr)

    async def power_table(self):
        # Returns a power table object with all the current power values

        table = PowerTable()

        table.ac_grid = await self.ac_grid_watts()
        table.ac_generator = await self.ac_genset_power_watts()
        table.ac_consumption = await self.ac_consumption_watts()
        table.ac_input_consumption = await self.ac_consumption_on_input()
        table.ac_output_consumption = await self.ac_consumption_on_output()

        table.dc_battery = await self.dc_battery_power_watts()
        table.dc_pv = await self.dc_pv_power_watts()
        table.dc_charger = await self.dc_charger_watts()
        table.dc_system = await self.dc_system_watts()
        table.ve_charge_power = await self.ve_charge_power_watts()
        return table

    async def set_relay_1(self, off_on):
        # Sets relay #1 state
        # /Relay/0/State (806)
        await self.write_uint(806, 1 if off_on else 0)

    async def set_relay_2(self, off_on):
        # Sets relay #2 state
        # /Relay/1/State (807)
        await self.write_uint(807, 1 if off_on else 0)

    async def set_grid_power_setpoint_watts(self, watts):
        # Sets the ESS Grid Power Setpoint (negative to send power to grid)
        # /Settings/Cgwacs/AcPowerSetPoint (2700)
        await self.write_int(2700, int(watts))

    async def set_inverter_power_limit_watts(self, watts):
        # Sets the maximum inverter power to the loads (-1 if no linit)
        # /Settings/Cgwacs/MaxDischargePower (2704)
        await self.write_uint(2704, int(0.5 + watts/10.0))

    async def set_charge_voltage_limit(self, volts):
        # Sets the charge voltage limit for managed batteries
        # /Settings/SystemSetup/MaxChargeVoltage (2710)
        await self.write_uint(2710, int(0.5 + 10.0 * volts))

    async def set_dvcc_max_charge_current_amps(self, amps):
        # Sets the maximum DVCC charge current to batteries (-1 if no linit)
        # /Settings/SystemSetup/MaxChargeCurrent (2705)
        await self.write_int(2705, int(amps))

    async def set_max_feed_in_power_watts(self, watts):
        # Sets the grid feed-in power (-1 if no linit)
        # /Settings/Cgwacs/MaxFeedInPower (2706)
        await self.write_int(2706, int(0.5 + watts/100.0))

    async def set_feed_excess_dc_pv_into_grid(self, yes_no):
        # Feed DC PV into grid settings
        # /Settings/Cgwacs/OvervoltageFeedIn (2707)
        await self.write_uint(2707, 1 if yes_no else 0)

    async def set_ess_mode_3(self, yes_no):
        # /Settings/Cgwacs/Hub4Mode (2902)
        await self.write_uint(2902, 3 if yes_no else 1)

    async def is_ess_mode_3(self):
        # /Settings/Cgwacs/Hub4Mode (2902)
        result = await self.read_uint(2902)
        return result == 3

    async def inverter_power_limit_watts(self):
        # Gets the maximum inverter power to the loads
        # /Settings/Cgwacs/MaxDischargePower (2704)
        return 10.0 * await self.read_uint(2704)

    async def grid_limiting_status(self):
        # Returns True if power into grid is being limited
        # /Settings/SystemSetup/MaxChargeVoltage (2709)
        result = await self.read_uint(2709)
        return result == 1

    async def charge_voltage_limit(self):
        # Gets the charge voltage limit for managed batteries
        # /Settings/SystemSetup/MaxChargeVoltage (2710)
        return 0.1 * await self.read_uint(2710)

    async def ess_settings(self):
        # Read all current ESS settings at 2700
        result = await self.read(2700, 11)
        return (self.make_signed(result[0]), result[1], result[2],
                self.make_signed(result[3]), result[4],
                self.make_signed(result[5]), self.make_signed(result[6]), self.make_signed(result[7]),
                self.make_signed(result[8]), self.make_signed(result[9]), result[10])

    async def ess_settings2(self):
        # Read all current ESS settings at 2900
        return await self.read(2900, 4)

    async def relay_1_state(self):
        # Returns the current state of Relay #1
        # /Relay/0/State (806)
        try:
            result = await self.read_uint(806)
        except self.errors:
            return False
        return result != 0

    async def relay_2_state(self):
        # Returns the current state of Relay #2
        # /Relay/1/State (807)
        try:
            result = await self.read_uint(807)
        except self.errors:
            return False
        return result != 0

    async def dvcc_max_charge_current_amps(self):
        # Returns the maximum DVCC charge current to batteries (-1 if no linit)
        # /Settings/SystemSetup/MaxChargeCurrent (2705)
        try:
            result = await self.read_int(2705)
        except self.errors:
            return 0
        return result

    async def ac_grid_watts(self):
        # Returns the current total Grid Power (L1+L2)
        # /Ac/Grid/L1/Power (820)
        # /Ac/Grid/L1/Power (821)
        try:
            result = await self.read(820, 2)
        except self.errors:
            return 0, 0, 0

        l1 = self.make_signed(result[0])
        l2 = self.make_signed(result[1])
        return (l1+l2), l1, l2

    async def ac_genset_power_watts(self):
        # Returns the current total Generator Power (L1+L2)
        # /Ac/Genset/L1/Power (823)
        # /Ac/Genset/L2/Power (824)
        try:
            result = await self.read(823, 2)
        except self.errors:
            return 0, 0, 0

        l1 = self.make_signed(result[0])
        l2 = self.make_signed(result[1])
        return (l1+l2), l1, l2

    async def ac_consumption_watts(self):
        # Returns the current total AC Power Consumption (L1+L2)
        # /Ac/Consumption/L1/Power (817)
        # /Ac/Consumption/L2/Power (818)
        try:
            result = await self.read(817, 2)
        except self.errors:
            return 0, 0, 0
        return (result[0]+result[1]), result[0], result[1]

    async def ac_consumption_on_input(self):
        # Returns the current total AC consumption on the input (L1+L2)
        # /Ac/ConsumptionOnInput/L1/Power (872,873)
        # /Ac/ConsumptionOnInput/L2/Power (874,875)
        # Note: Modbus numbering is flipped with output, error in documentation
        try:
            result = await self.read(878, 4)
        except self.errors:
            return 0, 0, 0

        l1 = self.make_signed32((result[0], result[1]))
        l2 = self.make_signed32((result[2], result[3]))
        return (l1+l2), l1, l2

    async def ac_consumption_on_output(self):
        # Returns the current total AC consumption on the output (L1+L2)
        # /Ac/ConsumptionOnOutput/L1/Power (878,879)
        # /Ac/ConsumptionOnOutput/L2/Power (880,881)
        # Note: Modbus numbering is flipped with input, error in documentation
        try:
            result = await self.read(872, 4)
        except self.errors:
            return 0, 0, 0

        l1 = self.make_signed32((result[0], result[1]))
        l2 = self.make_signed32((result[2], result[3]))
        return (l1+l2), l1, l2

    async def dc_battery_power_watts(self):
        # Returns the current Battery Power (negative if charging)
        # /Dc/Battery/Power (842)
        try:
            result = await self.read_int(842)
        except self.errors:
            return 0
        return result

    async def dc_battery(self):
        # Returns the current Battery voltage, current, power (negative if charging), and SoC.
        # /Dc/Battery/Voltage (840)
        # /Dc/Battery/Current (841)
        # /Dc/Battery/Power (842)
        # /Dc/Battery/Soc (843)
        try:
            result = await self.read(840, 4)
        except self.errors:
            return 0, 0, 0, 0
        volts = result[0] / 10.0
        amps = self.make_signed(result[1]) / 10.0
        watts = self.make_signed(result[2])
        soc_pct = result[3]
        return volts, amps, watts, soc_pct

    async def dc_charger_watts(self):
        # Returns the current DC Charger Power
        # /Dc/Charger/Power (855)
        try:
            result = await self.read_uint(855)
        except self.errors:
            return 0
        return result

    async def dc_system_watts(self):
        # Returns the current DC System Power
        # /Dc/System/Power (860)
        try:
            result = await self.read_int(860)
        except self.errors:
            return 0
        return result

    async def ve_charge_power_watts(self):
        # Returns the current VE.bus Charger Power
        # /Dc/Vebus/Power (866)
        try:
            result = await self.read_int(866)
        except self.errors:
            return 0
        return result

    async def state_of_charge(self):
        # Returns the current state of charge percentage
        # /Dc/Battery/Soc (843)
        return float(await self.read_uint(843))

    async def ess_min_state_of_charge(self):
        # Returns the ESS minimum state of charge (unless grid fails)
        # /Settings/CGwacs/BatteryLife/MinimumSocLimit (2901)
        return await self.read_uint(2901) / 10.0

    async def dc_pv_power_watts(self):
        # Returns the current DC-Coupled Solar PV Power
        # /Dc/Pv/Power (850)
        try:
            result = await self.read_uint(850)
        except self.errors:
            return 0
        return result

    async def calculate_efficiency(self):
        # Calculates the current effciency of the inverter and charger.
        # Returns (mode, efficiency pct), where mode is either 'Charger' or 'Inverter'
        table = await self.power_table()
        table.calculate_efficiency()
        return table.mode, table.efficiency_pct

    async def main(self):
        # Unit test code: Show power values

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        while True:
            ac_w = await self.ac_consumption_watts()
            grid_w = await self.ac_grid_watts()
            batt_w = await self.dc_battery_power_watts()
            pv_w = await self.dc_pv_power_watts()
            charge_w = await self.ve_charge_power_watts()
            # dc_sys_w = await self.dc_system_watts()

            dc_w = batt_w - pv_w
            if charge_w < 0.0:
                efficiency = 100.0 * charge_w / dc_w
            else:
                efficiency = 100.0 * dc_w / charge_w

            print(f'System: [AC Consumption {ac_w[0]} W] [Grid {grid_w[0]} W] [Battery {batt_w} W] '
                  f'[PV {pv_w} W] [Quattro DC {dc_w} W] [Quattro AC {charge_w} W] [Efficiency {efficiency:.1f}]')
            time.sleep(1.0)


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    s = System(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(s.main())
