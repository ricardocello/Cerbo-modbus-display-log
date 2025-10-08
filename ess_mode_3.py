# -------------------------------------------------------------------------------------------------------------------
# Implements a custom ESS Mode 3 Control Loop.
# This implementation is specific to the ricardocello Victron ESS configuration.
#
# Interesting Features
#
# The Daily Schedule is programmed to handle every day with minimal interaction other than the target minimum SoC
# at which to start the day. The schedule is built around sunrise and sunset times, so it is unaffected by
# seasons changing (including Daylight Saving Time).
#
# The current Daily Schedule has these actions:
#
# (1) Starting five hours before sunrise, the batteries are discharged to the ESS Minimum SoC using Critical Loads.
#     Any PV power that becomes available also powers the Critical Loads, which will slightly reduce
#     the battery discharge rate. This should be sufficient time to discharge the batteries down to 10% from 50% SoC.
#
# (2) Starting one hour after sunrise, solar power is used to power all loads. Grid usage is minimized to the
#     grid setpoint value in Watts. If there is insufficient solar to power all the loads, grid power is used.
#     This keeps the battery SoC increasing monotonically throughout the day. If there is excess solar power available,
#     it is used to charge the batteries. When the battery SoC reaches 80%, the battery is also used to power the
#     loads, helping to prevent the SoC from reaching 100%. As the solar power decreases such that it is again
#     insufficient to power all loads, the battery SoC will be held at 80%.
#
# (3) Starting in the afternoon (75% of the solar day completed), the battery is maintained at a 50% SoC.
#     If the SoC is above 50%, the battery is used to power the Critical Loads until it reaches 50% SoC.
#     If the SoC is below 50% due to a really cloudy day, grid is used to bring the battery SoC back up to 50%.
#     This is to guarantee the battery availability during the critical dinner time hours, especially in the summer.
#
# (4) Starting 20 minutes after sunset, the battery is maintained at a 50% SoC as above. However, when the
#     SoC reaches 50%, the inverter and charger are disabled to save considerable idle power overnight (passthru mode).
#     This also disables solar power, but since it is dark, it does not matter.
#     This continues through to the next morning before sunrise.
#
# The user can switch between Optimized, Keep Batteries Charged, and this External Control Mode 3 implementation
# by using the console GUI. When one of the ESS Mode 2 modes is active, the custom Mode 3 implementation idles.
# If the user changes the Minimum SoC value in the GUI, it will be passed on to the Mode 3 implementation when
# External Control is reselected. This is convenient for making a real-time setting change.
# If a Daily Schedule is running, it will be restarted to ensure consistency.
#
# The AllLoadsPV state handles the atypical use-case of applying maximum PV power to loads during the day.
# This is to help avoid filling a battery bank with insufficient capacity and for efficiency.
#
# There is a 400-500 W/sec built-in limitation in the inverter firmware (800-1000 W/sec for split-phase 240V loads).
# Although the Grid Meter and control loop run at 10 Hz, response time to a setpoint change appears to be 0.5 seconds.
# These limitations will cause exported power to be sent to the grid when large loads switch off.
#
# L1 and L2 have independent exponential filters for the power setpoints, with dynamic switching of time constants
# to help minimize inadvertent exporting of power to the grid. This also prevents undesired feeding back on one leg
# to the utility transformer, which should increase efficiency. The time constants have been carefully tuned to
# minimize grid feedback. This also balances the L1/L2 difference from the grid, eliminating the inefficiency of
# sending power back to the utility transformer on the Neutral line.
#
# See https://www.victronenergy.com/live/ess:ess_mode_2_and_3
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

import sys
import asyncio
import time
from zoneinfo import ZoneInfo
from enum import Enum
from datetime import datetime

from modbus_tcp_client import ModbusTCPClient

import settings_gx
import system_gx
import grid_gx
import quattro_gx
import mppt_gx
import shunt_gx

from sun import Sun


class State(Enum):
    # This External Control Mode 3 ESS implementation is always in one of the following states:
    Undefined = 0           # State is initially undefined at startup
    Mode2 = 1               # Normal ESS Mode 2 system operation (not externally controlled Mode 3)
    Idle = 2                # Inverter and charger are disabled (grid pass-thru)
    Charging = 3            # Grid and available PV are used to charge the battery up to a target SoC
    Discharging = 4         # Critical Loads are used to discharge the battery down to a target SoC
    Maintaining = 5         # Charge or discharge as needed to reach a target SoC

    # CriticalLoadsPV
    # PV is sent to the Critical Loads only, with excess PV power charging the batteries.
    # Grid covers the remainder of the power needs, but does not charge the batteries.
    CriticalLoadsPV = 6

    # AllLoadsPV
    # PV is sent to all loads first, with any excess PV power charging the batteries.
    # Grid covers the remainder of the power needs, but does not charge the batteries.
    # When SoC is above 80%, battery power is used before grid power to cover the remainder of
    # the loads in an attempt to keep the battery from reaching 100% SoC.
    AllLoadsPV = 7


