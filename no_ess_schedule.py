# -------------------------------------------------------------------------------------------------------------------
# Implements a scheduler for controlling a Victron system without the ESS Assistant installed.
# This implementation is specific to the ricardocello Victron configuration.
#
# Interesting Features
#
# The Daily Schedule is programmed to handle every day with minimal interaction.
# The schedule is built around sunrise and sunset times, so it is unaffected by
# seasons changing (including Daylight Saving Time).
#
# The current Daily Schedule has these actions:
#
# (1) Discharging State
#     Starting before sunrise, the batteries are discharged down to the minimum SoC (e.g. 15%)
#     by powering the Critical Loads with the inverters.
#
#     Any available PV will also power the loads, but in the early hours this will be minimal.
#     If the minimum SoC is reached, a transition is automatically made to the MonitoringSoC state.
#
# (2) MonitoringSoC State
#     Starting after sunrise, the incoming PV power is monitored while the grid is connected.
#     When the DVCC algorithm limits or turns off an MPPT, the DVCC current limit is slowly raised
#     until it permits all of the PV power to be consumed by the loads or the batteries.
#     Minimal grid power is used to charge the batteries in this state.
#
#     When the SoC reaches the target SoC (e.g. 40%), the Grid is disconnected if there is sufficient
#     PV power for the loads. Should the SoC drop below the hysteresis SoC (e.g. 35%) due to insufficient PV,
#     the Grid is reconnected with charging coming exclusively from PV until it again exceeds the target SoC
#     and there is sufficient PV power for the loads.
#     Either way, all of the available PV is consumed by either the loads and/or the batteries.
#
#     If the SoC reaches the high SoC (e.g. 90%), the Grid is disconnected in an attempt to prevent the
#     batteries from filling completely, regardless of whether the PV power is sufficient for the loads.
#
# (3) CheckSoC State
#     Starting in the afternoon, the battery BMS SoC is checked for drift by comparing to the shunt SoC.
#     If the difference is under the threshold, transitions immediately back to the MonitoringSoC state.
#     If the difference is over the threshold, the batteries are charged to 100% via PV and/or grid.
#     When the full recharge is completed, transitions back to the MonitoringSoC state.
#     The BMS SoC has been reset when 100% SoC is indicated.
#     This also ensures that the batteries are balanced occasionally.
#
# (4) Maintaining State
#     Starting after sunset, the battery is maintained at its SoC by disabling the charger.
#     The Grid is reconnected overnight unless there is an outage.
#     The SoC will typically be between 30% and 40% for a target SoC of 40%.
#     This is sufficient to carry through the dinner and evening hours, providing a backup power supply.
#     This continues through to the next morning.
#
# (5) Suspended State
#     By enabling "Limit Managed Battery Charge Voltage",
#     it is possible to suspend all control until the next scheduled event.
#     Disabling it resumes normal operation.
#
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
import math
from zoneinfo import ZoneInfo
from enum import Enum
from datetime import datetime

from modbus_tcp_client import ModbusTCPClient

import settings_gx
import system_gx
import quattro_gx
import shunt_gx
import battery_gx
import mppt_gx

from sun import Sun


class State(Enum):
    # Undefined
    # State is initially undefined at startup, no action is taken
    Undefined = 0

    # Charging
    # Connects to the Grid to charge the batteries up to a target SoC.
    Charging = 1

    # Maintaining
    # Connects to the Grid, but disables battery charging from both Grid and PV.
    Maintaining = 2

    # MonitorPVCharging
    # Connects to the Grid, adjusting the maximum charge current based on the amount of PV power available.
    MonitorPVCharging = 3

    # Discharging
    # Disconnects from the Grid to discharge the batteries down to a target SoC.
    Discharging = 4

    # MonitorSoC
    # Uses only PV to charge the batteries up to 50% SoC. Above 50%, disconnects from the grid.
    MonitorSoC = 5

    # CheckSoC
    # Checks for BMS SoC drift, recharges batteries to 100% if threshold exceeded.
    CheckSoC = 6

    # Suspended
    # Takes no actions, even scheduled ones.
    Suspended = 7


