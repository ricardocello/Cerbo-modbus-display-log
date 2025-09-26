# -------------------------------------------------------------------------------------------------------------------
# Implements a class to display columnar data for a status display or dashboard.
# Uses ANSI escape sequences for standard terminal windows.
#
# A display can contain multiple Sections, each composed of multiple Rows.
# Each Section can define its own Columns to display.
# Each Column can have its own field width.
# Each Row represents an individual parameter.
# Each parameter value is stored as a string, with convenience conversion functions for numeric values.
# Each parameter value can define conditional coloring based on the value.
#
# This is generically useful and completely decoupled from the Cerbo GX code.
# The setup() function is very specific to ricardocello but provides an good example.
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

# ----- ANSI Colors and Controls -----
RED = '\x1b[31m'
GREEN = '\x1b[32m'
BLUE = '\x1b[34m'
YELLOW = '\x1b[33m'
CYAN = '\x1b[36m'
NORM = '\x1b[0m'

HOME = '\x1b[H'
CLEAR = '\x1b[2J'


class Section:
    # Represents a Section in the color status display.
    def __init__(self, name):
        self.name = name
        self.columns = {}
        self.parameter_names = []
        self.values = {}
        self.section_color = CYAN

    def add_column(self, name, width, title_alignment='<', field_alignment='<'):
        # Add these first
        c = Column(name, width, title_alignment, field_alignment)
        self.columns[name] = c
        return c

    def hide_column(self, name, hide=True):
        self.columns[name].visible = not hide

    def add_parameter(self, name):
        # Add these after the columns are all defined
        self.parameter_names.append(name)

    def add_parameter_and_comment(self, parameter, comment=''):
        # Conveniently adds the parameter name to the section,
        # assigns the parameter name to column 1,
        # and the comment to the Comments column.

        self.add_parameter(parameter)
        self.set_value(parameter, self.name, parameter)
        self.set_value(parameter, 'Comments', comment)

    def use_rest_of_line(self, parameter, column):
        # Flags this parameter and column so that it occupies the remainder of the line.
        # This is useful for long verbose strings when no other columns are relevant.
        # values in columns following this one will not be displayed.

        self.set_value(parameter, column, '')
        self.values[parameter, column].use_rest_of_line = True

    def set_value(self, parameter, column, value, color=NORM):
        # Sets the string value for the specified parameter and column.
        try:
            pv = self.values[parameter, column]
        except KeyError:
            pv = ParameterValue(parameter, column)   # only create this once
            self.values[parameter, column] = pv

        pv.value = value
        pv.color = color
        return pv

    def first_column_is_parameter_name(self):
        # Sets the values of the first column to the name of each parameter
        for pname in self.parameter_names:
            self.set_value(pname, self.name, pname)

    def update(self):
        # Updates this section on the screen

        # Title row
        for cname in self.columns:
            c = self.columns[cname]
            if not c.visible:
                continue
            print(f'{self.section_color}{c.name:{c.title_alignment}{c.width}.{c.width}} ', end='')
        print(f'{NORM}')

        # Parameters
        for pname in self.parameter_names:

            # Columns
            for cname in self.columns:
                c = self.columns[cname]
                if not c.visible:
                    continue

                try:
                    v = self.values[pname, cname]
                    if v.use_rest_of_line:
                        print(f'{v.color}{v.value:60}', end='')
                        break
                    else:
                        print(f'{v.color}{v.value:{c.field_alignment}{c.width}.{c.width}} ', end='')

                except KeyError:
                    print(f'{"":{c.width}.{c.width}} ', end='')
            print(f'{NORM}')
        print('')


class Column:
    # Represents a column in a Section.
    def __init__(self, name, width, title_alignment='<', field_alignment='<'):
        self.name = name      # displayed on its own row
        self.width = width    # field width of the column (there is always onw space between columns)
        self.title_alignment = title_alignment
        self.field_alignment = field_alignment
        self.visible = True