class ESSMode3Control:
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS):

        # Inverter Settings
        self.max_inverter_power = 8000.0    # Total for both inverters (Watts)
        self.idle_power = 100.0             # Power used on DC bus (Watts, for inverters, Cerbo, etc.)
        self.max_power_per_inverter = self.max_inverter_power / 2

        # Inverter Status
        self.efficiency = 92.0              # Best inverter/charger efficiency (%, will be updated)

        # Charging, Discharging, Maintaining Settings
        self.charging_power = 4000.0        # For Charging, battery charging power (DC Watts)
        self.target_soc = 50.0              # Target state of charge for Charging or Discharging
        self.hysteresis = 1.0               # Initiate recharge/discharge when this far below/above target SoC (%)

        # Charging, Discharging, Maintaining Status
        self.charge_target_met = False      # True when the Charging target SoC has been reached
        self.discharge_target_met = False   # True when the Discharging target SoC has been reached
        self.passthru_after_soc = False     # When Maintaining Target reached, enter passthru when True

        # AllLoadsPV Settings
        self.grid_setpoint = 200.0          # How much grid should be used as a target for the control loop (Watts)
        self.use_batteries_soc = 80.0       # Use batteries to help prevent reaching 100% SoC at this SoC point
        self.always_use_batteries = False   # If True, always use batteries and PV to power all loads
        self.time_constant = 0.95           # Exponential filter time constant
        self.fast_time_constant = 0.82      # Exponential filter time constant when below grid setpoint (faster)
        self.show_l1_l2 = False             # Displays L1 and L2 to help when debugging
        self.min_usable_pv_power = 100.0    # Minimum PV power that is usable (Watts), below this just goes to battery

        # Control Loop
        self.verbose = False                # Shows control loop parameters if True
        self.update_interval = 1.0          # Seconds (0.1 for AllLoadsPV for a faster control loop)
        self.state = State.Undefined        # Current state
        self.count = 0                      # Loop counter
        self.is_still_mode3 = True          # Set to False when user alters mode to Optimized via console

        self.current_soc = 0.0              # Current measured State of Charge of batteries (%)
        self.pv_dc_power = 0.0              # PV DC power available (Watts)
        self.pv_power = 0.0                 # Estimated AC power available using PV DC Power (Watts)

        self.setpoint = [0.0] * 3           # Power at AC Input as defined by ESS Mode 3 documentation (Watts)
        self.input_power = [0.0] * 3        # Measured input power of the inverters (Watts: L1+L2, L1, L2)
        self.output_power = [0.0] * 3       # Measured output power of the inverters (Watts: L1+L2, L1, L2)
        self.total_power = [0.0] * 3        # Measured total power of the inverters (Watts: L1+L2, L1, L2)

        # Timing
        self.timezone = 'US/Eastern'        # Change as needed
        self.tz = ZoneInfo(self.timezone)   # Timezone object
        self.now = datetime.now(self.tz)    # Current timestamp
        self.previous_now = None            # Previous timestamp setting to None triggers a restart of the scehdule
        self.time_now = ''                  # Current formatted time

        # Daily Schedule
        self.use_schedule = False           # When true, runs the programmed Daily Schedule
        self.afternoon_ratio = 0.75         # Ratio of solar day elapsed to start afternoon time

        self.action_clock = ActionClock()   # Manages the Daily Schedule
        self.sun = None                     # Sunrise/sunset calculation
        self.sunrise = None                 # Approximate sunrise time (hour, minute)
        self.sunset = None                  # Approximate sunset time (hour, minute)
        self.afternoon = None               # Time when most of solar day is completed (hour, minute)

        # Grid Export Statistics for AllLoadsPV
        self.grid_export = GridExportStatistics(self.timezone)

        # Object for each device used on the Cerbo GX
        self.system = system_gx.System(addr)          # System Parameters on Cerbo GX
        self.grid = grid_gx.GridMeter(addr)           # Carlo Gavazzi EM530
        self.quattro = quattro_gx.Quattros(addr)      # 2x Quattro 48|5000|70-100|100 120V Split-Phase
        self.main_shunt = shunt_gx.MainShunt(addr)    # Main SmartShunt used as a battery monitor
        self.all_mppt = mppt_gx.AllMPPT(addr)         # 2x Victron SmartSolar MPPTs (250/70, 250/100)

    async def connect(self):
        # Connects to the Cerbo GX attached devices
        await self.system.connect()         # System Parameters on Cerbo GX
        await self.grid.connect()           # Carlo Gavazzi EM530
        await self.quattro.connect()        # 2x Victron Quattro 48|5000|70-100|100 120V Split-Phase
        await self.main_shunt.connect()     # SmartShunt used as battery monitor, VE.Direct
        await self.all_mppt.connect()       # SmartSolar VE.Can MPPT 250/70 and 250/100

    async def disconnect(self):
        # Disconnects from the Cerbo GX attached devices
        await self.system.disconnect()      # System Parameters on Cerbo GX
        await self.grid.disconnect()        # Carlo Gavazzi EM530
        await self.quattro.disconnect()     # 2x Victron Quattro 48|5000|70-100|100 120V Split-Phase
        await self.main_shunt.disconnect()  # SmartShunt used as battery monitor, VE.Direct
        await self.all_mppt.disconnect()    # SmartSolar VE.Can MPPT 250/70 and 250/100

    async def main_control_loop(self, initial_state=State.Idle,
                                target_soc=50.0, use_schedule=False, use_battery=False):
        # Implements a custom Victron ESS Mode 3 Control Loop
        # target_soc is for Charging/Discharging/Maintaining only
        # use_schedule enables automatic switching of states based on time of day
        # use_battery forces battery discharge to meet grid setpoint regardless of SoC for AllLoadsPV state
        #
        # Runs forever unless interrupted
        # Beware that interrupting with ^C does not always restore ESS Mode 2 properly due to asyncio behavior

        # Wait 30 seconds if not in verbose mode, useful as a Cerbo GX startup delay
        if not self.verbose:
            time.sleep(30.0)

        # Connect and change to initial state
        await self.connect()
        self.use_schedule = use_schedule
        await self.change_state(initial_state, target_soc=target_soc, use_battery=use_battery)

        # Main Control Loop
        try:
            while True:
                await self.control()
                time.sleep(self.update_interval)

        # Attempt to restore normal Victron ESS Mode 2 when interrupted (not reliable yet)
        except (KeyboardInterrupt, ModbusTCPClient.Disconnected):
            await self.change_state(State.Mode2)

    async def create_daily_schedule(self):
        # Creates the ActionClock to run the Daily Schedule.
        # Reads the ESS Minimum SoC value from the Console GUI for the target SoC for Charging/Discharging/Maintaining.

        # Calculate sunrise, sunset, and afternoon times
        await self.calculate_sun_times()

        # Get the target SoC from the Cerbo GX Console GUI
        gui_min_soc = await self.system.ess_min_state_of_charge()

        # Daily Schedule
        self.action_clock = ActionClock()

        # Before Sunrise
        self.action_clock.add_action(self.sunrise[0] - 5, self.sunrise[1], (State.Discharging, gui_min_soc))

        # Daytime
        self.action_clock.add_action(self.sunrise[0] + 1, self.sunrise[1], (State.AllLoadsPV, gui_min_soc))

        # Afternoon
        self.action_clock.add_action(self.afternoon[0], self.afternoon[1], (State.Maintaining, 50.0, False))

        # Twenty minutes after sunset
        t = self.add_time(self.sunset[0], self.sunset[1], 0, 20)
        self.action_clock.add_action(t[0], t[1], (State.Maintaining, 50.0, True))

        # Show Daily Schedule
        if not self.use_schedule:
            print('# Daily schedule is not active')
        else:
            self.action_clock.show()

    async def calculate_sun_times(self):
        # Compute the approximate sunrise and sunset times for today
        self.sun = Sun()
        self.sunrise = self.sun.sunrise_time()
        self.sunset = self.sun.sunset_time()

        # Compute the approximate solar day duration and afternoon time (as a ratio of the solar day)
        solar_duration_minutes = 60 * self.sunset[0] + self.sunset[1] - 60 * self.sunrise[0] - self.sunrise[1]
        afternoon_start = 60 * self.sunrise[0] + self.sunrise[1] + self.afternoon_ratio * solar_duration_minutes
        afternoon_h = int(afternoon_start / 60)
        afternoon_m = int(afternoon_start - 60 * afternoon_h)
        self.afternoon = afternoon_h, afternoon_m

        print(f'# Start of New Day: [Sunrise {self.sunrise[0]:02}:{self.sunrise[1]:02}] '
              f'[Afternoon {self.afternoon[0]:02}:{self.afternoon[1]:02}] '
              f'[Sunset {self.sunset[0]:02}:{self.sunset[1]:02}]')

    async def check_daily_schedule(self):
        # Gets the current timestamp, and checks to see if an action should occur if the Daily Schedule is active.
        # On startup or at midnight, automatically calculates the solar times and creates a new daily schedule.

        # Get the current time
        self.now = datetime.now(self.tz)
        self.time_now = self.now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]   # Include milliseconds

        # Check for date change (happens just after midnight, or at startup) and create new daily schedule if so
        if self.previous_now is None or self.now.day != self.previous_now.day:
            await self.create_daily_schedule()

        # Save the current time
        self.previous_now = self.now

        # If not using schedule, nothing else to do here
        if not self.use_schedule:
            return

        # Check if time for an action
        action = self.action_clock.tick(self.now)
        if action is None:
            return

        # Passthru setting for Maintaining
        do_passthru = False
        if action[3][0] == State.Maintaining:
            do_passthru = action[3][2]

        print(f'# Daily Schedule action at {action[1]:02}:{action[2]:02}: '
              f'[{action[3][0]}] [Target SoC {action[3][1]:.1f}%]')
        await self.change_state(action[3][0], target_soc=action[3][1], passthru_after_soc=do_passthru)

    async def change_state(self, new_state,
                           target_soc=50.0, charging_power=4000.0,
                           passthru_after_soc=False, use_battery=False):
        # Transitions the Mode 3 ESS to a new state.
        #
        # target_soc is applicable to Charging and Discharging States.
        # charging_power is applicable to Charging State.
        # passthru_after_soc is applicable to Maintaining State.
        # use_battery is applicable to AllLoadsPV

        # Settings
        mode3, inverter, charger, msg = True, False, False, ''
        self.count = 0
        self.update_interval = 1.0    # 1 second for all states except AllLoadsPV

        # ESS Mode 2: Reset to normal Mode 2 ESS mode and do nothing
        if new_state == State.Mode2:
            mode3, inverter, charger = False, True, True
            msg = '# ESS has been reset to Standard Mode 2 operation'

        # Idle State passes grid through to the output and greatly lowers power consumption
        elif new_state == State.Idle:
            mode3, inverter, charger = True, False, False
            msg = '# ESS is now in Idle State (Pass-Thru)'

        # Charging State charges the battery at a fixed rate until a target SoC is reached
        elif new_state == State.Charging:
            mode3, inverter, charger = True, False, True
            msg = f'# ESS is now in Battery Charging State ' \
                  f'[Target SoC {target_soc:.1f}%] [Charging Power {charging_power:.0f} W]'
            self.target_soc = target_soc
            self.charging_power = charging_power
            self.charge_target_met = False

        # Discharging State discharges the battery using only Critical Loads until a target SoC is reached
        elif new_state == State.Discharging:
            mode3, inverter, charger = True, True, True
            msg = f'# ESS is now in Battery Discharging State [Target SoC {target_soc:.1f}%]'
            self.target_soc = target_soc
            self.discharge_target_met = False

        # Maintaining State charges or discharges the battery until a target SoC is reached
        elif new_state == State.Maintaining:
            mode3, inverter, charger = True, True, True
            msg = f'# ESS is now in Battery Maintaining State [Target SoC {target_soc:.1f}%]'
            self.target_soc = target_soc
            self.charge_target_met = False
            self.discharge_target_met = False
            self.passthru_after_soc = passthru_after_soc

        # CriticalLoadsPV State sends PV power to the critical loads, with excess power charging the batteries
        elif new_state == State.CriticalLoadsPV:
            mode3, inverter, charger = True, True, True
            msg = '# ESS is now in Critical Loads PV Consumption State'

        # AllLoadsPV State sends PV power to all loads, with excess power charging the batteries
        elif new_state == State.AllLoadsPV:
            mode3, inverter, charger = True, True, True
            msg = '# ESS is now in All Loads PV Consumption State'
            self.update_interval = 0.1
            self.always_use_batteries = use_battery
            self.grid_export = GridExportStatistics()

        # Settings for System and Quattro hub4 in Mode 3
        if new_state != State.Mode2:
            await self.system.set_ess_mode_3(mode3)
            await self.quattro.enable_inverter(inverter)
            await self.quattro.enable_charger(charger)

            await self.quattro.set_setpoints_as_limit(True)
            await self.quattro.set_pv_feed_in(False)
            await self.quattro.set_setpoints_as_limit(True)
            await self.quattro.set_pv_feed_in_limit(32767, 32767)
            # tbd: other settings may have changed, need to check

        # A change of state has occurred
        if new_state != self.state:
            print(msg)

            # If leaving AllLoadsPV, show the grid export statistics and update the log file
            if self.state == State.AllLoadsPV:
                print(self.grid_export)
                self.grid_export.log_events_to_file()
            self.state = new_state

    async def control(self):
        # Implements the control function called repeatedly by the main control loop at 1 or 10 Hz.
        # All states are handled here.

        # Check daily schedule to see if change in state is needed
        await self.check_daily_schedule()

        # Check to see if user has manually changed the ESS Mode back to Mode 2.
        if await self.check_for_user_mode_change():
            return

        # Get Critical Loads Power usage
        self.output_power = await self.quattro.output_power_watts()       # total, L1, L2

        # Input power usage (negative is feed-in to grid)
        self.input_power = await self.quattro.input_power_watts()         # total, L1, L2

        # Total inverter power
        self.total_power = [self.output_power[0] - self.input_power[0],
                            self.output_power[1] - self.input_power[1],
                            self.output_power[2] - self.input_power[2]]

        # Estimate inverter/charger efficiency at this total output power level
        self.efficiency = self.quattro.estimated_efficiency(self.total_power[0])

        # Get current battery State of Charge
        self.current_soc = await self.main_shunt.state_of_charge()

        # Get available PV DC Power
        self.pv_dc_power = await self.all_mppt.total_dc_power()

        # Calculate estimated AC power that can be created using inverter at the current efficiency
        self.pv_power = self.efficiency * self.pv_dc_power / 100.0

        # State: Charging Battery
        if self.state == State.Charging:
            await self.charging()

        # State: Discharging Battery
        elif self.state == State.Discharging:
            await self.discharging()

        # State: Maintaining Battery
        elif self.state == State.Maintaining:
            await self.maintaining()

        # State: Critical Loads PV Consumption
        elif self.state == State.CriticalLoadsPV:
            await self.critical_loads_pv()

        # State: All Loads PV Consumption
        elif self.state == State.AllLoadsPV:
            await self.all_loads_pv()

        # Increment counter
        self.count += 1

    async def check_for_user_mode_change(self):
        # Checks to see if the user has changed ESS modes in the GX console GUI.
        # If so, suspends the current Mode 3 control loop and waits for a switch back to External Control.
        # If the Minimum SoC GUI setting was changed, the target SoC will now use that value.
        # This provides a way to update the ESS Mode 3 target SoC in real time.

        # Check if user has manually changed back to Mode 2 ESS
        still_mode3 = await self.system.is_ess_mode_3()

        # Mode 3 has resumed because user selected External Control in the GX GUI
        if still_mode3 and not self.is_still_mode3:
            self.target_soc = await self.system.ess_min_state_of_charge()
            print(f'# User has resumed External Control [New Target SoC {self.target_soc:.1f}%]')
            self.is_still_mode3 = True

            # Restart the Daily Schedule (if it was enabled)
            self.previous_now = None           # triggers a daily restart
            await self.check_daily_schedule()
            return False

        # Mode 3 is no longer selected, don't do anything else
        elif not still_mode3:
            if self.is_still_mode3:
                print('# User has changed modes using GX Console, Mode 3 will resume when External Control is selected')
                self.is_still_mode3 = False
            return True

        return False

    async def charging(self):
        # Charges the battery using PV and/or Grid until the target SoC is reached.
        # If the battery subsequently discharges below the hysteresis, charging is restarted.

        # Done charging when target SoC has been reached
        target_met = self.current_soc >= self.target_soc
        if target_met:
            self.charge_target_met = True

        # Done charging, but battery has been discharging and now SoC is now below hysteresis
        if self.charge_target_met and self.current_soc <= self.target_soc - self.hysteresis:
            print(f'{self.time_now} [Restarting Charge] '
                  f'[SoC {self.target_soc:5.1f}%] [Target {self.target_soc:5.1f}%]')
            await self.quattro.enable_charger(True)   # just in case disabled by maintaining()
            await self.quattro.enable_inverter(True)
            self.charge_target_met = False

        # DC Watts from PV should be used if available
        dc_power_needed = self.charging_power - self.pv_dc_power + self.idle_power
        dc_power_needed = max(dc_power_needed, 0.0)
        ac_power_needed_per_inverter = 0.0 if self.charge_target_met \
            else (0.5 * dc_power_needed / (self.efficiency/100.0))

        # Setpoint is Critical Loads plus extra power to charge batteries (split charging between Quattros)
        l1_setpoint = self.output_power[1] + ac_power_needed_per_inverter
        l2_setpoint = self.output_power[2] + ac_power_needed_per_inverter

        self.setpoint = [l1_setpoint + l2_setpoint, l1_setpoint, l2_setpoint]
        await self.quattro.set_mode_3_power_setpoint(self.setpoint[1], self.setpoint[2])

        if self.verbose:
            status = 'Not Charging' if self.charge_target_met else 'Charging'

            print(f'{self.time_now} [{status}] [PV Power {self.pv_dc_power:4.0f} W] '
                  f'[Battery Power {dc_power_needed:4.0f} W] '
                  f'[Per Inverter AC Power {ac_power_needed_per_inverter:4.0f} W] '
                  f'[SoC {self.current_soc:5.1f}%] [Target {self.target_soc:5.1f}%] '
                  f'[Setpoint {self.setpoint[0]:4.0f} W] [Eff {self.efficiency:4.1f}%]')

    async def discharging(self):
        # Discharges the battery using only Critical Loads.
        # If the battery subsequently charges above the hysteresis due to PV, discharging is restarted.

        # Done discharging when target SoC has been reached
        target_met = self.current_soc <= self.target_soc
        if target_met:
            self.discharge_target_met = True

        # Done discharging, but PV has been recharging and now SoC is now above hysteresis
        if self.discharge_target_met and self.current_soc >= self.target_soc + self.hysteresis:
            print(f'{self.time_now} [Restarting Discharge] '
                  f'[SoC {self.target_soc:5.1f}%] [Target {self.target_soc:5.1f}%]')
            await self.quattro.enable_charger(True)   # just in case disabled by maintaining()
            await self.quattro.enable_inverter(True)
            self.discharge_target_met = False

        # Setpoint should match Critical Loads (unless target has been reached)
        l1_setpoint = (self.output_power[1] + 0.5 * self.idle_power) if self.discharge_target_met else 0.0
        l2_setpoint = (self.output_power[2] + 0.5 * self.idle_power) if self.discharge_target_met else 0.0

        self.setpoint = [l1_setpoint + l2_setpoint, l1_setpoint, l2_setpoint]
        await self.quattro.set_mode_3_power_setpoint(self.setpoint[1], self.setpoint[2])

        if self.verbose:
            status = 'Not Discharging' if self.discharge_target_met else 'Discharging'

            print(f'{self.time_now} [{status}] [Critical Loads {self.output_power[0]:4.0f} W] '
                  f'[SoC {self.current_soc:5.1f}%] [Target {self.target_soc:5.1f}%] '
                  f'[Setpoint {self.setpoint[0]:4.0f} W] [Eff {self.efficiency:4.1f}%]')

    async def maintaining(self):
        # Maintains the target SoC by either charging or discharging the batteries.
        #
        # If passthru_after_soc is True, then the inverters are put into pass-thru mode
        # when the target SoC is reached. Once the hysteresis is exceeded in either direction,
        # the inverters and chargers are automatically re-enabled.
        # The disadvantage of this is that the MPPTs are also disabled, and PV power will be lost.

        # Charging because SoC is below the target SoC
        if self.current_soc < self.target_soc:
            await self.charging()

        # Discharging because SoC is above the target SoC
        elif self.current_soc > self.target_soc:
            await self.discharging()

        # At the target SoC
        else:
            # Give both charing and discharging code a chance to run to set flags
            await self.charging()
            await self.discharging()

            # Go into pass-thru mode to save power
            if self.passthru_after_soc:
                await self.quattro.enable_charger(False)
                await self.quattro.enable_inverter(False)

    async def critical_loads_pv(self):
        # Uses as much PV as possible for Critical Loads.
        # Excess PV power will charge the batteries.

        # Calculate the L1/L2 balance ratios
        try:
            ratio_l1 = self.output_power[1] / self.output_power[0]        # L1 ratio of output power
            ratio_l2 = self.output_power[2] / self.output_power[0]        # L2 ratio of output power
        except ZeroDivisionError:
            ratio_l1 = ratio_l2 = 0.5

        critical_pv_power = [min(self.pv_power, self.output_power[0] + self.idle_power), 0.0, 0.0]
        critical_pv_power[1] = min(self.max_power_per_inverter, critical_pv_power[0] * ratio_l1)
        critical_pv_power[2] = min(self.max_power_per_inverter, critical_pv_power[0] * ratio_l2)

        # Use the remainder of the PV power to charge the battery
        battery_charging_power = max(self.pv_power - critical_pv_power[0], 0)

        # Setpoint should also include idle power
        l1_setpoint = self.output_power[1] - critical_pv_power[1] + 0.5 * self.idle_power
        l2_setpoint = self.output_power[2] - critical_pv_power[2] + 0.5 * self.idle_power

        self.setpoint = [l1_setpoint + l2_setpoint, l1_setpoint, l2_setpoint]
        await self.quattro.set_mode_3_power_setpoint(self.setpoint[1], self.setpoint[2])

        if self.verbose:
            print(f'{self.time_now} [Critical Load PV Power {self.three_power(critical_pv_power)} W] '
                  f'[Battery Charging Power {battery_charging_power:4.0f} W] '
                  f'[Setpoint {self.setpoint[0]:4.0f} W] [Eff {self.efficiency:4.1f}%]')

    async def all_loads_pv(self):
        # Powers all loads using the grid meter to set a grid setpoint similar to ESS Mode 2.
        # By default, only PV power is used to power the loads.
        # Excess PV power will charge the batteries.
        #
        # If always_use_batteries is True, or if the SoC is over use_batteries_soc,
        # both PV and battery power will be used to power the loads
        # up to the limit of the inverters.

        # Initial Setpoint
        if self.count == 0:
            self.setpoint = list(await self.quattro.ess_power_setpoint())   # total, L1, L2
            await self.quattro.set_mode_3_power_setpoint(self.setpoint[1], self.setpoint[2])

        # Try to hold the actual grid power usage close to the grid setpoint
        grid_power = await self.grid.power_watts()  # total, L1, L2

        # Accumulate grid export statistics
        self.grid_export.grid_measurement(self.now, grid_power[0])
        if self.verbose and self.count % 600 == 0:
            print(self.grid_export)

        # Power needed for each inverter is independently calculated
        power_needed_now = [0.0] * 3
        power_needed_now[1] = grid_power[1] - self.grid_setpoint / 2.0
        power_needed_now[2] = grid_power[2] - self.grid_setpoint / 2.0
        power_needed_now[0] = power_needed_now[1] + power_needed_now[2]

        # If PV power is negligible, don't bother running the inverter
        if self.pv_power < self.min_usable_pv_power:
            l1_power_limit = 0
            l2_power_limit = 0

        # Use as much PV power as possible, distributing power based on L1/L2 ratio, staying within limits
        elif not self.always_use_batteries and self.current_soc < self.use_batteries_soc:

            # Calculate the L1/L2 balance ratios
            try:
                ratio_l1 = self.total_power[1] / self.total_power[0]     # L1 ratio of total power
                ratio_l2 = self.total_power[2] / self.total_power[0]     # L2 ratio of total power
            except ZeroDivisionError:
                ratio_l1 = ratio_l2 = 0.5

            # Allocate PV power to inverters based on the ratio
            l1_pv = self.pv_power * ratio_l1
            l2_pv = self.pv_power * ratio_l2

            # Limit power to available PV power or max inverter power per leg
            l1_power_limit = min(self.max_power_per_inverter, l1_pv)
            l2_power_limit = min(self.max_power_per_inverter, l2_pv)

            # If excess PV power available for L1, raise the power limit for L2, stay within limit
            if l2_pv < self.max_power_per_inverter <= l1_pv:
                l2_power_limit = min(self.max_power_per_inverter, l2_pv + l1_pv - self.max_power_per_inverter)

            # If excess PV power available for L2, raise the power limit for L1, stay within limit
            elif l1_pv < self.max_power_per_inverter <= l2_pv:
                l1_power_limit = min(self.max_power_per_inverter, l1_pv + l2_pv - self.max_power_per_inverter)

        # Limited only by inverter power: Use PV and battery up to each inverter power limit
        else:
            l1_power_limit = self.max_power_per_inverter
            l2_power_limit = self.max_power_per_inverter

        # Enforce minimum setpoint values based on power limits
        min_setpoint = [0.0, self.output_power[1] - l1_power_limit, self.output_power[2] - l2_power_limit]

        # Delayed start for debugging to analyze startup behavior
        if self.count >= 20:
            # Use a fast time constant when grid power drops below desired offset (per inverter)
            tc1 = self.time_constant if grid_power[1] > self.grid_setpoint else self.fast_time_constant
            tc2 = self.time_constant if grid_power[2] > self.grid_setpoint else self.fast_time_constant

            # Exponential filter (per inverter)
            self.setpoint[1] = tc1 * self.setpoint[1] + (1.0 - tc1) * (self.setpoint[1] - power_needed_now[1])
            self.setpoint[2] = tc2 * self.setpoint[2] + (1.0 - tc2) * (self.setpoint[2] - power_needed_now[2])

            # Limit the setpoint so the inverters are not overloaded (per inverter)
            self.setpoint[1] = max(self.setpoint[1], min_setpoint[1])
            self.setpoint[2] = max(self.setpoint[2], min_setpoint[2])
            self.setpoint[0] = self.setpoint[1] + self.setpoint[2]

        await self.quattro.set_mode_3_power_setpoint(self.setpoint[1], self.setpoint[2])

        if self.verbose:
            if self.show_l1_l2:
                print(f'{self.time_now} '
                      f'[Grid {self.three_power(grid_power)} W] '
                      f'[Inverter {self.three_power(self.total_power)} W] '
                      f'[Needed {self.three_power(power_needed_now)} W] [PV {self.pv_power:4.0f} W] '
                      f'[SoC {self.current_soc:4.1f}%] '
                      f'[Setpoint {self.three_power(self.setpoint)} W] [Eff {self.efficiency:4.1f}%]')
            else:
                print(f'{self.time_now} '
                      f'[Grid {grid_power[0]:4.0f} W] '
                      f'[Inverter {self.total_power[0]:4.0f} W] '
                      f'[Needed {power_needed_now[0]:4.0f} W] [PV {self.pv_power:4.0f} W] '
                      f'[SoC {self.current_soc:4.1f}%] '
                      f'[Setpoint {self.setpoint[0]:4.0f} W] [Eff {self.efficiency:4.1f}%]')

    @staticmethod
    def three_power(power):
        return f'{power[0]:4.0f} {power[1]:4.0f} {power[2]:4.0f}'

    @staticmethod
    def add_time(hour, minute, h, m):
        hh, mm = (hour + h), (minute + m)
        if mm >= 60:
            mm -= 60
            hh += 1
        if hh >= 24:
            hh -= 24
        return hh, mm