class NoESSSchedule:
    def __init__(self, addr=settings_gx.GX_IP_ADDRESS):

        # Settings
        self.target_soc = 50.0               # Target state of charge
        self.monitoring_target_soc = 40.0    # Target SoC for MonitoringSoC state
        self.min_soc = 15.0                  # Miniumum allowable State of Charge
        self.hi_soc = 90.0                   # High State of Charge
        self.hysteresis = 5.0                # Initiate recharge/discharge when this far below/above target SoC (%)

        self.charge_limit_amps = 120.0       # Battery DVCC charging current limit (sized to meet battery specs)
        self.pv_charge_limit_amps = 140.0    # Battery DVCC charging current limit (sized to meet battery specs)
        self.efficiency = 92.0               # Best inverter/charger efficiency (%, will be updated)

        self.soc_error_threshold = 8.0       # Difference between shunt and BMS SoC causes recharge to 100% (%)
        self.recharge_current = 80.0         # CheckSoC recharging current (A)

        self.charge_target_met = False       # True when the Charging target SoC has been reached
        self.discharge_target_met = False    # True when the Discharging target SoC has been reached
        self.check_recharging = False        # True when recharging due to excessive BMS SoC drift

        # Control Loop
        self.verbose = True                  # Shows control loop parameters if True
        self.update_interval = 1.0           # Seconds
        self.state = State.Undefined         # Current state
        self.count = 0                       # Loop counter since current state started
        self.unsuspend = False               # Set to True if suspended, but user has just unsuspended

        self.current_soc = 0.0               # Measured State of Charge of batteries from shunt (%)
        self.charge_current = 0.0            # Battery Charging Current from shunt (A)
        self.battery_soc = 0.0               # EG4 BMS State of Charge (%)
        self.pv_dc_power = 0.0               # PV DC power available (Watts)
        self.pv_dc_current = 0.0             # PV DC current (Amps)
        self.pv_monitor_limit = 2.0          # Maximum charge current adjusted dynamically (Amps)
        self.pv_monitor_delay = 0            # Counts down to handle Limited MPPT slow response

        self.pv_power = 0.0                  # Estimated AC power available using PV DC Power (Watts)
        self.output_power = [0.0] * 3        # Measured output power of the inverters (Watts: L1+L2, L1, L2)

        self.avg_output_power = 0.0          # 10 minute averge total output power for critical loads
        self.avg_pv_power = 0.0              # 10 minute averge total pv AC power available

        # Timing
        self.timezone = 'US/Eastern'         # Change as needed
        self.tz = ZoneInfo(self.timezone)    # Timezone object
        self.now = datetime.now(self.tz)     # Current timestamp
        self.previous_now = None             # Previous timestamp setting to None triggers a restart of the scehdule
        self.time_now = ''                   # Current formatted time

        # Daily Schedule
        self.use_schedule = False            # When true, runs the programmed Daily Schedule
        self.afternoon_ratio = 0.75          # Ratio of solar day elapsed to start afternoon time

        self.action_clock = ActionClock()    # Manages the Daily Schedule
        self.sun = None                      # Sunrise/sunset calculation
        self.sunrise = None                  # Approximate sunrise time (hour, minute)
        self.sunset = None                   # Approximate sunset time (hour, minute)
        self.afternoon = None                # Time when most of solar day is completed (hour, minute)

        # Object for each device used on the Cerbo GX
        self.system = system_gx.System(addr)          # System Parameters on Cerbo GX
        self.quattro = quattro_gx.Quattros(addr)      # 2x Quattro 48|5000|70-100|100 120V Split-Phase
        self.main_shunt = shunt_gx.MainShunt(addr)    # Main SmartShunt used as a battery monitor
        self.battery = battery_gx.Battery(addr)       # EG4 Battery Rack, VE.Can
        self.all_mppt = mppt_gx.AllMPPT(addr)         # 2x Victron SmartSolar MPPTs (250/70, 250/100)

    async def connect(self):
        # Connects to the Cerbo GX attached devices
        await self.system.connect()         # System Parameters on Cerbo GX
        await self.quattro.connect()        # 2x Victron Quattro 48|5000|70-100|100 120V Split-Phase
        await self.main_shunt.connect()     # SmartShunt used as battery monitor, VE.Direct
        await self.battery.connect()        # EG4 Battery Rack, VE.Can
        await self.all_mppt.connect()       # SmartSolar VE.Can MPPT 250/70 and 250/100

    async def disconnect(self):
        # Disconnects from the Cerbo GX attached devices
        await self.system.disconnect()      # System Parameters on Cerbo GX
        await self.quattro.disconnect()     # 2x Victron Quattro 48|5000|70-100|100 120V Split-Phase
        await self.main_shunt.disconnect()  # SmartShunt used as battery monitor, VE.Direct
        await self.battery.disconnect()     # EG4 Battery Rack, VE.Can
        await self.all_mppt.disconnect()    # SmartSolar VE.Can MPPT 250/70 and 250/100

    async def main_control_loop(self, initial_state=State.Undefined, target_soc=50.0, use_schedule=False):
        # Implements a Control Loop for managing the Victron system.
        # target_soc is for Charging/Discharging only
        # use_schedule enables automatic switching of states based on time of day
        #
        # Runs forever unless interrupted

        # Wait 30 seconds if not in verbose mode, useful as a Cerbo GX startup delay
        if not self.verbose:
            time.sleep(30.0)

        # Connect and change to initial state
        await self.connect()
        self.use_schedule = use_schedule
        await self.change_state(initial_state, target_soc=target_soc)

        # Main Control Loop
        try:
            while True:
                await self.control()
                time.sleep(self.update_interval)

        # Interrupted
        except (KeyboardInterrupt, ModbusTCPClient.Disconnected):
            pass

    async def create_daily_schedule(self):
        # Creates the ActionClock to run the Daily Schedule.

        # Calculate sunrise, sunset, and afternoon times
        await self.calculate_sun_times()

        # Daily Schedule
        self.action_clock = ActionClock()

        # Before Sunrise
        self.action_clock.add_action(self.sunrise[0] - 1, self.sunrise[1], (State.Discharging, self.min_soc))

        # Daytime
        self.action_clock.add_action(self.sunrise[0] + 2, self.sunrise[1],
                                     (State.MonitorSoC, self.monitoring_target_soc))

        # Afternoon
        self.action_clock.add_action(self.afternoon[0], self.afternoon[1], (State.CheckSoC, self.target_soc))

        # After sunset
        t = self.add_time(self.sunset[0], self.sunset[1], 3, 0)
        self.action_clock.add_action(t[0], t[1], (State.Maintaining, self.target_soc))

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
        new_state, target_soc = action[3]

        # If in Suspended state, do not change the state, but log it anyway
        if self.state == State.Suspended and not self.unsuspend:
            print(f'# [Suspended] Daily Schedule action not taken at {action[1]:02}:{action[2]:02}: '
                  f'[{new_state}] [Target SoC {target_soc:.1f}%]')

        # Change to the new state, clear unsuspend flag
        else:
            print(f'# Daily Schedule action at {action[1]:02}:{action[2]:02}: '
                  f'[{new_state}] [Target SoC {target_soc:.1f}%]')
            await self.change_state(new_state, target_soc)

            if self.unsuspend:
                self.unsuspend = False

    async def check_suspend_switch(self):
        # Checks the "Limit Managed Battery Charge Voltage" switch.
        # If just activated, changes to the Suspended state.
        # If just deactivated, restarts the normal daily schedule.

        cvl = await self.system.charge_voltage_limit()
        switch = cvl != 0.0

        # Not suspended, but switch has been activated
        if self.state != State.Suspended and switch:
            await self.change_state(State.Suspended)

        # Already suspended, but switch has just been deactivated
        if self.state == State.Suspended and not switch:
            self.unsuspend = True
            self.previous_now = None    # reset the daily schedule

    async def change_state(self, new_state, target_soc=50.0):
        # Transitions to a new state.

        # Settings
        msg = ''
        self.count = 0
        self.update_interval = 1.0
        self.target_soc = target_soc

        # Charging State charges the battery at a fixed rate until a target SoC is reached
        if new_state == State.Charging:
            msg = f'# [Battery Charging] [Grid Connected] [Target SoC {target_soc:.1f}%]'
            self.charge_target_met = False

        # Maintaining State charges or discharges the battery until a target SoC is reached
        elif new_state == State.Maintaining:
            msg = f'# [Battery Maintaining] [Grid Connected]'
            self.charge_target_met = False
            self.discharge_target_met = False

        # PV Monitoring state charges the battery based on available PV
        elif new_state == State.MonitorPVCharging:
            msg = f'# [PV Monitoring] [Grid Connected]'
            self.pv_monitor_limit = 2.0         # Adjusted dynamically (Amps)
            self.update_interval = 1.0

        # Discharging State discharges the battery using only Critical Loads until a target SoC is reached
        elif new_state == State.Discharging:
            msg = f'# [Battery Discharging] [Grid Disconnected] [Target SoC {target_soc:.1f}%]'
            self.discharge_target_met = False

        # SoC Monitoring state charges the battery based on available PV, disconnecting grid above target SoC
        elif new_state == State.MonitorSoC:
            msg = f'# [SoC Monitoring] [Target SoC {target_soc:.1f}%]'
            self.pv_monitor_limit = 2.0         # Adjusted dynamically (Amps)

        # Check SoC state checks for BMS SoC drift and recharges if necessary
        elif new_state == State.CheckSoC:
            msg = f'# [Check SoC] [Target SoC {target_soc:.1f}%]'

        # Suspended state does nothing
        elif new_state == State.Suspended:
            msg = f'# [Suspended]'

        # A change of state has occurred
        if new_state != self.state:
            print(msg)
            self.state = new_state

    async def control(self):
        # Implements the control function called repeatedly by the main control loop at 1 Hz.
        # All states are handled here.

        # Check "Limit Managed Battery Charge Voltage" switch to suspend/resume operation
        await self.check_suspend_switch()

        # Check daily schedule to see if change in state is needed
        await self.check_daily_schedule()

        # Get Critical Loads Power usage
        self.output_power = await self.quattro.output_power_watts()       # total, L1, L2

        # Estimate inverter/charger efficiency at this total output power level
        self.efficiency = self.quattro.estimated_efficiency(self.output_power[0])

        # Get current battery State of Charge
        self.current_soc = await self.main_shunt.state_of_charge()
        self.charge_current = await self.main_shunt.current_amps()
        self.battery_soc = await self.battery.state_of_charge()

        # Get available PV DC Power and Current
        self.pv_dc_power = await self.all_mppt.total_dc_power()
        self.pv_dc_current = await self.all_mppt.total_dc_current()

        # Calculate estimated AC power that can be created using inverter at the current efficiency
        self.pv_power = self.efficiency * self.pv_dc_power / 100.0

        # Average Critical Loads and PV Power over 10 minutes
        if self.count > 0:
            alpha = math.exp(-1.0 / 600.0)   # 600 seconds = 10 minute time constant
            self.avg_output_power = (1.0 - alpha) * self.output_power[0] + alpha * self.avg_output_power
            self.avg_pv_power = (1.0 - alpha) * self.pv_power + alpha * self.avg_pv_power
        else:
            self.avg_output_power = self.output_power[0]
            self.avg_pv_power = self.pv_power

        # State: Charging Battery
        if self.state == State.Charging:
            await self.charging()

        # State: Maintaining Battery
        elif self.state == State.Maintaining:
            await self.maintaining()

        # State: Monitoring PV Charging
        elif self.state == State.MonitorPVCharging:
            await self.monitoring_pv_charging()

        # State: Discharging Battery
        elif self.state == State.Discharging:
            await self.discharging()

        # State: Monitoring SoC
        elif self.state == State.MonitorSoC:
            await self.monitoring_soc()

        # State: Check SoC
        elif self.state == State.CheckSoC:
            await self.check_soc()

        # State: Suspended
        elif self.state == State.Suspended:
            await self.suspended()

        # Increment counter
        self.count += 1

    async def charging(self):
        # Connects to the Grid to charge the batteries up to a target SoC.
        # If PV power is also available, it is prioritized.
        #
        # When the target SoC is reached, the charging current is reduced to zero,
        # but the grid remains connected.

        # Connect to Grid
        await self.connect_to_grid(True)

        # Done charging when target SoC has been reached
        target_met = self.current_soc >= self.target_soc
        if target_met:
            if not self.charge_target_met:
                await self.set_max_charge_current(0.0)
                self.charge_target_met = True

        # Not done charging, charge as fast a possible
        else:
            await self.set_max_charge_current(self.charge_limit_amps)

        if self.verbose:
            status = 'Not Charging' if self.charge_target_met else 'Charging'
            max_charge = await self.get_max_charge_current()
            print(f'{self.time_now} [{status}] [Grid Connected] '
                  f'[SoC {self.current_soc:5.1f}%] [Target {self.target_soc:5.1f}%] '
                  f'[Max Charge Current {max_charge:.0f} A]')

    async def maintaining(self):
        # Connects to the Grid, but disables battery charging from both Grid and PV.

        # Only set the charge current once, allowing user to override in the GUI
        if self.count == 0:
            await self.connect_to_grid(True)
            await self.set_max_charge_current(0.0)

        # If user disconnected from grid in the GUI, and the SoC is getting too low, reconnect to the grid
        grid_connected = await self.is_grid_connected()
        if not grid_connected and self.current_soc <= self.target_soc:
            await self.connect_to_grid(True)
            await self.set_max_charge_current(0.0)

        if self.verbose:
            connected = '[Grid Connected]' if grid_connected else '[Grid Disconnected]'
            max_charge = await self.get_max_charge_current()

            print(f'{self.time_now} [Maintaining] {connected} '
                  f'[SoC {self.current_soc:5.1f}%] [Max Charge Current {max_charge:.0f} A] ')

    async def monitoring_pv_charging(self):
        # Connects to the Grid, continuously adjusting the maximum charge current
        # based on the amount of PV power available.
        # Detects throttling of the MPPTs and raises the current limit as necessary.
        # Minimizes use of Grid power to recharge the batteries.

        # Connect to Grid
        await self.connect_to_grid(True)

        # Monitor PV current and adjust the DVCC maximum charge current
        mppt_modes, is_limited, is_off = await self.monitoring_pv()

        if self.verbose:
            print(f'{self.time_now} [PV Monitoring] [Grid Connected] [SoC {self.current_soc:5.1f}%] '
                  f'[Max Charge Current {self.pv_monitor_limit:.0f} A] [PV DC {self.pv_dc_current:.1f} A] '
                  f'[MPPT {mppt_modes[0]} {mppt_modes[1]}] [{self.pv_monitor_delay}]')

    async def monitoring_pv(self):
        # Adjusts the DVCC maximum charge current based on available PV current.
        # When the MPPTs are Off, the charge limit is set to 1A to allow MPPTs to wake up in the morning.
        # When the MPPTs are Limited, doubles the max charge current and waits to see the result.
        # The doubling continues until all MPPTs are Active. Then the current is adjusted properly.
        # When the MPPTs are Active, the max charge current is set to the available PV current.

        # Check PV modes
        mppt_modes = await self.all_mppt.get_mppt_modes()
        is_limited = mppt_modes[0] == 'Limited' or mppt_modes[1] == 'Limited'
        is_off = mppt_modes[0] == 'Off' and mppt_modes[1] == 'Off'

        # MPPTs are off: Turn off charging
        if is_off:
            self.pv_monitor_limit = 1.0   # zero will never wake up MPPTs in morning
            self.pv_monitor_delay = 0

        # Active MPPTs: Set the current limit to the available DC current
        elif not is_limited:
            self.pv_monitor_limit = self.pv_dc_current + 5.0
            self.pv_monitor_delay = 0

        # Limited MPPTs: Increase the current limit and start the delay counter, waiting to see what happens
        elif self.pv_monitor_delay == 0:
            self.pv_monitor_limit *= 2.0
            self.pv_monitor_delay = 10

        # Decrement the delay counter
        if self.pv_monitor_delay > 0:
            self.pv_monitor_delay -= 1

        # Set the DVCC charging limit
        self.pv_monitor_limit = min(self.pv_monitor_limit, self.pv_charge_limit_amps)
        await self.set_max_charge_current(self.pv_monitor_limit)

        # Return the MPPT status
        return mppt_modes, is_limited, is_off

    async def discharging(self):
        # Disconnects from the Grid to discharge the batteries down to a target SoC
        # by powering the Critical Loads through the inverters.
        # If PV power is also available, it is prioritized.
        #
        # Transitions to MonitorSoC state when the target SoC has been reached,
        # and reconnects to the Grid if below the target.

        # Disconnect from Grid, allow PV to charge batteries
        await self.connect_to_grid(False)
        await self.set_max_charge_current(self.charge_limit_amps)

        # Done discharging when target SoC has been reached
        target_met = self.current_soc <= self.target_soc
        if target_met:
            if not self.discharge_target_met:
                self.discharge_target_met = True
                await self.change_state(State.MonitorSoC, self.monitoring_target_soc)

        if self.verbose:
            status = 'Not Discharging' if self.discharge_target_met else 'Discharging'
            print(f'{self.time_now} [{status}] [Critical Loads {self.output_power[0]:4.0f} W] '
                  f'[PV Power {self.pv_power:.0f} W] '
                  f'[SoC {self.current_soc:5.1f}%] [Target {self.target_soc:5.1f}%]')

    async def monitoring_soc(self):
        # Uses only PV to charge the batteries up to the target State of Charge.
        # Above the target SoC, disconnects from the Grid if PV power is adequate for the loads.
        # Also disconnects from the Grid if the SoC is higher than 90% to avoid filling the batteries.
        # If insufficient PV power is available and the SoC falls below the target SoC - hysteresis,
        # the Grid is reconnected and the batteries are then recharged from PV.
        # The Grid is never used to charge the batteries in this state, only PV power is used.

        is_grid_connected = await self.is_grid_connected()

        # ----- Grid is currently connected -----
        if is_grid_connected:

            # Monitor PV current and adjust the DVCC maximum charge current
            mppt_modes, is_limited, is_off = await self.monitoring_pv()

            # Current State of Charge meets or exceeds target SoC
            if self.current_soc >= self.target_soc:

                # Current PV power is sufficient to power current inverter loads, disconnect from Grid
                # or if current SoC > 90%, in order to burn off some SoC to prevent filling the batteries
                if self.avg_pv_power > self.avg_output_power or self.current_soc >= self.hi_soc:
                    await self.connect_to_grid(False)

            if self.verbose:
                max_charge = await self.get_max_charge_current()

                print(f'{self.time_now} [SoC Monitoring] [Grid Connected] '
                      f'[SoC {self.current_soc:5.1f}% {self.target_soc:5.1f}%] '
                      f'[Max Charge {max_charge:.0f} A] [PV DC {self.pv_dc_current:.1f} A] '
                      f'[MPPT {mppt_modes[0]} {mppt_modes[1]}] '
                      f'[Avg PV Power {self.avg_pv_power:.0f} W] [Avg Loads {self.avg_output_power:.0f} W]')

        # ----- Grid is currently disconnected -----
        else:
            # DVCC charging limit
            await self.set_max_charge_current(self.pv_charge_limit_amps)

            # Current State of Charge has fallen below target SoC - hysteresis
            if self.current_soc < (self.target_soc - self.hysteresis):
                await self.connect_to_grid(True)

            if self.verbose:
                charge = f'[Charging {self.charge_current:.1f} A]' if self.charge_current >= 0.0 else \
                         f'[Discharging {-self.charge_current:.1f} A]'

                print(f'{self.time_now} [SoC Monitoring] [Grid Disconnected] '
                      f'[SoC {self.current_soc:5.1f}% {self.target_soc:5.1f}%] '
                      f'{charge} [PV DC {self.pv_dc_current:.1f} A] '
                      f'[PV Power {self.pv_power:.0f} W] [Loads {self.output_power[0]:.0f} W] '
                      f'[Eff {self.efficiency:4.1f} %]')

    async def check_soc(self):
        # Checks the difference between the battery BMS SoC and the shunt SoC.
        # If the difference is acceptable, simply transitions back the MonitoringSoC state.
        # If the threshold is exceeded, starts recharging the batteries to 100% to reset the BMS.
        # When completed, transitions back to the MonitoringSoC state.

        # Check for excessive battery BMS SoC missmatch with shunt SoC
        soc_error = self.current_soc - self.battery_soc

        # If difference is under threshold, transition immediately back to MonitoringSoC state
        if not self.check_recharging and abs(soc_error) < self.soc_error_threshold:
            await self.change_state(State.MonitorSoC, self.monitoring_target_soc)
            if self.verbose:
                print(f'{self.time_now} [Check SoC] [SoC {self.current_soc:5.1f}%] [SoC Error {soc_error:5.1f}%]')
            return

        # Connect to grid and set charge current once
        if not self.check_recharging:
            await self.connect_to_grid(True)
            await self.set_max_charge_current(self.recharge_current)
            self.check_recharging = True

        # Battery BMS SoC has reached 100% SoC, done recharging, so transition back to MonitoringSoC state
        elif self.battery_soc == 100.0:
            self.check_recharging = False
            await self.change_state(State.MonitorSoC, self.monitoring_target_soc)

        if self.verbose:
            max_charge = await self.get_max_charge_current()

            print(f'{self.time_now} [Check SoC Recharging] [Grid Connected] '
                  f'[SoC {self.current_soc:5.1f}%] [BMS SoC {self.battery_soc:5.1f}%] '
                  f'[Max Charge Current {max_charge:.0f} A]')

    async def suspended(self):
        # Called when in the Suspended state
        is_grid_connected = await self.is_grid_connected()
        grid_status = '[Grid Connected]' if is_grid_connected else '[Grid Disconnected]'
        max_charge = await self.get_max_charge_current()

        print(f'{self.time_now} [Suspended] {grid_status} '
              f'[SoC {self.current_soc:5.1f}%] [Max Charge Current {max_charge:.0f} A]')

    async def connect_to_grid(self, yes_no):
        state = await self.system.relay_1_state()
        if yes_no != state:
            await self.system.set_relay_1(yes_no)

    async def is_grid_connected(self):
        return await self.system.relay_1_state()

    async def set_max_charge_current(self, amps):
        amps = int(amps + 0.9)
        a = await self.system.dvcc_max_charge_current_amps()
        if a != amps:
            await self.system.set_dvcc_max_charge_current_amps(amps)

    async def get_max_charge_current(self):
        return await self.system.dvcc_max_charge_current_amps()

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