class ParameterValue:
    # Represents a parameter value in a specific column.
    def __init__(self, parameter_name, column_name):
        self.parameter_name = parameter_name
        self.column_name = column_name
        self.value = ''
        self.color = NORM
        self.use_rest_of_line = False


class ColorStatusDisplay:
    # This class implements the color status display.

    def __init__(self, name):
        self.name = name    # displayed as the first row
        self.sections = {}

        print(f'{CLEAR}{HOME}', end='')   # clear the screen

    def add_section(self, name):
        # Adds a section to the display
        s = Section(name)
        self.sections[name] = s
        return s

    def set_value(self, section, parameter, column, value, color=NORM):
        # Sets the specified value string
        s = self.sections[section]
        s.set_value(parameter, column, value, color=color)

    def set_float_value(self, section, parameter, column, value, units='', fmt='6.0f', color=NORM):
        # Sets the specified float value string
        self.set_value(section, parameter, column, f'{value:{fmt}} {units:3.3}', color=color)

    def update(self):
        # Updates the entire display
        print(f'{HOME}{CYAN}{self.name}\n')
        for section in self.sections:
            self.sections[section].update()

    @staticmethod
    def pos_neg_color(value, pos_color=GREEN, neg_color=YELLOW):
        # Returns pos_color if the value is positive, neg_color if negative
        return pos_color if value > 0.0 else neg_color

    @staticmethod
    # Returns pos_color for each positive value, neg_color for each negative value
    def pos_neg_color_v(values, pos_color=GREEN, neg_color=YELLOW):
        return tuple([pos_color if v > 0.0 else neg_color for v in values])

    @staticmethod
    def range_two_color(value, lo, hi, in_color=GREEN, out_color=YELLOW):
        # Returns in_color if the value between lo and hi, out_color if not
        return in_color if lo <= value < hi else out_color

    @staticmethod
    def range_two_color_v(values, lo, hi, in_color=GREEN, out_color=YELLOW):
        # Returns in_color for each value between lo and hi, out_color if not
        return tuple([in_color if lo <= v < hi else out_color for v in values])

    @staticmethod
    def range_three_color(value, green_lo, green_hi, yellow_lo, yellow_hi):
        # Returns GREEN if value is between green_lo and green_hi
        # Returns YELLOW if value is between yellow_lo and yellow_hi
        # Otherwise returns RED
        if green_lo <= value < green_hi:
            return GREEN
        if yellow_lo <= value < yellow_hi:
            return YELLOW
        return RED

    @staticmethod
    def range_three_color_v(values, green_lo, green_hi, yellow_lo, yellow_hi):
        # Returns GREEN for each value between green_lo and green_hi
        # Returns YELLOW for each value between yellow_lo and yellow_hi
        # Otherwise returns RED
        return tuple([ColorStatusDisplay.range_three_color(v, green_lo, green_hi, yellow_lo, yellow_hi)
                      for v in values])


if __name__ == "__main__":
    # Execute main() if this file is executed directly
    # This unit test displays a simple test setup.

    display = ColorStatusDisplay('Unit Test Display')
    grid_section = display.add_section('Grid')

    grid_section.add_column('Grid', 20)
    grid_section.add_column('Total', 10, title_alignment='^', field_alignment='>')
    grid_section.add_column('L1', 10, title_alignment='^', field_alignment='>')
    grid_section.add_column('L2', 10, title_alignment='^', field_alignment='>')
    grid_section.add_column('Comments', 20)

    grid_section.add_parameter_and_comment('Grid Power:', 'Grid power used')
    grid_section.add_parameter_and_comment('Grid Voltage:', 'Grid voltage')
    grid_section.add_parameter_and_comment('Grid Power Factor:', 'Power Factor')
    grid_section.add_parameter_and_comment('Grid Frequency:', 'Grid AC frequency')

    display.set_float_value('Grid', 'Grid Power:', 'Total', 5000, 'W')
    display.update()