class ActionClock:
    # Manages a Daily Schedule with actions that should occur only once per day.
    # Call tick() repeatedly with the current time, and it will return an action when necessary.
    #
    # When the ActionClock is created, the most recent action is executed regardless of the current time.
    # This is useful when the ESS control loop is stopped and restarted.

    def __init__(self):
        self.actions = []
        self.do_startup_action = True   # When the first tick() occurs, any current action will be given immediately

    def add_action(self, hour, minute, info):
        # Adds the specified action using 24-hour time.
        # Maintains the list of actions in increasing time order (insertion sort).
        # Only one action is permitted at a specific time.
        # Actions are stored internally as a list containing the hour, minute, and info.
        # A flag is also stored to mark when an action has been completed.

        insert_at = len(self.actions)
        for index, action in enumerate(self.actions):
            t = 60 * hour + minute
            t_action = 60 * action[1] + action[2]

            if t_action > t:
                insert_at = index
                break

            elif t_action == t:
                self.actions[index][3] = info
                return

        self.actions.insert(insert_at, [True, hour, minute, info])

    def reset_daily_actions(self):
        # Resets all actions to be active for the day
        for action in self.actions:
            action[0] = True  # mark action as active

    def tick(self, timestamp):
        # Accepts the current timestamp.
        # If it is time for an action, returns the action list [active, hour, minute, info].
        # Otherwise, returns None
        # Once an action is triggered during a day, it will not occur again

        if self.do_startup_action:
            self.do_startup_action = False
            return self.startup_action(timestamp)

        for index, action in enumerate(self.actions):
            if action[0] and timestamp.hour == action[1] and timestamp.minute == action[2]:
                action[0] = False  # mark action as inactive
                return action
        return None

    def show(self):
        # Displays the Daily Schedule
        if len(self.actions) == 0:
            return

        print(f'# Daily Schedule')
        for action in self.actions:
            print(f'# {action[1]:02}:{action[2]:02} {action[3][0]:20} {action[3][1]}%')

    def startup_action(self, timestamp):
        # Returns the action for the current timestamp, even if the action should have occured earlier in the day.
        # This is useful for consistency during restarts of the system during the day.

        if len(self.actions) == 0:
            return None

        action_index = len(self.actions) - 1     # assume last action in the list from previous day
        for index, action in enumerate(self.actions):
            t = 60 * timestamp.hour + timestamp.minute
            t_action = 60 * action[1] + action[2]

            if t_action > t:
                action_index = index - 1    # can be -1 if current time is before the first action
                break

        return self.actions[action_index]