if __name__ == "__main__":
    # Run the main_control_loop() if this file is executed directly

    # Default settings
    startup_state = State.Undefined
    tsoc = 40.0
    do_schedule = False

    n = len(sys.argv)
    if n > 1:

        # Connect to Grid, Charging Batteries to Target SoC
        if sys.argv[1] == 'charge':
            startup_state = State.Charging
            tsoc = float(sys.argv[2]) if n > 2 else 40.0

        # Disconnect from Grid, Discharging Batteries to Target SoC
        elif sys.argv[1] == 'discharge':
            startup_state = State.Discharging
            tsoc = float(sys.argv[2]) if n > 2 else 15.0

        # Connect to Grid, minimize battery charging
        elif sys.argv[1] == 'maintain':
            startup_state = State.Maintaining

        # Connect to Grid, charge battery based on available PV, minimize grid use
        elif sys.argv[1] == 'pvmonitor':
            startup_state = State.MonitorPVCharging

        # Charge batteries using PV to target SoC, disconnect from Grid above target
        elif sys.argv[1] == 'monitor':
            startup_state = State.MonitorSoC

        # Run the daily schedule
        elif sys.argv[1] == 'schedule':
            startup_state = State.Undefined
            do_schedule = True

    # Run the main control loop
    no_ess_schedule = NoESSSchedule()
    asyncio.run(no_ess_schedule.main_control_loop(startup_state, target_soc=tsoc, use_schedule=do_schedule))
