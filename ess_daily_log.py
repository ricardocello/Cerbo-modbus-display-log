# -------------------------------------------------------------------------------------------------------------------
# Implements a class to write ESS daily summary log files.
# These files can be completely created from existing compressed and gzip log files.
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

import glob
from ess_log import *


class DailyLogWriter(TabDelimitedLogWriter):
    # Class for writing ESS tab-delimited daily summary log files
    # The daily log files can be created completely from archived/gziped regular log files stored in a directory

    def __init__(self, filename, ess_stats):
        super().__init__(filename)

        # Date is first column
        self.add_column('Date')

        # ----- Grid -----
        self.add_min_mean_max_columns(ess_stats.grid_power)
        self.add_min_mean_max_columns(ess_stats.grid_house_power)
        self.add_min_mean_max_columns(ess_stats.grid_addition_power)
        self.add_min_mean_max_columns(ess_stats.grid_voltage, fmt=':.1f')
        self.add_min_mean_max_columns(ess_stats.grid_frequency, fmt=':.2f')

        # ----- Inverter -----
        self.add_min_mean_max_columns(ess_stats.inverter_ac_total_power)
        self.add_min_mean_max_columns(ess_stats.inverter_ac_input_power)
        self.add_min_mean_max_columns(ess_stats.inverter_ac_output_power)
        self.add_min_mean_max_columns(ess_stats.inverter_rack_temperature, fmt=':.1f')

        # ----- AC Consumption -----
        self.add_min_mean_max_columns(ess_stats.ac_consumption)
        self.add_min_mean_max_columns(ess_stats.ac_critical_load_consumption)
        self.add_min_mean_max_columns(ess_stats.ac_house_consumption)
        self.add_min_mean_max_columns(ess_stats.ac_addition_consumption)
        self.add_min_mean_max_columns(ess_stats.ac_battery_charger_consumption)

        # ----- PV Solar -----
        self.add_max_column(ess_stats.pv_power, fmt=':.1f')
        self.add_max_column(ess_stats.pv_dc_current, fmt=':.1f')
        self.add_max_column(ess_stats.pv_voltage_250_70, fmt=':.1f')
        self.add_max_column(ess_stats.pv_voltage_250_100, fmt=':.1f')

        # ----- Battery -----
        self.add_min_mean_max_columns(ess_stats.battery_soc, fmt=':.1f')
        self.add_min_mean_max_columns(ess_stats.battery_voltage, fmt=':.2f')
        self.add_min_mean_max_columns(ess_stats.battery_temperature, fmt=':.1f')
        self.add_min_mean_max_columns(ess_stats.battery_charge_current, fmt=':.1f')

    def add_min_mean_max_columns(self, stats, fmt=':.0f'):
        min_name = 'Min ' + stats.name
        mean_name = 'Mean ' + stats.name
        max_name = 'Max ' + stats.name
        self.columns[min_name] = Column(min_name, fmt)
        self.columns[mean_name] = Column(mean_name, fmt)
        self.columns[max_name] = Column(max_name, fmt)

    def add_max_column(self, stats, fmt=':.0f'):
        max_name = 'Max ' + stats.name
        self.columns[max_name] = Column(max_name, fmt)

    def set_min_mean_max_values(self, stats):
        # Sets three values to min name, mean name, max name
        min_name = 'Min ' + stats.name
        mean_name = 'Mean ' + stats.name
        max_name = 'Max ' + stats.name
        self.set_row_value(min_name, stats.min)
        self.set_row_value(mean_name, stats.mean())
        self.set_row_value(max_name, stats.max)

    def set_max_value(self, stats):
        # Sets value using max name
        max_name = 'Max ' + stats.name
        self.set_row_value(max_name, stats.max)