class GridExportStatistics:
    # This class calculates detailed statistics for Grid Export events (which are very undesirable).
    # The measurement function takes the current timestamp and grid power measurement.

    class Event:
        # An event is a consecutive string of negative grid power measurements (exporting to grid).
        # Each event is characterized by its duration (sec), its total energy (Wh), and its maximum export power (W).

        def __init__(self, timestamp):
            self.timestamp = timestamp
            self.total_duration = 0.0        # seconds
            self.total_energy = 0.0          # Wh
            self.max_export_power = 0.0      # W
            self.num_measurements = 0

        def measurement(self, power, duration):    # Watts, seconds
            # Adds the specified measured power and its duration to the event.
            watt_hours = power * duration / 3600.0

            self.total_duration += duration
            self.total_energy += watt_hours
            self.max_export_power = max(self.max_export_power, power)
            self.num_measurements += 1

        def __str__(self):
            t = self.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]    # Include milliseconds
            return f'{t} {self.total_duration:6.3f} [{self.total_energy:6.1f} Wh] [{self.max_export_power:4.0f} W Max]'

    def __init__(self, timezone='US/Eastern'):
        self.tz = ZoneInfo(timezone)

        self.previous_timestamp = None
        self.events = []
        self.current_event = None

        self.total_duration = 0.0             # seconds
        self.total_energy = 0.0               # Wh
        self.total_measurements = 0

        self.max_duration = 0.0               # seconds
        self.max_energy = 0.0                 # Wh
        self.max_export_power = 0.0           # W

    def __str__(self):
        num_events = len(self.events)
        return (f'# Grid Export: [{num_events:4} Events] [{self.total_duration:6.1f} sec] [{self.total_energy:8.3f} Wh]'
                f'[{self.max_duration:6.3f} sec Max] '
                f'[{self.max_energy:8.3f} Wh Max] [{self.max_export_power:4.0f} W Max]')

    def grid_measurement(self, timestamp, watts):
        # Now exporting power to grid
        if watts < 0.0:
            # Start a new current event
            if self.current_event is None:
                self.current_event = self.Event(timestamp)

            if self.previous_timestamp is None:
                self.previous_timestamp = timestamp
            duration = timestamp - self.previous_timestamp
            self.current_event.measurement(-watts, duration.total_seconds())

        # Now importing power from grid
        elif self.current_event is not None:

            # Update statistics
            self.total_duration += self.current_event.total_duration
            self.total_energy += self.current_event.total_energy
            self.total_measurements += self.current_event.num_measurements

            self.max_export_power = max(self.max_export_power, self.current_event.max_export_power)
            self.max_duration = max(self.max_duration, self.current_event.total_duration)
            self.max_energy = max(self.max_energy, self.current_event.total_energy)

            # Add the event to the list, completing the event
            self.events.append(self.current_event)
            self.current_event = None

        # Save timestamp for next measurement
        self.previous_timestamp = timestamp

    def show_events(self):
        for e in self.events:
            print(e)

    def log_events_to_file(self):
        today = datetime.now(self.tz)
        filename = today.strftime('%Y_%m_%d_%H_%M_%S_grid_export.log')

        with open(filename, 'a') as file:
            # Header Information
            file.write(f'{filename}\n')
            file.write(f'Total Duration:         {self.total_duration:6.3f} seconds\n')
            file.write(f'Total Energy:           {self.total_energy:8.3f} Wh\n')
            file.write(f'Maximum Export Power:   {self.max_export_power:4.0f} W\n')
            file.write(f'Number of Measurements: {self.total_measurements}\n')
            file.write(f'\n')

            # Tab-delimited event log
            file.write(f'Event\tDuration (sec)\tMeasurements\tEnergy (Wh)\tMax Export (W)\n')
            for e in self.events:
                t = e.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Include milliseconds
                file.write(f'{t}\t{e.total_duration:6.3f}\t{e.num_measurements}\t'
                           f'{e.total_energy:8.3f}\t{e.max_export_power:4.0f}\n')


