# -------------------------------------------------------------------------------------------------------------------
# Implements a class to talk to Split-Phase Victron Quattros or Multiplus Inverters
# over the VE.Bus through the Cerbo GX device.
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


class Quattros(CerboGX):
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS):
        super().__init__(addr, uid=settings_gx.VEBUS_INVERTERS)

    async def set_mode_3_power_setpoint(self, l1_watts, l2_watts):
        # Sets the power level at AC Input (negative values feed-in power)
        # /Hub4/L1/AcPowerSetpoint (37)
        # /Hub4/L2/AcPowerSetpoint (40)

        await self.write_int(37, int(l1_watts))
        await self.write_int(40, int(l2_watts))

    async def enable_charger(self, yes_no):
        # Enables or disables the battery charger
        # /Hub4/DisableCharge (38)

        await self.write_uint(38, 0 if yes_no else 1)

    async def enable_inverter(self, yes_no):
        # Enables or disables inverter power
        # /Hub4/DisableFeedIn (39)

        await self.write_uint(39, 0 if yes_no else 1)

    async def set_idle_mode(self):
        # Sets idle mode (no charger, no feed-in)
        # /Hub4/DisableCharge (38)
        # /Hub4/DisableFeedIn (39)

        await self.write_uint(38, 1)
        await self.write_uint(39, 1)

    async def set_pv_feed_in(self, yes_no):
        # Enables or disables PV power feed-in
        # /Hub4/DoNotFeedInOvervoltage (65)

        await self.write_uint(65, 0 if yes_no else 1)

    async def set_pv_feed_in_limit(self, l1_watts, l2_watts):
        # Sets the limit on PV feed-in power (use large number for no limit)
        # /Hub4/L1/MaxFeedInPower (66)
        # /Hub4/L2/MaxFeedInPower (67)

        await self.write_int(66, int(l1_watts))
        await self.write_int(67, int(l2_watts))

    async def set_setpoints_as_limit(self, yes_no):
        # Enables or disables input power setpoints as limits
        # /Hub4/TargetPowerIsMaxFeedIn (71)

        await self.write_uint(71, 0 if yes_no else 1)

    async def output_freq_hz(self):
        # Returns the output power frequency (Hz)
        # /Ac/Out/L1/F (21)

        try:
            result = await self.read_uint(21)
        except self.errors:
            return 0.0
        return result / 100.0

    async def ess_power_setpoint(self):
        # Gets the power level at AC Input (negative values feed-in power)
        # /Hub4/L1/AcPowerSetpoint (37)
        # /Hub4/L2/AcPowerSetpoint (40)

        try:
            result = await self.read(37, 4)
        except self.errors:
            return 0, 0, 0

        l1 = self.make_signed(result[0])
        l2 = self.make_signed(result[3])
        return (l1+l2), l1, l2

    async def all_out_power(self):
        # Returns the Quattro output power (Total, L1, L2)
        # /Ac/Out/L1/P (23)
        # /Ac/Out/L2/P (24)
        # /Ac/ActiveIn/L1/V (15) * /Ac/ActiveIn/L1/A (18)
        # /Ac/ActiveIn/L2/V (16) * /Ac/ActiveIn/L2/A (19)

        try:
            base = 15
            result = await self.read(base, 10)
        except self.errors:
            return (0, 0, 0), (0, 0, 0)

        out_w_l1 = 10 * self.make_signed(result[23-base])
        out_w_l2 = 10 * self.make_signed(result[24-base])
        out_va_l1 = int(0.1 * result[15-base] * 0.1 * self.make_signed(result[18-base]))
        out_va_l2 = int(0.1 * result[16-base] * 0.1 * self.make_signed(result[19-base]))

        return (out_w_l1 + out_w_l2, out_w_l1, out_w_l2), (out_va_l1 + out_va_l2, out_va_l1, out_va_l2)

    async def input_power_factor(self):
        # Returns the Quattro input power factor (Total, L1, L2)
        # Registers 3, 4, 6, 7, 12, 13

        try:
            base = 3
            result = await self.read(base, 11)
        except self.errors:
            return 0, 0, 0

        in_v_l1 = 0.1 * result[3-base]
        in_v_l2 = 0.1 * result[4-base]
        in_a_l1 = 0.1 * self.make_signed(result[6-base])
        in_a_l2 = 0.1 * self.make_signed(result[7-base])
        in_w_l1 = 10 * self.make_signed(result[12-base])
        in_w_l2 = 10 * self.make_signed(result[13-base])
        in_va_l1 = in_v_l1 * in_a_l1
        in_va_l2 = in_v_l2 * in_a_l2

        try:
            in_pf_l1 = in_w_l1 / in_va_l1
        except ZeroDivisionError:
            in_pf_l1 = 0
        try:
            in_pf_l2 = in_w_l2 / in_va_l2
        except ZeroDivisionError:
            in_pf_l2 = 0
        try:
            in_pf = (in_w_l1 + in_w_l2) / (in_va_l1 + in_va_l2)
        except ZeroDivisionError:
            in_pf = 0

        in_pf_l1 = min(1.0, in_pf_l1)
        in_pf_l1 = max(-1.0, in_pf_l1)
        in_pf_l2 = min(1.0, in_pf_l2)
        in_pf_l2 = max(-1.0, in_pf_l2)
        in_pf = min(1.0, in_pf)
        in_pf = max(-1.0, in_pf)

        return in_pf, in_pf_l1, in_pf_l2

    async def output_power_factor(self):
        # Returns the Quattro output power factor (Total, L1, L2)
        # Registers 15, 16, 18, 19, 23, 24
        try:
            base = 15
            result = await self.read(base, 10)
        except self.errors:
            return 0, 0, 0

        out_v_l1 = 0.1 * result[15-base]
        out_v_l2 = 0.1 * result[16-base]
        out_a_l1 = 0.1 * self.make_signed(result[18-base])
        out_a_l2 = 0.1 * self.make_signed(result[19-base])
        out_w_l1 = 10 * self.make_signed(result[23-base])
        out_w_l2 = 10 * self.make_signed(result[24-base])
        out_va_l1 = out_v_l1 * out_a_l1
        out_va_l2 = out_v_l2 * out_a_l2

        try:
            out_pf_l1 = out_w_l1 / out_va_l1
        except ZeroDivisionError:
            out_pf_l1 = 0
        try:
            out_pf_l2 = out_w_l2 / out_va_l2
        except ZeroDivisionError:
            out_pf_l2 = 0
        try:
            out_pf = (out_w_l1 + out_w_l2) / (out_va_l1 + out_va_l2)
        except ZeroDivisionError:
            out_pf = 0

        out_pf_l1 = min(1.0, out_pf_l1)
        out_pf_l1 = max(-1.0, out_pf_l1)
        out_pf_l2 = min(1.0, out_pf_l2)
        out_pf_l2 = max(-1.0, out_pf_l2)
        out_pf = min(1.0, out_pf)
        out_pf = max(-1.0, out_pf)

        return out_pf, out_pf_l1, out_pf_l2

    async def input_power_watts(self):
        # Returns the Quattro input power (Total, L1, L2)
        # /Ac/ActiveIn/L1/P (12)
        # /Ac/ActiveIn/L2/P (13)

        try:
            result = await self.read(12, 2)
        except self.errors:
            return 0, 0, 0

        l1 = 10 * self.make_signed(result[0])
        l2 = 10 * self.make_signed(result[1])
        return (l1+l2), l1, l2

    async def input_power_va(self):
        # Returns the Quattro input apparent power (Total, L1, L2)
        # /Ac/ActiveIn/L1/V (3) * /Ac/ActiveIn/L1/A (6)
        # /Ac/ActiveIn/L2/V (4) * /Ac/ActiveIn/L2/A (7)

        try:
            volts = await self.read(3, 2)
            amps = await self.read(6, 2)
        except self.errors:
            return 0, 0, 0

        l1 = int(0.1 * volts[0] * 0.1 * self.make_signed(amps[0]))
        l2 = int(0.1 * volts[1] * 0.1 * self.make_signed(amps[1]))
        return (l1+l2), l1, l2

    async def output_power_watts(self):
        # Returns the Quattro output power (Total, L1, L2)
        # /Ac/Out/L1/P (23)
        # /Ac/Out/L2/P (24)

        try:
            result = await self.read(23, 2)
        except self.errors:
            return 0, 0, 0

        l1 = 10 * self.make_signed(result[0])
        l2 = 10 * self.make_signed(result[1])
        return (l1+l2), l1, l2

    async def output_power_va(self):
        # Returns the Quattro output apparent power (Total, L1, L2)
        # /Ac/ActiveIn/L1/V (15) * /Ac/ActiveIn/L1/A (18)
        # /Ac/ActiveIn/L2/V (16) * /Ac/ActiveIn/L2/A (19)

        try:
            volts = await self.read(15, 2)
            amps = await self.read(18, 2)
        except self.errors:
            return 0, 0, 0

        l1 = int(0.1 * volts[0] * 0.1 * self.make_signed(amps[0]))
        l2 = int(0.1 * volts[1] * 0.1 * self.make_signed(amps[1]))
        return (l1+l2), l1, l2

    async def ess_power_setpoints(self):
        # Returns the Quattro power setpoints (Total, L1, L2)
        # /Hub4/L1/AcPowerSetpoint (37)
        # /Hub4/L2/AcPowerSetpoint (40)

        try:
            result = await self.read(37, 4)
        except self.errors:
            return 0, 0, 0

        l1 = self.make_signed(result[0])
        l2 = self.make_signed(result[3])
        return (l1+l2), l1, l2

    async def state_string(self):
        # Returns the current inverter VE.bus state as a string
        # /State (31)

        state = await self.read_uint(31)
        if state == 0:
            return 'Off'
        elif state == 1:
            return 'Low Power'
        elif state == 2:
            return 'Fault'
        elif state == 3:
            return 'Bulk'
        elif state == 4:
            return 'Absorption'
        elif state == 5:
            return 'Float'
        elif state == 6:
            return 'Storage'
        elif state == 7:
            return 'Equalize'
        elif state == 8:
            return 'Passthru'
        elif state == 9:
            return 'Inverting'
        elif state == 10:
            return 'Power Assist'
        elif state == 11:
            return 'Power Supply'
        elif state == 244:
            return 'Sustain'
        elif state == 252:
            return 'External Control'
        return f'Unknown {state}'

    async def is_feed_in_enabled(self):
        # Returns inverter power feed-in setting
        # /Hub4/DisableFeedIn (39)

        result = await self.read_uint(39)
        return result == 0

    async def is_pv_feed_in_enabled(self):
        # Returns PV power feed-in setting
        # /Hub4/DoNotFeedInOvervoltage (65)

        result = await self.read_uint(65)
        return result == 0

    async def max_feed_in_watts(self):
        # Returns maximum feed-in power (Total, L1, L2)
        # /Hub4/L1/MaxFeedInPower (66), /Hub4/L2/MaxFeedInPower (67)

        try:
            result = await self.read(66, 2)
        except self.errors:
            return 0, 0, 0

        l1 = 100 * result[0]
        l2 = 100 * result[1]
        return (l1+l2), l1, l2

    async def is_charging_enabled(self):
        # Returns battery charger setting
        # /Hub4/DisableCharge (38)

        result = await self.read_uint(38)
        return result == 0

    async def are_setpoints_limits(self):
        # Retuns the setpoints as limit setting
        # /Hub4/TargetPowerIsMaxFeedIn (71)

        result = await self.read_uint(71)
        return result == 1

    async def ripple_volts(self):
        # Returns the ripple voltage for both Quattros (L1, L2)
        # /Devices/0/Diagnostics/UBatRipple (120 non-standard register address)
        # /Devices/1/Diagnostics/UBatRipple (122 non-standard register address)
        #
        # NOTE: These are custom non-standard definitions defined in
        #    /opt/victronenergy/dbus-modbustcp/attributes.csv
        #
        # com.victronenergy.vebus,/Devices/0/Diagnostics/UBatRipple,u,V DC,120,uint32,100,R
        # com.victronenergy.vebus,/Devices/1/Diagnostics/UBatRipple,u,V DC,122,uint32,100,R
        #
        # This function will always return zero if the custom attributes are not present.

        try:
            result = await self.read(120, 4)
        except self.errors:
            return 0, 0

        l1 = 0.01 * self.make_signed32((result[0], result[1]))
        l2 = 0.01 * self.make_signed32((result[2], result[3]))
        return l1, l2

    async def active_warnings_alarms(self):
        # Returns a list of active warnings and alarms
        # /Alarms/HighTemperature (34)
        # /Alarms/LowBattery (35)
        # /Alarms/Overload (36)
        # Registers (42-51), 64, 94

        try:
            result = ''
            high_temp, low_battery, overload = await self.read(34, 3)
            temp_sensor, volt_sensor, \
                temp_l1, low_battery_l1, overload_l1, ripple_l1, \
                temp_l2, low_battery_l2, overload_l2, ripple_l2 = await self.read(42, 10)
            grid_lost = await self.read_uint(64)
            low_voltage = await self.read_uint(94)

            result += self.warning_alarm_string(high_temp, '|High Temperature')
            result += self.warning_alarm_string(low_battery, '|Low Battery')
            result += self.warning_alarm_string(overload, '|Overload')
            result += self.warning_alarm_string(temp_sensor, '|Temperature Sensor')
            result += self.warning_alarm_string(volt_sensor, '|Voltage Sensor')

            result += self.warning_alarm_string(temp_l1, '|L1 Temperature')
            result += self.warning_alarm_string(low_battery_l1, '|L1 Low Battery')
            result += self.warning_alarm_string(overload_l1, '|L1 Overload')
            result += self.warning_alarm_string(ripple_l1, '|L1 Ripple')

            result += self.warning_alarm_string(temp_l2, '|L2 Temperature')
            result += self.warning_alarm_string(low_battery_l2, '|L2 Low Battery')
            result += self.warning_alarm_string(overload_l2, '|L2 Overload')
            result += self.warning_alarm_string(ripple_l2, '|L2 Ripple')

            result += self.warning_alarm_string(grid_lost, '|Grid Lost')
            result += self.warning_alarm_string(low_voltage, '|Low Voltage')

            return result if result else 'None'

        except self.errors:
            return ''

    @staticmethod
    def warning_alarm_string(value, name):
        if value == 0:
            return ''
        elif value == 1:
            return name
        else:
            return name.upper()

    async def main(self):
        # Unit Test Code: Gather info from the Quattros and display it

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        while True:
            in_w = await q.input_power_watts()
            in_va = await q.input_power_va()
            out_w = await q.output_power_watts()
            out_va = await q.output_power_va()
            setpoints = await q.ess_power_setpoints()
            ripple = await self.ripple_volts()

            if in_va[0] < 10.0:
                in_pf = 0.0
            else:
                in_pf = in_w[0] / in_va[0]

            if out_va[0] < 10.0:
                out_pf = 0.0
            else:
                out_pf = out_w[0] / out_va[0]

            print(f'Quattros: [Input {in_w[0]} W  {in_va[0]} VA  {in_pf:.2f} PF]'
                  f' [Output {out_w[0]} W   {out_va[0]} VA  {out_pf:.2f} PF]'
                  f' [ESS Setpoint {setpoints[0]} W]'
                  f' [Ripple {ripple[0]:.2f} {ripple[1]:.2f} V]')
            time.sleep(1.0)

    async def main_test(self):
        # Unit Test Code: Gather info from the Quattros and display it

        r = await self.connect()
        if r:
            print(f'# Unable to connect to Cerbo GX at {self.ip_address}')
            return

        last_out_w = await q.output_power_watts()
        last_out_va = await q.output_power_va()
        count = 1

        while True:
            out_w = await q.output_power_watts()
            out_va = await q.output_power_va()
            setpoints = await q.ess_power_setpoints()
            if out_w[0] != last_out_w[0]:
                print(f'Count {count}')
                count = 0

            # print(f'Quattros: [Output {out_w[0]} W   {out_va[0]} VA [ESS Setpoint {setpoints[0]} W]')
            time.sleep(0.1)
            last_out_w = out_w
            last_out_va = out_va
            count += 1


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    q = Quattros(addr=settings_gx.GX_IP_ADDRESS)
    asyncio.run(q.main_test())
