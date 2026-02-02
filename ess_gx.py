# -------------------------------------------------------------------------------------------------------------------
# Implements a class to interact with the Victron ESS controlled by the Cerbo GX device using ModbusTCP.
# Displays and logs overall status of the entire system every second.
#
# This implementation is specific to the ricardocello Victron ESS configuration.
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

import sys
import time
import asyncio

from modbus_tcp_client import ModbusTCPClient

import cerbo_gx
import settings_gx
import system_gx
import grid_gx
import quattro_gx
import battery_gx
import mppt_gx
import temperature_gx
import shunt_gx
import acload_gx

from ess_log import *
from ess_status_display import *


class ESS:

    # ----- ANSI Colors -----
    RED = '\x1b[31m'
    GREEN = '\x1b[32m'
    BLUE = '\x1b[34m'
    YELLOW = '\x1b[33m'
    CYAN = '\x1b[36m'
    NORM = '\x1b[0m'
    HOME = '\x1b[H'
    CLEAR = '\x1b[2J'

    def __init__(self, addr=settings_gx.GX_IP_ADDRESS):
        # Object for each device used on the Cerbo GX
        self.gx = cerbo_gx.CerboGX(addr)                             # Victron Cerbo GX
        self.system = system_gx.System(addr)                         # System Parameters on Cerbo GX
        self.grid = grid_gx.GridMeter(addr)                          # Carlo Gavazzi EM530
        self.quattro = quattro_gx.Quattros(addr)                     # 2x Quattro 48|5000|70-100|100 120V Split-Phase
        self.battery = battery_gx.Battery(addr)                      # 3x EG4-LL v1 modules in parallel, CANbus BMS
        self.main_shunt = shunt_gx.MainShunt(addr)                   # Main SmartShunt used as a battery monitor
        self.cv_shunt = shunt_gx.ChargeverterShunt(addr)             # Chargerverter SmartShunt as DC source
        self.all_mppt = mppt_gx.AllMPPT(addr)                        # 2x Victron SmartSolar MPPTs (250/70, 250/100)
        self.rack_temp = temperature_gx.RackTemperature(addr)        # Rack Temperature Sensor
        self.cv_temp = temperature_gx.ChargeverterTemperature(addr)  # Chargeverter Temperature Sensor
        self.addition = acload_gx.AdditionEnergyMeter(addr)          # Addition Energy Meter from UDP broadcast
        self.house = acload_gx.HouseEnergyMeter(addr)                # Main House Energy Meter from UDP broadcast

        # Display
        self.display = None                           # Color Status Display

        # Log File
        self.log_file = None                          # Log file being written
        self.playback_reader = None                   # Used for playback of log files only

        # Timestamps
        self.starting_date = None                     # Date when this run started
        self.timestamp = None                         # Current timestamp

        # Statistics
        self.ess_stats = ESSStats()

        # ----- Grid -----
        self.grid_power = None                        # (total, L1, L2) Watts
        self.grid_house_power = None                  # (total, L1, L2) Watts
        self.grid_addition_power = None               # (total, L1, L2) Watts
        self.grid_voltage = None                      # (total, L1, L2)
        self.grid_power_factor = None                 # (L1, L2)
        self.grid_frequency = None                    # Hz

        # ----- Inverters -----
        self.inverter_ac_total_power = None           # (total, L1, L2) Watts
        self.inverter_ac_input_power = None           # (total, L1, L2) Watts
        self.inverter_ac_output_power = None          # (total, L1, L2) Watts
        self.inverter_input_power_factor = None       # (total, L1, L2) Watts
        self.inverter_output_power_factor = None      # (total, L1, L2) Watts
        self.inverter_ess_power_limit = None          # Watts
        self.inverter_efficiency = None               # (mode, efficiency pct)
        self.inverter_state = None                    # Bulk, Absorption, Float, etc.
        self.inverter_warnings_alarms = None          # active warnings or alarms
        self.inverter_rack_temperature = None         # deg C

        # ----- AC Consumption -----
        self.ac_consumption = None                    # (total, L1, L2) Watts
        self.ac_house_consumption = None              # (total, L1, L2) Watts
        self.ac_critical_load_consumption = None      # (total, L1, L2) Watts
        self.ac_addition_consumption = None           # (total, L1, L2) Watts
        self.ac_battery_charger_consumption = None    # (total, L1, L2) Watts

        # ----- PV Solar -----
        self.pv_power = None                          # (total, 250/100, 250/70) Watts
        self.pv_dc_current = None                     # (total, 250/100, 250/70) Amps
        self.pv_energy_yield_today = None             # (total, 250/100, 250/70) kWh
        self.pv_efficiency = None                     # (total, 250/100, 250/70) %
        self.pv_power_lost = None                     # (total, 250/100, 250/70) Watts
        self.pv_net_efficiency = None                 # %
        self.pv_voltage = None                        # (250/100, 250/70) Volts
        self.pv_current = None                        # (250/100, 250/70) Amps
        self.pv_opmode = None                         # Off, Active, Limited, Unknown

        # ----- Battery -----
        self.battery_soc = None                       # (% shunt, % bms)
        self.battery_voltage = None                   # (Shunt, BMS) Volts
        self.battery_cell_voltages = None             # (min, max) Volts
        self.battery_temperature = None               # deg C
        self.battery_blocking = None                  # (# of modules, # of charge block, # of discharge block)
        self.battery_charge_current = None            # Amps
        self.battery_power = None                     # Watts
        self.battery_power_lost = None                # Watts

        # ----- Chargeverter -----
        self.chargeverter_power = None                # Watts
        self.chargeverter_volts = None                # Volts at shunt
        self.chargeverter_current = None              # Amps through shunt
        self.chargeverter_temp = None                 # deg C

    async def connect(self):
        # Connects to the Cerbo GX attached devices

        await self.gx.connect()           # Victron Cerbo GX
        await self.system.connect()       # System Parameters on Cerbo GX
        await self.grid.connect()         # Carlo Gavazzi EM530
        await self.quattro.connect()      # 2x Victron Quattro 48|5000|70-100|100 120V Split-Phase
        await self.battery.connect()      # 3x EG4-LL v1 modules in parallel, CANbus BMS
        await self.main_shunt.connect()   # SmartShunt used as battery monitor, VE.Direct
        await self.cv_shunt.connect()     # SmartShunt used as Chargeverter power monitor, VE.Direct
        await self.all_mppt.connect()     # SmartSolar VE.Can MPPT 250/70 and 250/100
        await self.rack_temp.connect()    # Rack Temperature Sensor
        await self.cv_temp.connect()      # Chargeverter Temperature Sensor
        await self.addition.connect()     # Addition Energy Meter
        await self.house.connect()        # House Energy Meter

        # Create the log file
        self.create_log_file()

    async def disconnect(self):
        # Disconnects from the Cerbo GX attached devices

        await self.gx.disconnect()  # Victron Cerbo GX
        await self.system.disconnect()  # System Parameters on Cerbo GX
        await self.grid.disconnect()  # Carlo Gavazzi EM530
        await self.quattro.disconnect()  # 2x Victron Quattro 48|5000|70-100|100 120V Split-Phase
        await self.battery.disconnect()  # 3x EG4-LL v1 modules in parallel, CANbus BMS
        await self.main_shunt.disconnect()  # SmartShunt used as battery monitor, VE.Direct
        await self.cv_shunt.disconnect()  # SmartShunt used as Chargeverter power monitor, VE.Direct
        await self.all_mppt.disconnect()  # SmartSolar VE.Can MPPT 250/70 and 250/100
        await self.rack_temp.disconnect()  # Rack Temperature Sensor
        await self.cv_temp.disconnect()  # Chargeverter Temperature Sensor
        await self.addition.disconnect()  # Addition Energy Meter
        await self.house.disconnect()  # House Energy Meter

    def create_log_file(self, logfile='ess.log'):
        # Close any existing file, triggering writing a new one (change of day)
        if self.log_file:
            self.log_file.file.close()
            self.log_file.file = None

        # Create the log file
        self.log_file = ESSLogWriter(logfile)
        if self.log_file.create_or_update_file():
            self.ess_stats.clear()    # clear statistics if a new file was just created

        # Read statistics from existing log file
        self.get_statistics_from_existing_logfile(logfile)

        # Save the Starting Date to know when to archive at end of day
        ts = datetime.now()
        self.starting_date = ts.strftime('%Y-%m-%d')

        # Timestamp column
        self.log_file.add_timestamp_column()

        # ----- Grid -----
        self.log_file.add_power_columns('Grid Power (W)')
        self.log_file.add_power_columns('Grid House Power (W)')
        self.log_file.add_power_columns('Grid Addition Power (W)')
        self.log_file.add_column('Grid Voltage', ':.1f')
        self.log_file.add_column('L1 Grid Voltage', ':.1f')
        self.log_file.add_column('L2 Grid Voltage', ':.1f')
        self.log_file.add_column('L1 Grid Power Factor', ':.2f')
        self.log_file.add_column('L2 Grid Power Factor', ':.2f')
        self.log_file.add_column('Grid Frequency (Hz)', ':.2f')

        # ----- Inverter -----
        self.log_file.add_power_columns('Total Inverter Power (W)')
        self.log_file.add_power_columns('Inverter Input Power (W)')
        self.log_file.add_power_columns('Inverter Output Power (W)')
        self.log_file.add_pf_columns('Inverter Input Power Factor')
        self.log_file.add_pf_columns('Inverter Output Power Factor')
        self.log_file.add_column('ESS Power Limit (W)', ':.0f')
        self.log_file.add_column('Inverter Efficiency (%)', ':.1f')
        self.log_file.add_column('Inverter State')
        self.log_file.add_column('Active Warnings and Alarms')
        self.log_file.add_column('Inverter Temperature (°C)', ':.1f')

        # ----- AC Consumption -----
        self.log_file.add_power_columns('Total AC Consumption (W)')
        self.log_file.add_power_columns('AC Critical Loads (W)')
        self.log_file.add_power_columns('AC House Consumption (W)')
        self.log_file.add_power_columns('AC Addition Consumption (W)')
        self.log_file.add_power_columns('AC Battery Chargers (W)')

        # ----- PV Solar -----
        self.log_file.add_pv_columns('PV Power (W)')
        self.log_file.add_pv_columns('PV DC Current (A)')
        self.log_file.add_pv_columns('PV Yield Today (kWh)')
        self.log_file.add_pv_columns('PV Efficiency (%)')
        self.log_file.add_pv_columns('PV Power Lost (W)')
        self.log_file.add_column('PV Net Efficiency (%)', ':.1f')
        self.log_file.add_2pv_columns('PV Voltage (V)')
        self.log_file.add_2pv_columns('PV Current (A)')
        self.log_file.add_2pv_columns('PV MPPT Mode', '')

        # ----- Battery -----
        self.log_file.add_column('Shunt SoC (%)', ':.1f')
        self.log_file.add_column('BMS SoC (%)', ':.1f')
        self.log_file.add_column('Shunt Voltage (V)', ':.2f')
        self.log_file.add_column('BMS Voltage (V)', ':.2f')
        self.log_file.add_column('Min Cell Voltage (V)', ':.2f')
        self.log_file.add_column('Max Cell Voltage (V)', ':.2f')
        self.log_file.add_column('Battery Temperature (°C)', ':.1f')
        self.log_file.add_column('Battery Status')
        self.log_file.add_column('Shunt Charge Current (A)', ':.1f')
        self.log_file.add_column('Shunt Power (W)', ':.0f')
        self.log_file.add_column('Battery Cable Power Loss (W)', ':.0f')

        # ----- Chargeverter -----
        self.log_file.add_column('Chargeverter Power (W)', ':.1f')
        self.log_file.add_column('Chargeverter Current (A)', ':.1f')
        self.log_file.add_column('Chargeverter Temperature (°C)', ':.1f')

        # Write the log file header
        self.log_file.log_header()

    def update_log_file(self):
        # Writes the current values to the log file if it is open
        if self.log_file is None:
            return
        lf = self.log_file

        # ----- Grid -----
        lf.set_power_values('Grid Power (W)', self.grid_power)
        lf.set_power_values('Grid House Power (W)', self.grid_house_power)
        lf.set_power_values('Grid Addition Power (W)', self.grid_addition_power)
        lf.set_row_value('Grid Voltage', self.grid_voltage[0])
        lf.set_row_value('L1 Grid Voltage', self.grid_voltage[1])
        lf.set_row_value('L2 Grid Voltage', self.grid_voltage[2])
        lf.set_row_value('L1 Grid Power Factor', self.grid_power_factor[0])
        lf.set_row_value('L2 Grid Power Factor', self.grid_power_factor[1])
        lf.set_row_value('Grid Frequency (Hz)', self.grid_frequency)

        # ----- Inverter -----
        lf.set_power_values('Total Inverter Power (W)', self.inverter_ac_total_power)
        lf.set_power_values('Inverter Input Power (W)', self.inverter_ac_input_power)
        lf.set_power_values('Inverter Output Power (W)', self.inverter_ac_output_power)
        lf.set_pf_values('Inverter Input Power Factor', self.inverter_input_power_factor)
        lf.set_pf_values('Inverter Output Power Factor', self.inverter_output_power_factor)
        lf.set_row_value('ESS Power Limit (W)', self.inverter_ess_power_limit)
        lf.set_row_value('Inverter Efficiency (%)', self.inverter_efficiency[1])
        lf.set_row_value('Inverter State', self.inverter_state)
        lf.set_row_value('Active Warnings and Alarms', self.inverter_warnings_alarms)
        lf.set_row_value('Inverter Temperature (°C)', self.inverter_rack_temperature)

        # ----- AC Consumption -----
        lf.set_power_values('Total AC Consumption (W)', self.ac_consumption)
        lf.set_power_values('AC Critical Loads (W)', self.ac_critical_load_consumption)
        lf.set_power_values('AC House Consumption (W)', self.ac_house_consumption)
        lf.set_power_values('AC Addition Consumption (W)', self.ac_addition_consumption)
        lf.set_power_values('AC Battery Chargers (W)', self.ac_battery_charger_consumption)

        # ----- PV Solar -----
        lf.set_pv_values('PV Power (W)', self.pv_power)
        lf.set_pv_values('PV DC Current (A)', self.pv_dc_current)
        lf.set_pv_values('PV Yield Today (kWh)', self.pv_energy_yield_today)
        lf.set_pv_values('PV Efficiency (%)', self.pv_efficiency)
        lf.set_pv_values('PV Power Lost (W)', self.pv_power_lost)
        lf.set_row_value('PV Net Efficiency (%)', self.pv_net_efficiency)
        lf.set_2pv_values('PV Voltage (V)', self.pv_voltage)
        lf.set_2pv_values('PV Current (A)', self.pv_current)
        lf.set_2pv_values('PV MPPT Mode', self.pv_opmode)

        # ----- Battery -----
        lf.set_row_value('Shunt SoC (%)', self.battery_soc[0])
        lf.set_row_value('BMS SoC (%)', self.battery_soc[1])
        lf.set_row_value('Shunt Voltage (V)', self.battery_voltage[0])
        lf.set_row_value('BMS Voltage (V)', self.battery_voltage[1])
        lf.set_row_value('Min Cell Voltage (V)', self.battery_cell_voltages[0])
        lf.set_row_value('Max Cell Voltage (V)', self.battery_cell_voltages[1])
        lf.set_row_value('Battery Temperature (°C)', self.battery_temperature)
        lf.set_row_value('Battery Status', self.battery_blocking)
        lf.set_row_value('Shunt Charge Current (A)', self.battery_charge_current)
        lf.set_row_value('Shunt Power (W)', self.battery_power)
        lf.set_row_value('Battery Cable Power Loss (W)', self.battery_power_lost)

        # ----- Chargeverter -----
        lf.set_row_value('Chargeverter Power (W)', self.chargeverter_power)
        lf.set_row_value('Chargeverter Current (A)', self.chargeverter_current)
        lf.set_row_value('Chargeverter Temperature (°C)', self.chargeverter_temp)

        # Write the line to the log file
        lf.log_row()

    async def gather_cerbo_info(self):
        # Gathers the info from the Cerbo GX attached devices and writes to the log file
        # This is typically called every second.
        #
        # Handles the change of day by compressing and archiving the existing log file, and
        # starting a new log file.

        # Timestamp
        ts = datetime.now()
        self.timestamp = ts.strftime('%Y-%m-%d %H:%M:%S')

        # Change of Day: Close the existing file, compress and archive it, create a new one
        current_date = ts.strftime('%Y-%m-%d')
        if current_date != self.starting_date:
            # Close the current log file, create a new log file
            self.create_log_file()

            # Get new timestamp, because compressing and archiving take time
            ts = datetime.now()
            self.timestamp = ts.strftime('%Y-%m-%d %H:%M:%S')

        # ----- Grid -----
        self.grid_power = await self.grid.power_watts()
        self.grid_house_power = await self.house.power_watts()
        self.grid_addition_power = await self.addition.power_watts()
        self.grid_voltage = await self.grid.voltage()
        self.grid_power_factor = await self.grid.power_factor()
        self.grid_frequency = await self.grid.frequency_hz()

        # ----- Inverters -----
        self.inverter_ac_input_power = await self.quattro.input_power_watts()
        self.inverter_ac_output_power = await self.quattro.output_power_watts()

        # Calculate total AC power from inverters
        diff = [self.inverter_ac_output_power[i] - self.inverter_ac_input_power[i] for i in range(3)]
        self.inverter_ac_total_power = \
            [diff[i] if diff[i] > 0 else 0 for i in range(3)]

        self.inverter_input_power_factor = await self.quattro.input_power_factor()
        self.inverter_output_power_factor = await self.quattro.output_power_factor()
        self.inverter_ess_power_limit = round(await self.system.inverter_power_limit_watts())
        self.inverter_efficiency = await self.quattro.calculate_efficiency()
        self.inverter_state = await self.quattro.state_string()
        self.inverter_warnings_alarms = await self.quattro.active_warnings_alarms()
        self.inverter_rack_temperature = await self.rack_temp.degrees_c()

        # ----- AC Consumption -----
        self.ac_consumption = await self.system.ac_consumption_watts()
        self.ac_critical_load_consumption = self.inverter_ac_output_power
        self.ac_addition_consumption = self.grid_addition_power

        # Calculate AC house consumption by excluding Addition power and house critical loads power
        diff = [self.ac_consumption[i] - self.inverter_ac_output_power[i] - self.ac_addition_consumption[i]
                for i in range(3)]
        self.ac_house_consumption = [diff[i] if diff[i] > 0 else 0 for i in range(3)]
        self.ac_house_consumption[0] = self.ac_house_consumption[1] + self.ac_house_consumption[2]

        # Calculate AC consumption when charging batteries (not counted in total above)
        diff = [self.inverter_ac_input_power[i] - self.inverter_ac_output_power[i] for i in range(3)]
        self.ac_battery_charger_consumption = \
            [diff[i] if diff[i] > 0 else 0 for i in range(3)]

        # ----- PV Solar -----
        self.pv_opmode = await self.all_mppt.get_mppt_modes()
        self.pv_power, self.pv_voltage, self.pv_current, \
            dc_w, dc_v, self.pv_dc_current, self.pv_energy_yield_today, self.pv_efficiency = \
            await self.all_mppt.read_pv_dc_values()
        self.pv_net_efficiency = 0.0 if self.inverter_efficiency[0] == 'Charger' else \
            self.pv_efficiency[0] * self.inverter_efficiency[1] / 100.0

        # ----- Battery -----
        self.battery_power, shunt_v, self.battery_charge_current, shunt_soc = await self.main_shunt.dc_info()
        soc = await self.battery.state_of_charge()
        self.battery_soc = (shunt_soc, soc)  # Both SoCs in a tuple

        batt_v = await self.battery.voltage()
        self.battery_voltage = (shunt_v, batt_v)  # Both voltages

        self.battery_temperature = await self.battery.degrees_c()
        self.battery_cell_voltages = await self.battery.cell_voltages()

        # Calculate battery power lost in cables and fuses with voltage drop and current
        self.battery_power_lost = round(abs((shunt_v - batt_v) * self.battery_charge_current))

        # BMS blocking charge/discharge string
        block = await self.battery.blocking_modules()
        if block[1] == 0 and block[2] == 0:
            msg = f'Normal ({block[0]})'
        else:
            msg = f'{block[1]}/{block[0]}  {block[2]}/{block[0]}'
        self.battery_blocking = msg

        # PV Solar power lost in cables (calculations needing the shunt info)
        self.pv_power_lost = [0, 0, 0]
        self.pv_power_lost[1] = round(abs(dc_v[0] - shunt_v) * self.pv_dc_current[1])
        self.pv_power_lost[2] = round(abs(dc_v[1] - shunt_v) * self.pv_dc_current[2])
        self.pv_power_lost[0] = self.pv_power_lost[1] + self.pv_power_lost[2]

        # ----- Chargeverter -----
        self.chargeverter_power, self.chargeverter_volts, self.chargeverter_current = await self.cv_shunt.dc_info()
        self.chargeverter_temp = await self.cv_temp.degrees_c()

        # Update the log tab-delimited log file
        self.update_log_file()

    def gather_playback_info(self):
        # Reads the current values from the playback log file if it is open
        # Returns 1 if at end of file, 0 otherwise
        if self.playback_reader is None:
            return 1

        # Get the values
        if self.playback_reader.read_next_row():
            return 1

        self.timestamp = self.playback_reader.get_string_value('Timestamp')

        # ----- Grid -----
        self.grid_power = self.playback_reader.get_power_values('Grid Power (W)')
        self.grid_house_power = self.playback_reader.get_power_values('Grid House Power (W)')
        self.grid_addition_power = self.playback_reader.get_power_values('Grid Addition Power (W)')
        self.grid_voltage = self.playback_reader.get_3float_values('Grid Voltage')
        l1_pf = self.playback_reader.get_float_value('L1 Grid Power Factor')
        l2_pf = self.playback_reader.get_float_value('L2 Grid Power Factor')
        self.grid_power_factor = (l1_pf, l2_pf)
        self.grid_frequency = self.playback_reader.get_float_value('Grid Frequency (Hz)')

        # ----- Inverter -----
        self.inverter_ac_total_power = self.playback_reader.get_power_values('Total Inverter Power (W)')
        self.inverter_ac_input_power = self.playback_reader.get_power_values('Inverter Input Power (W)')
        self.inverter_ac_output_power = self.playback_reader.get_power_values('Inverter Output Power (W)')

        self.inverter_input_power_factor = self.playback_reader.get_3float_values('Inverter Input Power Factor')
        self.inverter_output_power_factor = self.playback_reader.get_3float_values('Inverter Output Power Factor')

        self.inverter_ess_power_limit = self.playback_reader.get_int_value('ESS Power Limit (W)')
        eff = self.playback_reader.get_float_value('Inverter Efficiency (%)')
        self.inverter_efficiency = ('', eff)

        self.inverter_state = self.playback_reader.get_string_value('Inverter State')
        self.inverter_warnings_alarms = self.playback_reader.get_string_value('Active Warnings and Alarms')
        self.inverter_rack_temperature = self.playback_reader.get_float_value('Inverter Temperature (°C)')

        # ----- AC Consumption -----
        self.ac_consumption = self.playback_reader.get_power_values('Total AC Consumption (W)')
        self.ac_critical_load_consumption = self.playback_reader.get_power_values('AC Critical Loads (W)')
        self.ac_house_consumption = self.playback_reader.get_power_values('AC House Consumption (W)')
        self.ac_addition_consumption = self.playback_reader.get_power_values('AC Addition Consumption (W)')
        self.ac_battery_charger_consumption = self.playback_reader.get_power_values('AC Battery Chargers (W)')

        # ----- PV Solar -----
        self.pv_power = self.playback_reader.get_pv_values('PV Power (W)')
        self.pv_dc_current = self.playback_reader.get_pv_values('PV DC Current (A)')
        self.pv_energy_yield_today = self.playback_reader.get_pv_values('PV Yield Today (kWh)')
        self.pv_efficiency = self.playback_reader.get_pv_values('PV Efficiency (%)')

        p_lost = self.playback_reader.get_pv_values('PV Power Lost (W)')
        self.pv_power_lost = (int(p_lost[0]), int(p_lost[1]), int(p_lost[2]))

        self.pv_net_efficiency = self.playback_reader.get_float_value('PV Net Efficiency (%)')
        self.pv_voltage = self.playback_reader.get_2pv_values('PV Voltage (V)')
        self.pv_current = self.playback_reader.get_2pv_values('PV Current (A)')
        opmode_70 = self.playback_reader.get_string_value('250/70 PV MPPT Mode')
        opmode_100 = self.playback_reader.get_string_value('250/100 PV MPPT Mode')
        self.pv_opmode = (opmode_70, opmode_100)

        # ----- Battery -----
        soc_shunt = self.playback_reader.get_float_value('Shunt SoC (%)')
        soc_bms = self.playback_reader.get_float_value('BMS SoC (%)')
        self.battery_soc = (soc_shunt, soc_bms)

        v_shunt = self.playback_reader.get_float_value('Shunt Voltage (V)')
        v_bms = self.playback_reader.get_float_value('BMS Voltage (V)')
        self.battery_voltage = (v_shunt, v_bms)

        v_min = self.playback_reader.get_float_value('Min Cell Voltage (V)')
        v_max = self.playback_reader.get_float_value('Max Cell Voltage (V)')
        self.battery_cell_voltages = (v_min, v_max)

        self.battery_temperature = self.playback_reader.get_float_value('Battery Temperature (°C)')
        self.battery_blocking = self.playback_reader.get_string_value('Battery Status')
        self.battery_charge_current = self.playback_reader.get_float_value('Shunt Charge Current (A)')
        self.battery_power = self.playback_reader.get_int_value('Shunt Power (W)')
        self.battery_power_lost = self.playback_reader.get_int_value('Battery Cable Power Loss (W)')

        # ----- Chargeverter -----
        self.chargeverter_power = self.playback_reader.get_float_value('Chargeverter Power (W)')
        self.chargeverter_current = self.playback_reader.get_float_value('Chargeverter Current (A)')
        self.chargeverter_temp = self.playback_reader.get_float_value('Chargeverter Temperature (°C)')

        return 0

    def get_statistics_from_existing_logfile(self, logfile, stop_time=None):
        # Reads the entire logfile, updating the statistics objects for columns of interest

        print(f'# Reading existing log file {logfile} to gather statistics...')
        rlf = ESSLogReader(logfile)
        rlf.open_file()

        stop_tick = 0
        if stop_time:
            stop_hms = stop_time.split(':')
            stop_tick = stop_hms[0] * 3600 + stop_hms[1] * 60 + stop_hms[2]

        while not rlf.read_next_row():

            # Check the time
            if stop_time:
                ts = rlf.get_string_value('Timestamp').split(' ')
                hms = ts.split(':')
                tick = hms[0] * 3600 + hms[1] * 60 + hms[2]

                if tick > stop_tick:
                    break

            # ----- Grid -----
            self.ess_stats.next_grid((rlf.get_float_value(self.ess_stats.grid_power.name),
                                      rlf.get_float_value(self.ess_stats.grid_house_power.name),
                                      rlf.get_float_value(self.ess_stats.grid_addition_power.name),
                                      rlf.get_float_value(self.ess_stats.grid_voltage.name),
                                      rlf.get_float_value(self.ess_stats.grid_frequency.name)))

            # ----- Inverter -----
            self.ess_stats.next_inverter((rlf.get_float_value(self.ess_stats.inverter_ac_total_power.name),
                                          rlf.get_float_value(self.ess_stats.inverter_ac_input_power.name),
                                          rlf.get_float_value(self.ess_stats.inverter_ac_output_power.name),
                                          rlf.get_float_value(self.ess_stats.inverter_rack_temperature.name)))

            # ----- AC Consumption -----
            self.ess_stats.next_ac_consumption(
                (rlf.get_float_value(self.ess_stats.ac_consumption.name),
                 rlf.get_float_value(self.ess_stats.ac_critical_load_consumption.name),
                 rlf.get_float_value(self.ess_stats.ac_house_consumption.name),
                 rlf.get_float_value(self.ess_stats.ac_addition_consumption.name),
                 rlf.get_float_value(self.ess_stats.ac_battery_charger_consumption.name)))

            # ----- PV Solar -----
            self.ess_stats.next_pv_solar((rlf.get_float_value(self.ess_stats.pv_power.name),
                                          rlf.get_float_value(self.ess_stats.pv_dc_current.name),
                                          rlf.get_float_value(self.ess_stats.pv_voltage_250_70.name),
                                          rlf.get_float_value(self.ess_stats.pv_voltage_250_100.name)))

            # ----- Battery -----
            self.ess_stats.next_battery((rlf.get_float_value(self.ess_stats.battery_soc.name),
                                         rlf.get_float_value(self.ess_stats.battery_voltage.name),
                                         rlf.get_float_value(self.ess_stats.battery_temperature.name),
                                         rlf.get_float_value(self.ess_stats.battery_charge_current.name)))

        rlf.file.close()

    def update_statistics(self):
        # Updates the statistics (min, mean, max)
        # Should be called after playback_update() or gather_cerbo_info()

        # ----- Grid -----
        self.ess_stats.next_grid((self.grid_power[0],
                                  self.grid_house_power[0],
                                  self.grid_addition_power[0],
                                  self.grid_voltage[0],
                                  self.grid_frequency))

        # ----- Inverter -----
        self.ess_stats.next_inverter((self.inverter_ac_total_power[0],
                                      self.inverter_ac_input_power[0],
                                      self.inverter_ac_output_power[0],
                                      self.inverter_rack_temperature))

        # ----- AC Consumption -----
        self.ess_stats.next_ac_consumption((self.ac_consumption[0],
                                            self.ac_critical_load_consumption[0],
                                            self.ac_house_consumption[0],
                                            self.ac_addition_consumption[0],
                                            self.ac_battery_charger_consumption[0]))

        # ----- PV Solar -----
        self.ess_stats.next_pv_solar((self.pv_power[0], self.pv_dc_current[0],
                                      self.pv_voltage[0], self.pv_voltage[1]))

        # ----- Battery -----
        self.ess_stats.next_battery((self.battery_soc[0],
                                     self.battery_voltage[0],
                                     self.battery_temperature,
                                     self.battery_charge_current))

    def update_display(self):
        # Updates the color status display using the gathered information from the Cerbo or the playback file

        # Timestamp
        d = self.display
        d.name = f'ESS Status {self.timestamp}'

        # ----- Grid -----
        d.set_3_float_values('Grid', 'Grid Power:', self.grid_power, colors=d.pos_neg_color_v(self.grid_power))

        d.set_3_float_values('Grid', 'Grid House Power:', self.grid_house_power,
                             colors=d.pos_neg_color_v(self.grid_house_power))

        d.set_3_float_values('Grid', 'Grid Addition Power:', self.grid_addition_power,
                             colors=d.pos_neg_color_v(self.grid_addition_power))

        d.set_3_float_values('Grid', 'Grid Voltage:', self.grid_voltage, fmt='.1f', units='V',
                             colors=(d.range_two_color(self.grid_voltage[0], 228.0, 252.0),
                                     d.range_two_color(self.grid_voltage[1], 114.0, 126.0),
                                     d.range_two_color(self.grid_voltage[2], 114.0, 126.0)))

        d.set_float_value('Grid', 'Grid Power Factor:', 'L1', self.grid_power_factor[0], fmt='.3f',
                          color=self.display.range_two_color(self.grid_power_factor[0], -0.8, 0.8,
                                                             in_color=self.RED, out_color=self.GREEN))

        d.set_float_value('Grid', 'Grid Power Factor:', 'L2', self.grid_power_factor[1], fmt='.3f',
                          color=self.display.range_two_color(self.grid_power_factor[1], -0.8, 0.8,
                                                             in_color=self.RED, out_color=self.GREEN))

        d.set_float_value('Grid', 'Grid Frequency:', 'Total', self.grid_frequency, fmt='.2f', units='Hz',
                          color=d.range_two_color(self.grid_frequency, 59.70, 60.30, out_color=self.RED))

        d.set_value('Grid', 'Grid Power:', 'Min Mean Max',
                    self.ess_stats.grid_power.min_mean_max_string(units='W'))
        d.set_value('Grid', 'Grid House Power:', 'Min Mean Max',
                    self.ess_stats.grid_house_power.min_mean_max_string(units='W'))
        d.set_value('Grid', 'Grid Addition Power:', 'Min Mean Max',
                    self.ess_stats.grid_addition_power.min_mean_max_string(units='W'))
        d.set_value('Grid', 'Grid Voltage:', 'Min Mean Max',
                    self.ess_stats.grid_voltage.min_mean_max_string(fmt='6.1f', units='V'))
        d.set_value('Grid', 'Grid Frequency:', 'Min Mean Max',
                    self.ess_stats.grid_frequency.min_mean_max_string(fmt='6.2f', units='Hz'))

        # ----- Inverter -----
        d.set_3_float_values('Inverter', 'Inverter Power (Total):', self.inverter_ac_total_power,
                             colors=d.pos_neg_color_v(self.inverter_ac_total_power))

        d.set_3_float_values('Inverter', 'Inverter Input Power:', self.inverter_ac_input_power,
                             colors=d.pos_neg_color_v(self.inverter_ac_input_power))

        d.set_3_float_values('Inverter', 'Inverter Output Power:', self.inverter_ac_output_power,
                             colors=d.pos_neg_color_v(self.inverter_ac_output_power))

        d.set_3_float_values('Inverter', 'Inverter Input PF:', self.inverter_input_power_factor, fmt='.3f', units='',
                             colors=d.range_two_color_v(self.inverter_input_power_factor, -0.8, 0.8,
                                                        in_color=self.RED, out_color=self.GREEN))

        d.set_3_float_values('Inverter', 'Inverter Output PF:', self.inverter_output_power_factor, fmt='.3f', units='',
                             colors=self.display.range_two_color_v(self.inverter_output_power_factor, -0.8, 0.8,
                                                                   in_color=self.RED, out_color=self.GREEN))

        d.set_float_value('Inverter', 'Inverter ESS Power Limit:', 'Total', self.inverter_ess_power_limit, units='W',
                          color=d.pos_neg_color(self.inverter_ess_power_limit))

        d.set_float_value('Inverter', 'Inverter Efficiency:', 'Total', self.inverter_efficiency[1],
                          fmt='.1f', units='%', color=d.range_three_color(self.inverter_efficiency[1],
                                                                          90.0, 100.0, 80.0, 90.0))

        d.set_value('Inverter', 'Inverter Efficiency:', 'L1', self.inverter_efficiency[0],
                    color=self.GREEN if self.inverter_efficiency[0] == 'Inverter' else self.YELLOW)

        d.set_value('Inverter', 'Inverter State:', 'Total', '    ' + self.inverter_state, color=self.GREEN)

        d.set_value('Inverter', 'Active Warnings & Alarms:', 'Total', '    ' + self.inverter_warnings_alarms,
                    color=self.GREEN if self.inverter_warnings_alarms == 'None' else self.RED)

        d.set_float_value('Inverter', 'Inverter Temperature:', 'Total', self.inverter_rack_temperature,
                          fmt='.1f', units='°C', color=d.range_three_color(self.inverter_rack_temperature,
                                                                           5.0, 40.0, 40.0, 50.0))

        d.set_value('Inverter', 'Inverter Power (Total):', 'Min Mean Max',
                    self.ess_stats.inverter_ac_total_power.min_mean_max_string(units='W'))
        d.set_value('Inverter', 'Inverter Input Power:', 'Min Mean Max',
                    self.ess_stats.inverter_ac_input_power.min_mean_max_string(units='W'))
        d.set_value('Inverter', 'Inverter Output Power:', 'Min Mean Max',
                    self.ess_stats.inverter_ac_output_power.min_mean_max_string(units='W'))
        d.set_value('Inverter', 'Inverter Temperature:', 'Min Mean Max',
                    self.ess_stats.inverter_rack_temperature.min_mean_max_string(fmt='6.1f', units='°C'))

        # ----- AC Consumption -----
        d.set_3_float_values('AC Consumption', 'AC Consumption (Total):', self.ac_consumption,
                             colors=d.pos_neg_color_v(self.ac_consumption))

        d.set_3_float_values('AC Consumption', 'AC Critical Loads:', self.ac_critical_load_consumption,
                             colors=d.pos_neg_color_v(self.ac_critical_load_consumption))

        d.set_3_float_values('AC Consumption', 'AC House Consumption:', self.ac_house_consumption,
                             colors=d.pos_neg_color_v(self.ac_house_consumption))

        d.set_3_float_values('AC Consumption', 'AC Addition Consumption:', self.ac_addition_consumption,
                             colors=d.pos_neg_color_v(self.ac_addition_consumption))

        d.set_3_float_values('AC Consumption', 'AC Battery Chargers:', self.ac_battery_charger_consumption,
                             colors=d.pos_neg_color_v(self.ac_battery_charger_consumption))

        d.set_value('AC Consumption', 'AC Consumption (Total):', 'Min Mean Max',
                    self.ess_stats.ac_consumption.min_mean_max_string(units='W'))
        d.set_value('AC Consumption', 'AC Critical Loads:', 'Min Mean Max',
                    self.ess_stats.ac_critical_load_consumption.min_mean_max_string(units='W'))
        d.set_value('AC Consumption', 'AC House Consumption:', 'Min Mean Max',
                    self.ess_stats.ac_house_consumption.min_mean_max_string(units='W'))
        d.set_value('AC Consumption', 'AC Addition Consumption:', 'Min Mean Max',
                    self.ess_stats.ac_addition_consumption.min_mean_max_string(units='W'))
        d.set_value('AC Consumption', 'AC Battery Chargers:', 'Min Mean Max',
                    self.ess_stats.ac_battery_charger_consumption.min_mean_max_string(units='W'))

        # ----- PV Solar -----
        d.set_3pv_float_values('PV Solar', 'PV Power:', self.pv_power, fmt='.1f', units='W',
                               colors=d.pos_neg_color_v(self.pv_power))

        d.set_3pv_float_values('PV Solar', 'PV DC Current:', self.pv_dc_current, fmt='.1f', units='A',
                               colors=d.pos_neg_color_v(self.pv_dc_current))

        d.set_3pv_float_values('PV Solar', 'PV Yield Today:', self.pv_energy_yield_today, fmt='.1f', units='kWh',
                               colors=d.pos_neg_color_v(self.pv_energy_yield_today))

        d.set_3pv_float_values('PV Solar', 'PV Efficiency:', self.pv_efficiency, fmt='.1f', units='%',
                               colors=d.range_two_color_v(self.pv_efficiency, 95.0, 100.0))

        d.set_3pv_float_values('PV Solar', 'PV Power Lost in Rack:', self.pv_power_lost, units='W',
                               colors=d.pos_neg_color_v(self.pv_power_lost))

        d.set_float_value('PV Solar', 'PV Net Efficiency:', 'Total', self.pv_net_efficiency, fmt='.1f', units='%',
                          color=d.range_two_color(self.pv_net_efficiency, 95.0, 100.0))

        d.set_float_value('PV Solar', 'PV Voltage:', '250/70', self.pv_voltage[0], fmt='.1f', units='V',
                          color=d.range_two_color(self.pv_voltage[0], 60.0, 245.0, out_color=self.RED))
        d.set_float_value('PV Solar', 'PV Voltage:', '250/100', self.pv_voltage[1], fmt='.1f', units='V',
                          color=d.range_two_color(self.pv_voltage[1], 60.0, 245.0, out_color=self.RED))

        d.set_float_value('PV Solar', 'PV Current:', '250/70', self.pv_current[0], fmt='.1f', units='A',
                          color=d.range_two_color(self.pv_current[0], 0.0, 40.0, out_color=self.RED))
        d.set_float_value('PV Solar', 'PV Current:', '250/100', self.pv_current[1], fmt='.1f', units='A',
                          color=d.range_two_color(self.pv_current[1], 0.0, 40.0, out_color=self.RED))

        d.set_value('PV Solar', 'PV MPPT Modes:', '250/70', self.pv_opmode[0] + '  ',
                    color=self.GREEN if self.pv_opmode[0] == 'Active' else self.RED)
        d.set_value('PV Solar', 'PV MPPT Modes:', '250/100', self.pv_opmode[1] + '  ',
                    color=self.GREEN if self.pv_opmode[1] == 'Active' else self.RED)

        d.set_value('PV Solar', 'PV Power:', 'Maximum',
                    self.ess_stats.pv_power.max_string(units='W'))
        d.set_value('PV Solar', 'PV DC Current:', 'Maximum',
                    self.ess_stats.pv_dc_current.max_string(fmt='6.1f', units='A'))

        pv_voltage_250_70 = self.ess_stats.pv_voltage_250_70.max_string(fmt='6.1f', units='V')
        pv_voltage_250_100 = self.ess_stats.pv_voltage_250_100.max_string(fmt='6.1f', units='V')
        max_pv_string = f'[{pv_voltage_250_70}  {pv_voltage_250_100}]'
        d.set_value('PV Solar', 'PV Voltage:', 'Maximum', max_pv_string)

        # ----- Battery -----
        d.set_2batt_float_values('Battery', 'Battery SoC:', self.battery_soc, fmt='.1f', units='%',
                                 colors=d.range_three_color_v(self.battery_soc, 20.0, 95.0, 95.0, 99.0))

        d.set_2batt_float_values('Battery', 'Battery Voltage:', self.battery_voltage, fmt='.2f', units='V',
                                 colors=d.range_three_color_v(self.battery_voltage, 52.0, 56.0, 50.0, 52.0))

        d.set_float_value('Battery', 'Battery Cell Voltages:', 'BMS', self.battery_cell_voltages[0],
                          fmt='.2f', units='V',
                          color=d.range_three_color(self.battery_cell_voltages[0], 3.00, 3.40, 3.40, 3.50))
        d.set_float_value('Battery', 'Battery Cell Voltages:', ' ', self.battery_cell_voltages[1],
                          fmt='.2f', units='V',
                          color=d.range_three_color(self.battery_cell_voltages[1], 3.00, 3.40, 3.40, 3.50))

        d.set_float_value('Battery', 'Battery Temperature:', 'BMS', self.battery_temperature,
                          fmt='.1f', units='°C', color=d.range_three_color(self.battery_temperature,
                                                                           5.0, 40.0, 40.0, 50.0))

        d.set_value('Battery', 'Battery Module Status:', 'BMS', self.battery_blocking,
                    color=self.GREEN if 'Normal' in self.battery_blocking else self.RED)

        d.set_float_value('Battery', 'Battery Charge Current:', 'Shunt', self.battery_charge_current,
                          fmt='.1f', units='A', color=d.range_three_color(self.battery_charge_current,
                                                                          0.0, 120.0, -150.0, 0.0))

        d.set_float_value('Battery', 'Battery Power:', 'Shunt', self.battery_power,
                          fmt='.0f', units='W', color=d.range_three_color(self.battery_power, 0, 6000, -8000, 0))

        d.set_float_value('Battery', 'Battery Cable Power Loss:', 'Shunt', self.battery_power_lost,
                          fmt='.0f', units='W', color=d.range_three_color(self.battery_power_lost, 0, 10, 10, 50))

        d.set_value('Battery', 'Battery SoC:', 'Min Mean Max',
                    self.ess_stats.battery_soc.min_mean_max_string(fmt='6.1f', units='%'))
        d.set_value('Battery', 'Battery Voltage:', 'Min Mean Max',
                    self.ess_stats.battery_voltage.min_mean_max_string(fmt='6.2f', units='V'))
        d.set_value('Battery', 'Battery Temperature:', 'Min Mean Max',
                    self.ess_stats.battery_temperature.min_mean_max_string(fmt='6.1f', units='°C'))
        d.set_value('Battery', 'Battery Charge Current:', 'Min Mean Max',
                    self.ess_stats.battery_charge_current.min_mean_max_string(fmt='6.1f', units='A'))

        # ----- Chargeverter -----
        d.set_float_value('Chargeverter', 'Chargeverter Power:', 'Value', self.chargeverter_power,
                          fmt='.0f', units='W', color=d.range_three_color(self.chargeverter_power, 0, 3000, 3000, 5000))

        d.set_float_value('Chargeverter', 'Chargeverter Current:', 'Value', self.chargeverter_current,
                          fmt='.1f', units='A', color=d.range_three_color(self.chargeverter_current,
                                                                          0.0, 50.0, 50.0, 80.0))

        d.set_float_value('Chargeverter', 'Chargeverter Temperature:', 'Value', self.chargeverter_temp,
                          fmt='.1f', units='°C', color=d.range_three_color(self.chargeverter_temp,
                                                                           5.0, 40.0, 40.0, 50.0))

        # Update the display
        self.display.update()

    async def status_display(self):
        # Creates the ESS display and updates the info every second
        self.display = ESSColorStatusDisplay()
        self.display.setup()

        while True:
            await self.gather_cerbo_info()  # Get all the values from the Cerbo GX attached devices
            self.update_statistics()
            self.update_display()
            time.sleep(1.0)                 # Display and log file update rate

    async def playback_display(self, decimation=0):
        # Creates the ESS display and updates the info from the playback file at an accelerated rate
        self.display = ESSColorStatusDisplay()
        self.display.setup()

        while True:
            if self.gather_playback_info():   # Get all the values from the playback log file
                break
            self.update_statistics()
            self.update_display()

            if decimation:
                for i in range(decimation-1):
                    if self.playback_reader.read_next_row():
                        break
            time.sleep(0.1)                   # Playback update rate

    async def main(self, playback_log_file=None, decimation=0):
        # Playback an existing logfile, showing status until terminated
        if playback_log_file:
            self.playback_reader = ESSLogReader(playback_log_file)
            self.playback_reader.open_file()
            await self.playback_display(decimation)

        # Connect to Cerbo GX and update the status display until terminated
        else:
            while True:
                try:
                    await self.connect()
                    await self.status_display()

                except (ConnectionResetError, TimeoutError, ModbusTCPClient.Disconnected):
                    print('# Disconnected from ModbusTCP server')
                    await self.disconnect()

                    print('# Retrying...')
                    time.sleep(30.0)

                except KeyboardInterrupt:
                    return


if __name__ == "__main__":
    # Execute main() if this file is executed directly
    # Plays back from a log file if it is specified
    # Otherwise connects and provides real-time display and logging

    playback_file = None
    playback_decimation = 0

    if len(sys.argv) >= 2:
        playback_file = sys.argv[1]
    if len(sys.argv) >= 3:
        playback_decimation = int(sys.argv[2])

    ess = ESS()
    asyncio.run(ess.main(playback_file, playback_decimation))