if __name__ == "__main__":
    # Run the main_control_loop() if this file is executed directly

    # Default settings
    startup_state = State.Idle
    tsoc = 50.0
    do_schedule = False
    use_batteries = False

    n = len(sys.argv)
    if n > 1:
        # ESS Mode 2
        if sys.argv[1] == 'mode2':
            startup_state = State.Mode2

        # Charging Batteries
        elif sys.argv[1] == 'charge':
            startup_state = State.Charging
            tsoc = float(sys.argv[2]) if n > 2 else 50.0

        # Discharging Batteries
        elif sys.argv[1] == 'discharge':
            startup_state = State.Discharging
            tsoc = float(sys.argv[2]) if n > 2 else 50.0

        # Power Critical Loads from PV and Grid
        elif sys.argv[1] == 'critical':
            startup_state = State.CriticalLoadsPV

        # Power All Loads from PV and Grid, minimize grid use
        elif sys.argv[1] == 'all':
            startup_state = State.AllLoadsPV
            use_batteries = True

        # Run the daily schedule
        elif sys.argv[1] == 'schedule':
            startup_state = State.Undefined
            do_schedule = True

    # Run the main control loop
    ess_mode_3 = ESSMode3Control()
    asyncio.run(ess_mode_3.main_control_loop(startup_state,
                                             target_soc=tsoc,
                                             use_schedule=do_schedule,
                                             use_battery=use_batteries))
