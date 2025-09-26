# -------------------------------------------------------------------------------------------------------------------
# Implements a class to read and write ESS log files.
# This is specific to the ricardocello ESS implementation.
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

from tab_delimited_log import *
from statistics import *


class ESSStats:
    # This class holds all the statistics gathered during display or file playback

    def __init__(self):

        # ----- Grid -----
        self.grid_power = Statistics('Grid Power (W)')
        self.grid_house_power = Statistics('Grid House Power (W)')
        self.grid_addition_power = Statistics('Grid Addition Power (W)')
        self.grid_voltage = Statistics('Grid Voltage')
        self.grid_frequency = Statistics('Grid Frequency (Hz)')

        # ----- Inverter -----
        self.inverter_ac_total_power = Statistics('Total Inverter Power (W)')
        self.inverter_ac_input_power = Statistics('Inverter Input Power (W)')
        self.inverter_ac_output_power = Statistics('Inverter Output Power (W)')
        self.inverter_rack_temperature = Statistics('Inverter Temperature (°C)')

        # ----- AC Consumption -----
        self.ac_consumption = Statistics('Total AC Consumption (W)')
        self.ac_critical_load_consumption = Statistics('AC Critical Loads (W)')
        self.ac_house_consumption = Statistics('AC House Consumption (W)')
        self.ac_addition_consumption = Statistics('AC Addition Consumption (W)')
        self.ac_battery_charger_consumption = Statistics('AC Battery Chargers (W)')

        # ----- PV Solar -----
        self.pv_power = Statistics('PV Power (W)')
        self.pv_dc_current = Statistics('PV DC Current (A)')
        self.pv_voltage_250_70 = Statistics('250/70 PV Voltage (V)')
        self.pv_voltage_250_100 = Statistics('250/100 PV Voltage (V)')

        # ----- Battery -----
        self.battery_soc = Statistics('Shunt SoC (%)')
        self.battery_voltage = Statistics('Shunt Voltage (V)')
        self.battery_temperature = Statistics('Battery Temperature (°C)')
        self.battery_charge_current = Statistics('Shunt Charge Current (A)')

    def clear(self):
        # Clears the existing statistics

        # ----- Grid -----
        self.grid_power.clear()
        self.grid_house_power.clear()
        self.grid_addition_power.clear()
        self.grid_voltage.clear()
        self.grid_frequency.clear()

        # ----- Inverter -----
        self.inverter_ac_total_power.clear()
        self.inverter_ac_input_power.clear()
        self.inverter_ac_output_power.clear()
        self.inverter_rack_temperature.clear()

        # ----- AC Consumption -----
        self.ac_consumption.clear()
        self.ac_critical_load_consumption.clear()
        self.ac_house_consumption.clear()
        self.ac_addition_consumption.clear()
        self.ac_battery_charger_consumption.clear()

        # ----- PV Solar -----
        self.pv_power.clear()
        self.pv_dc_current.clear()
        self.pv_voltage_250_70.clear()
        self.pv_voltage_250_100.clear()

        # ----- Battery -----
        self.battery_soc.clear()
        self.battery_voltage.clear()
        self.battery_temperature.clear()
        self.battery_charge_current.clear()

    def next_grid(self, grid_values):
        self.grid_power.next_value(grid_values[0])
        self.grid_house_power.next_value(grid_values[1])
        self.grid_addition_power.next_value(grid_values[2])
        self.grid_voltage.next_value(grid_values[3])
        self.grid_frequency.next_value(grid_values[4])

    def next_inverter(self, inverter_values):
        self.inverter_ac_total_power.next_value(inverter_values[0])
        self.inverter_ac_input_power.next_value(inverter_values[1])
        self.inverter_ac_output_power.next_value(inverter_values[2])
        self.inverter_rack_temperature.next_value(inverter_values[3])

    def next_ac_consumption(self, ac_consumption_values):
        self.ac_consumption.next_value(ac_consumption_values[0])
        self.ac_critical_load_consumption.next_value(ac_consumption_values[1])
        self.ac_house_consumption.next_value(ac_consumption_values[2])
        self.ac_addition_consumption.next_value(ac_consumption_values[3])
        self.ac_battery_charger_consumption.next_value(ac_consumption_values[4])

    def next_pv_solar(self, pv_solar_values):
        self.pv_power.next_value(pv_solar_values[0])
        self.pv_dc_current.next_value(pv_solar_values[1])
        self.pv_voltage_250_70.next_value(pv_solar_values[2])
        self.pv_voltage_250_100.next_value(pv_solar_values[3])

    def next_battery(self, battery_values):
        self.battery_soc.next_value(battery_values[0])
        self.battery_voltage.next_value(battery_values[1])
        self.battery_temperature.next_value(battery_values[2])
        self.battery_charge_current.next_value(battery_values[3])

    def next_stats(self, ess_stats):
        # Aggregates the statistics

        # ----- Grid -----
        self.grid_power.next_stats(ess_stats.grid_power)
        self.grid_house_power.next_stats(ess_stats.grid_house_power)
        self.grid_addition_power.next_stats(ess_stats.grid_addition_power)
        self.grid_voltage.next_stats(ess_stats.grid_voltage)
        self.grid_frequency.next_stats(ess_stats.grid_frequency)

        # ----- Inverter -----
        self.inverter_ac_total_power.next_stats(ess_stats.inverter_ac_total_power)
        self.inverter_ac_input_power.next_stats(ess_stats.inverter_ac_input_power)
        self.inverter_ac_output_power.next_stats(ess_stats.inverter_ac_output_power)
        self.inverter_rack_temperature.next_stats(ess_stats.inverter_rack_temperature)

        # ----- AC Consumption -----
        self.ac_consumption.next_stats(ess_stats.ac_consumption)
        self.ac_critical_load_consumption.next_stats(ess_stats.ac_critical_load_consumption)
        self.ac_house_consumption.next_stats(ess_stats.ac_house_consumption)
        self.ac_addition_consumption.next_stats(ess_stats.ac_addition_consumption)
        self.ac_battery_charger_consumption.next_stats(ess_stats.ac_battery_charger_consumption)

        # ----- PV Solar -----
        self.pv_power.next_stats(ess_stats.pv_power)
        self.pv_dc_current.next_stats(ess_stats.pv_dc_current)
        self.pv_voltage_250_70.next_stats(ess_stats.pv_voltage_250_70)
        self.pv_voltage_250_100.next_stats(ess_stats.pv_voltage_250_100)

        # ----- Battery -----
        self.battery_soc.next_stats(ess_stats.battery_soc)
        self.battery_voltage.next_stats(ess_stats.battery_voltage)
        self.battery_temperature.next_stats(ess_stats.battery_temperature)
        self.battery_charge_current.next_stats(ess_stats.battery_charge_current)


