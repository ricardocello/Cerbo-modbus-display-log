# -------------------------------------------------------------------------------------------------------------------
# Implements an ESS status display.
# Uses ANSI escape sequences for standard terminal windows.
#
# This class is very specific to ricardocello but provides an good example.
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

from color_status_display import *


class ESSColorStatusDisplay(ColorStatusDisplay):
    # ESS Status Display Implementation

    def __init__(self):
        super().__init__('ESS Status')
        # Fixed field widths are common to all sections
        self.name_field_width = 26
        self.data_field_width = 12
        self.minmax_field_width = 27
        self.comment_field_width = 52

    def setup(self):
        # Sections
        grid = self.add_section('Grid')
        inverter = self.add_section('Inverter')
        ac = self.add_section('AC Consumption')
        pv = self.add_section('PV Solar')
        battery = self.add_section('Battery')
        cv = self.add_section('Chargeverter')

        # ----- Grid Section -----
        grid.add_column('Grid', self.name_field_width)
        grid.add_column('Total', self.data_field_width, title_alignment='^', field_alignment='>')
        grid.add_column('L1', self.data_field_width, title_alignment='^', field_alignment='>')
        grid.add_column('L2', self.data_field_width, title_alignment='^', field_alignment='>')
        grid.add_column('Min Mean Max', self.minmax_field_width, title_alignment='^', field_alignment='^')
        grid.add_column('Comments', self.comment_field_width)

        grid.add_parameter_and_comment('Grid Power:', 'Total utility grid power used')
        grid.add_parameter_and_comment('Grid House Power:', 'Grid power used in Main House')
        grid.add_parameter_and_comment('Grid Addition Power:', 'Grid power used in Addition')
        grid.add_parameter_and_comment('Grid Voltage:', 'Grid voltage')
        grid.add_parameter_and_comment('Grid Power Factor:', 'Power Factor for Main House Only')
        grid.add_parameter_and_comment('Grid Frequency:', 'Grid AC frequency')

        # ----- Inverter Section -----
        inverter.add_column('Inverter', self.name_field_width)
        inverter.add_column('Total', self.data_field_width, title_alignment='^', field_alignment='>')
        inverter.add_column('L1', self.data_field_width, title_alignment='^', field_alignment='>')
        inverter.add_column('L2', self.data_field_width, title_alignment='^', field_alignment='>')
        inverter.add_column('Min Mean Max', self.minmax_field_width, title_alignment='^', field_alignment='^')
        inverter.add_column('Comments', self.comment_field_width)

        inverter.add_parameter_and_comment('Inverter Power (Total):', 'Total Quattro AC Power Generated')
        inverter.add_parameter_and_comment('Inverter Input Power:', 'Quattro AC Input Power')
        inverter.add_parameter_and_comment('Inverter Output Power:', 'Quattro AC Output Power')
        inverter.add_parameter_and_comment('Inverter Input PF:', 'Estimated Input Power Factor')
        inverter.add_parameter_and_comment('Inverter Output PF:', 'Estimated Output Power Factor')
        inverter.add_parameter_and_comment('Inverter ESS Power Limit:', 'Dynamically adjusted power limit')
        inverter.add_parameter_and_comment('Inverter Efficiency:', 'Estimated efficiency of charger or inverter')
        inverter.add_parameter_and_comment('Inverter Temperature:', 'Temperature at top of rack')

        inverter.add_parameter_and_comment('Inverter State:')
        inverter.use_rest_of_line('Inverter State:', 'Total')

        inverter.add_parameter_and_comment('Active Warnings & Alarms:')
        inverter.use_rest_of_line('Active Warnings & Alarms:', 'Total')

        # ----- AC Consumption Section -----
        ac.add_column('AC Consumption', self.name_field_width)
        ac.add_column('Total', self.data_field_width, title_alignment='^', field_alignment='>')
        ac.add_column('L1', self.data_field_width, title_alignment='^', field_alignment='>')
        ac.add_column('L2', self.data_field_width, title_alignment='^', field_alignment='>')
        ac.add_column('Min Mean Max', self.minmax_field_width, title_alignment='^', field_alignment='^')
        ac.add_column('Comments', self.comment_field_width)

        ac.add_parameter_and_comment('AC Consumption (Total):', 'Total AC power being consumed')
        ac.add_parameter_and_comment('AC Critical Loads:', 'House critical loads consumption')
        ac.add_parameter_and_comment('AC House Consumption:', 'House non-critical loads consumption')
        ac.add_parameter_and_comment('AC Addition Consumption:', 'Addition power consumption')
        ac.add_parameter_and_comment('AC Battery Chargers:', 'Quattro AC power consumed to charge batteries')

        # ----- PV Solar Section -----
        pv.add_column('PV Solar', self.name_field_width)
        pv.add_column('Total', self.data_field_width, title_alignment='^', field_alignment='>')
        pv.add_column('250/70', self.data_field_width, title_alignment='^', field_alignment='>')
        pv.add_column('250/100', self.data_field_width, title_alignment='^', field_alignment='>')
        pv.add_column('Maximum', self.minmax_field_width, title_alignment='^', field_alignment='^')
        pv.add_column('Comments', self.comment_field_width)

        pv.add_parameter_and_comment('PV Power:', 'Power generated by solar panels')
        pv.add_parameter_and_comment('PV DC Current:', 'DC current to battery and inverters')
        pv.add_parameter_and_comment('PV Yield Today:', 'Total solar energy produced today')
        pv.add_parameter_and_comment('PV Efficiency:', 'Estimated efficiency converting PV power to DC')
        pv.add_parameter_and_comment('PV Power Lost in Rack:', 'Cable and fuse DC power loss though rack cables')
        pv.add_parameter_and_comment('PV Net Efficiency:', 'Overall PV efficiency thru inverter to loads')
        pv.add_parameter_and_comment('PV Voltage:', 'Voltage from solar panels')
        pv.add_parameter_and_comment('PV Current:', 'Current from solar panels')
        pv.add_parameter_and_comment('PV MPPT Modes:', 'Can be limited by max current, battery SoC, or DVCC')

        # ----- Battery Section -----
        battery.add_column('Battery', self.name_field_width)
        battery.add_column('Shunt', self.data_field_width, title_alignment='^', field_alignment='>')
        battery.add_column('BMS', self.data_field_width, title_alignment='^', field_alignment='>')
        battery.add_column(' ', self.data_field_width, title_alignment='^', field_alignment='>')
        battery.add_column('Min Mean Max', self.minmax_field_width, title_alignment='^', field_alignment='^')
        battery.add_column('Comments', self.comment_field_width)

        battery.add_parameter_and_comment('Battery SoC:', 'State of Charges from SmartShunt and BMS')
        battery.add_parameter_and_comment('Battery Voltage:', 'Voltage measurements from SmartShunt and BMS')
        battery.add_parameter_and_comment('Battery Cell Voltages:', 'Minimum and Maximum Cell Voltages')
        battery.add_parameter_and_comment('Battery Temperature:', 'Temperature reported by batteries in rack')
        battery.add_parameter_and_comment('Battery Module Status:', 'BMS charge/discharge FET blocking status')
        battery.add_parameter_and_comment('Battery Charge Current:', 'DC current to (+) or from (-) the battery')
        battery.add_parameter_and_comment('Battery Power:', 'DC power to (+) or from (-) the battery')
        battery.add_parameter_and_comment('Battery Cable Power Loss:',
                                          'Total cable and fuse DC power loss between racks')

        # ----- Chargeverter Section -----
        cv.add_column('Chargeverter', self.name_field_width)
        cv.add_column('Value', self.data_field_width, title_alignment='^', field_alignment='>')
        cv.add_column(' ', self.data_field_width, title_alignment='^', field_alignment='>')
        cv.add_column('  ', self.data_field_width, title_alignment='^', field_alignment='>')
        cv.add_column('Comments', self.comment_field_width)

        cv.add_parameter_and_comment('Chargeverter Power:', 'DC power to battery and inverters')
        cv.add_parameter_and_comment('Chargeverter Current:', 'DC current to battery and inverters')
        cv.add_parameter_and_comment('Chargeverter Temperature:', 'Temperature on Chargeverter case')

    def set_3_float_values(self, section, parameter, values, units='W', fmt='6.0f', colors=(NORM, NORM, NORM)):
        # Convenience function for (Total, L1, L2) tuples
        self.set_float_value(section, parameter, 'Total', values[0], units=units, fmt=fmt, color=colors[0])
        self.set_float_value(section, parameter, 'L1', values[1], units=units, fmt=fmt, color=colors[1])
        self.set_float_value(section, parameter, 'L2', values[2], units=units, fmt=fmt, color=colors[2])

    def set_3pv_float_values(self, section, parameter, values, units='', fmt='6.1f', colors=(NORM, NORM, NORM)):
        # Convenience function for (Total, 250/70, 250/100) tuples
        self.set_float_value(section, parameter, 'Total', values[0], units=units, fmt=fmt, color=colors[0])
        self.set_float_value(section, parameter, '250/70', values[1], units=units, fmt=fmt, color=colors[1])
        self.set_float_value(section, parameter, '250/100', values[2], units=units, fmt=fmt, color=colors[2])

    def set_2batt_float_values(self, section, parameter, values, units='', fmt='6.1f', colors=(NORM, NORM)):
        # Convenience function for (Shunt, BMS) tuples
        self.set_float_value(section, parameter, 'Shunt', values[0], units=units, fmt=fmt, color=colors[0])
        self.set_float_value(section, parameter, 'BMS', values[1], units=units, fmt=fmt, color=colors[1])


if __name__ == "__main__":
    # Execute main() if this file is executed directly
    # This unit test displays the setup once to see if is correct.

    display = ESSColorStatusDisplay()
    display.setup()
    display.update()