class DailyLogSummary:
    def __init__(self, filename='ESS_Daily.log'):
        self.stats = ESSStats()

        self.log_writer = DailyLogWriter(filename, self.stats)
        self.log_writer.create_file()
        self.log_writer.log_header()

    def run(self):
        # Get list of compressed log files in the current directory
        file_list = sorted(glob.glob('Log_*.gz'))

        # Process each file
        print(f'Date         Max Grid  Max Inverter')
        for fname in file_list:
            s = self.process_file(fname)
            print(s)

        self.log_writer.close()

        grid_power_max_watts = self.stats.grid_power.max_string(units='W')
        inverter_power_max_watts = self.stats.inverter_ac_total_power.max_string(units='W')

        return print(f'Total       {grid_power_max_watts} {inverter_power_max_watts}')

    def process_file(self, filename):
        day_stats = ESSStats()

        file_date = filename[4:14]
        rlf = ESSLogReader(filename)
        rlf.open_gzip_file()

        while True:
            if rlf.read_next_row():
                break

            # ----- Grid -----
            day_stats.next_grid((rlf.get_float_value(day_stats.grid_power.name),
                                 rlf.get_float_value(day_stats.grid_house_power.name),
                                 rlf.get_float_value(day_stats.grid_addition_power.name),
                                 rlf.get_float_value(day_stats.grid_voltage.name),
                                 rlf.get_float_value(day_stats.grid_frequency.name)))

            # ----- Inverter -----
            day_stats.next_inverter((rlf.get_float_value(day_stats.inverter_ac_total_power.name),
                                     rlf.get_float_value(day_stats.inverter_ac_input_power.name),
                                     rlf.get_float_value(day_stats.inverter_ac_output_power.name),
                                     rlf.get_float_value(day_stats.inverter_rack_temperature.name)))

            # ----- AC Consumption -----
            day_stats.next_ac_consumption((rlf.get_float_value(day_stats.ac_consumption.name),
                                           rlf.get_float_value(day_stats.ac_critical_load_consumption.name),
                                           rlf.get_float_value(day_stats.ac_house_consumption.name),
                                           rlf.get_float_value(day_stats.ac_addition_consumption.name),
                                           rlf.get_float_value(day_stats.ac_battery_charger_consumption.name)))

            # ----- PV Solar -----
            day_stats.next_pv_solar((rlf.get_float_value(day_stats.pv_power.name),
                                     rlf.get_float_value(day_stats.pv_dc_current.name),
                                     rlf.get_float_value(day_stats.pv_voltage_250_70.name),
                                     rlf.get_float_value(day_stats.pv_voltage_250_70.name)))

            # ----- Battery -----
            day_stats.next_battery((rlf.get_float_value(day_stats.battery_soc.name),
                                    rlf.get_float_value(day_stats.battery_voltage.name),
                                    rlf.get_float_value(day_stats.battery_temperature.name),
                                    rlf.get_float_value(day_stats.battery_charge_current.name)))

        # Add today's stats to the total stats
        self.stats.next_stats(day_stats)
        rlf.file.close()

        self.log_writer.set_row_value('Date', file_date)

        # ----- Grid -----
        self.log_writer.set_min_mean_max_values(day_stats.grid_power)
        self.log_writer.set_min_mean_max_values(day_stats.grid_house_power)
        self.log_writer.set_min_mean_max_values(day_stats.grid_addition_power)
        self.log_writer.set_min_mean_max_values(day_stats.grid_voltage)
        self.log_writer.set_min_mean_max_values(day_stats.grid_frequency)

        # ----- Inverter -----
        self.log_writer.set_min_mean_max_values(day_stats.inverter_ac_total_power)
        self.log_writer.set_min_mean_max_values(day_stats.inverter_ac_input_power)
        self.log_writer.set_min_mean_max_values(day_stats.inverter_ac_output_power)
        self.log_writer.set_min_mean_max_values(day_stats.inverter_rack_temperature)

        # ----- AC Consumption -----
        self.log_writer.set_min_mean_max_values(day_stats.ac_consumption)
        self.log_writer.set_min_mean_max_values(day_stats.ac_critical_load_consumption)
        self.log_writer.set_min_mean_max_values(day_stats.ac_house_consumption)
        self.log_writer.set_min_mean_max_values(day_stats.ac_addition_consumption)
        self.log_writer.set_min_mean_max_values(day_stats.ac_battery_charger_consumption)

        # ----- PV Solar -----
        self.log_writer.set_max_value(day_stats.pv_power)
        self.log_writer.set_max_value(day_stats.pv_dc_current)
        self.log_writer.set_max_value(day_stats.pv_voltage_250_70)
        self.log_writer.set_max_value(day_stats.pv_voltage_250_100)

        # ----- Battery -----
        self.log_writer.set_min_mean_max_values(day_stats.battery_soc)
        self.log_writer.set_min_mean_max_values(day_stats.battery_voltage)
        self.log_writer.set_min_mean_max_values(day_stats.battery_temperature)
        self.log_writer.set_min_mean_max_values(day_stats.battery_charge_current)

        # Log the stats for this day
        self.log_writer.log_row()

        grid_power_max_watts = day_stats.grid_power.max_string(units='W')
        inverter_power_max_watts = day_stats.inverter_ac_total_power.max_string(units='W')

        return f'{file_date}  {grid_power_max_watts} {inverter_power_max_watts}'


if __name__ == "__main__":
    # Execute main() if this file is executed directly
    dls = DailyLogSummary()
    dls.run()