class ESSLogWriter(TabDelimitedLogWriter):
    # Specific functions for writing ESS tab-delimited log files

    def add_power_columns(self, name, fmt=':.0f'):
        # Adds a column with the name, and two more columns prefixed with L1 and L2 (single digit watts)
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.columns[name] = Column(name, fmt)
        self.columns[l1] = Column(l1, fmt)
        self.columns[l2] = Column(l2, fmt)

    def add_pf_columns(self, name, fmt=':.2f'):
        # Adds a column with the name, and two more columns prefixed with L1 and L2 (power factor format)
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.columns[name] = Column(name, fmt)
        self.columns[l1] = Column(l1, fmt)
        self.columns[l2] = Column(l2, fmt)

    def add_pv_columns(self, name, fmt=':.1f'):
        # Adds a column with the name, and two more columns prefixed with 250/70 and 250/100
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.columns[name] = Column(name, fmt)
        self.columns[mppt_250_70] = Column(mppt_250_70, fmt)
        self.columns[mppt_250_100] = Column(mppt_250_100, fmt)

    def add_2pv_columns(self, name, fmt=':.1f'):
        # Adds two columns prefixed with 250/70 and 250/100
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.columns[mppt_250_70] = Column(mppt_250_70, fmt)
        self.columns[mppt_250_100] = Column(mppt_250_100, fmt)

    def set_power_values(self, name, values):
        # Sets three values to columns name, L1 name, L2 name
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.set_row_value(name, values[0])
        self.set_row_value(l1, values[1])
        self.set_row_value(l2, values[2])

    def set_pf_values(self, name, values):
        # Sets three values to columns name, L1 name, L2 name
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.set_row_value(name, values[0])
        self.set_row_value(l1, values[1])
        self.set_row_value(l2, values[2])

    def set_pv_values(self, name, values):
        # Sets three values to columns name, 250/70 name, 250/100 name
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.set_row_value(name, values[0])
        self.set_row_value(mppt_250_70, values[1])
        self.set_row_value(mppt_250_100, values[2])

    def set_2pv_values(self, name, values):
        # Sets two values to columns 250/70 name, 250/100 name
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.set_row_value(mppt_250_70, values[0])
        self.set_row_value(mppt_250_100, values[1])


class ESSLogReader(TabDelimitedLogReader):
    # Specific functions for reading ESS log files

    def get_power_values(self, name):
        # Gets three values from columns name, L1 name, L2 name
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        return int(self.columns[name].value), int(self.columns[l1].value), int(self.columns[l2].value)

    def get_3float_values(self, name):
        # Gets two values from columns L1 name, L2 name
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        return float(self.columns[name].value), float(self.columns[l1].value), float(self.columns[l2].value)

    def get_pv_values(self, name):
        # Gets three values from columns name, 250/70 name, 250/100 name
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        return float(self.columns[name].value), float(self.columns[mppt_250_70].value), \
            float(self.columns[mppt_250_100].value)

    def get_2pv_values(self, name):
        # Gets two values from columns 250/70 name, 250/100 name
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        return float(self.columns[mppt_250_70].value), float(self.columns[mppt_250_100].value)


def test_saved_values():
    # Unit test demonstrates reading directly from a zip file and saving column values.

    rlf = ESSLogReader('ess.log.gz')
    rlf.open_gzip_file()
    rlf.save_column('Grid Power (W)')
    rlf.read_whole_file()
    print(rlf.columns['Grid Power (W)'].saved_values)


if __name__ == "__main__":
    # Execute main() if this file is executed directly
    test_saved_values()
