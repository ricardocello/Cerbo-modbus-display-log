# -------------------------------------------------------------------------------------------------------------------
# Implements a class to read and write tab-delimited columnar log files conveniently.
# This is generically useful, although some convenience functions specific to ricardocello are present as well.
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

from datetime import datetime
import gzip
import shutil


class Column:
    # Represents a column in the log file.
    # The format should be in format_string format, e.g. :6.2f
    # By default, for writing files, the format is a string.
    # The format specification is not used when reading files.

    def __init__(self, name, fmt=''):
        self.name = name
        self.format = fmt
        self.value = None

    def value_string(self):
        # Returns a string representing the current value in the desired format

        if self.value is None:
            return ''
        fmt_str = '{' + f'{self.format}' + '}'
        return fmt_str.format(self.value)


class TabDelimitedLogWriter:
    # Creates a columnar log file separated by tabs.
    # Provides convenient functions for writing data.

    def __init__(self, filename):
        self.filename = filename
        self.file = None
        self.columns = {}

    def create_or_update_file(self):
        # Read the existing log file starting date and time; if nothing in file, create a new file
        dt = self.current_file_start_date_time()
        if dt is None:
            print(f'# Creating new log file {self.filename}')
            self.file = open(self.filename, 'w')
            return
        (log_date, log_time) = dt

        # Check the current date; if it matches the log file, just append to existing log file
        ts = datetime.now()
        current_date = ts.strftime('%Y-%m-%d')
        if log_date == current_date:
            print(f'# Appending to existing log file {self.filename}')
            self.file = open(self.filename, 'a')
            return

        # Compress the existing log file with its starting date and time in the filename
        gzip_filename = f'Log_{log_date}_{log_time}.gz'
        print(f'# Archiving and compressing existing log file {self.filename} as {gzip_filename}...')
        with open(self.filename, 'rb') as f_in:
            with gzip.open(gzip_filename, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Create a new log file, overwriting the old one which has just been archived
        print(f'# Creating new log file {self.filename}')
        self.file = open(self.filename, 'w')

    def current_file_start_date_time(self):
        # Returns the starting date and time of the log file by reading the first row of data.
        # Returns None if it cannot read the file or the file contains no date or time information.
        words = None
        try:
            with open(self.filename, 'r') as f:
                try:
                    f.readline()   # skip header
                    first_row = f.readline()
                    w = first_row.split()
                    if len(w) >= 2:
                        words = (w[0], w[1])
                except IOError:
                    pass
        except FileNotFoundError:
            pass
        return words

    def add_column(self, name, fmt=''):
        self.columns[name] = Column(name, fmt)

    def add_timestamp_column(self):
        self.columns['Timestamp'] = Column('Timestamp')

    def add_power_columns(self, name, fmt=':.0f'):
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.columns[name] = Column(name, fmt)
        self.columns[l1] = Column(l1, fmt)
        self.columns[l2] = Column(l2, fmt)

    def add_pf_columns(self, name, fmt=':.2f'):
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.columns[name] = Column(name, fmt)
        self.columns[l1] = Column(l1, fmt)
        self.columns[l2] = Column(l2, fmt)

    def add_pv_columns(self, name, fmt=':.1f'):
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.columns[name] = Column(name, fmt)
        self.columns[mppt_250_70] = Column(mppt_250_70, fmt)
        self.columns[mppt_250_100] = Column(mppt_250_100, fmt)

    def add_2pv_columns(self, name, fmt=':.1f'):
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.columns[mppt_250_70] = Column(mppt_250_70, fmt)
        self.columns[mppt_250_100] = Column(mppt_250_100, fmt)

    def log_header(self):
        for name in self.columns:
            self.file.write(f'{name}\t')
        self.file.write('\n')
        self.file.flush()

    def add_row_value(self, name, value):
        self.columns[name].value = value

    def add_row_values(self, names, values):
        for n, v in zip(names, values):
            self.add_row_value(n, v)

    def add_power_values(self, name, values):
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.add_row_value(name, values[0])
        self.add_row_value(l1, values[1])
        self.add_row_value(l2, values[2])

    def add_pf_values(self, name, values):
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        self.add_row_value(name, values[0])
        self.add_row_value(l1, values[1])
        self.add_row_value(l2, values[2])

    def add_pv_values(self, name, values):
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.add_row_value(name, values[0])
        self.add_row_value(mppt_250_70, values[1])
        self.add_row_value(mppt_250_100, values[2])

    def add_2pv_values(self, name, values):
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        self.add_row_value(mppt_250_70, values[0])
        self.add_row_value(mppt_250_100, values[1])

    def log_row(self):
        for name, c in self.columns.items():
            if name == 'Timestamp':
                ts = datetime.now()
                formatted_timestamp = ts.strftime('%Y-%m-%d %H:%M:%S')
                self.file.write(f'{formatted_timestamp}\t')
            else:
                self.file.write(f'{c.value_string()}\t')
        self.file.write('\n')
        self.file.flush()


class TabDelimitedLogReader:
    # Reads a columnar log file separated by tabs

    def __init__(self, filename):
        self.filename = filename
        self.file = None
        self.columns = {}
        self.line_count = 0

    def open_file(self):
        # Reads an existing file one row at a time
        self.file = open(self.filename, 'r')
        header = self.read_next_line()
        for name in header:
            self.columns[name] = Column(name)

    def read_next_row(self):
        # Reads the next row and assigns values to each column
        # Ignore redundant header lines
        # Returns 1 if done reading file, 0 otherwise
        while True:
            values = self.read_next_line()
            if not values or not values[0]:
                return 1
            if values[0] != 'Timestamp':
                break

        # print(f'Line {self.line_count}')
        for index, c in enumerate(self.columns):
            self.columns[c].value = values[index]
            # print(index, c, values[index])
        return 0

    def get_string_value(self, name):
        # Returns the current value for the specified column as a string.
        return self.columns[name].value

    def get_int_value(self, name):
        # Returns the current value for the specified column as an integer.
        return int(self.columns[name].value)

    def get_float_value(self, name):
        # Returns the current value for the specified column as a float.
        return float(self.columns[name].value)

    def get_power_values(self, name):
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        return int(self.columns[name].value), int(self.columns[l1].value), int(self.columns[l2].value)

    def get_3float_values(self, name):
        l1 = 'L1 ' + name
        l2 = 'L2 ' + name
        return float(self.columns[name].value), float(self.columns[l1].value), float(self.columns[l2].value)

    def get_pv_values(self, name):
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        return float(self.columns[name].value), float(self.columns[mppt_250_70].value), \
            float(self.columns[mppt_250_100].value)

    def get_2pv_values(self, name):
        mppt_250_70 = '250/70 ' + name
        mppt_250_100 = '250/100 ' + name
        return float(self.columns[mppt_250_70].value), float(self.columns[mppt_250_100].value)

    def read_next_line(self):
        # Reads the next line from the file and splits it into a tuple
        line = self.file.readline().rstrip()
        self.line_count += 1
        return line.split('\t')
