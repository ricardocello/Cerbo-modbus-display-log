# -------------------------------------------------------------------------------------------------------------------
# Implements a class to read and write tab-delimited columnar log files conveniently.
# This is a generically useful class.
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
    # Represents a column in the log file for both writing and reading.
    # The format should be in format_string format, e.g. 6.2f
    # By default, for writing files, the format is a string.
    #
    # The format specification is not used when reading files.
    # When reading, it is possible to save columnar values for later analysis.

    def __init__(self, name, fmt=''):
        self.name = name
        self.format = fmt
        self.value = None          # current value
        self.saved_values = None   # a list of saved values for Reader only, populated only when this is a list

    def value_string(self):
        # Returns a string representing the current value in the desired format

        if self.value is None:
            return ''
        fmt_str = '{' + f'{self.format}' + '}'
        # print('<Debug> ', self.name, self.format, self.value, fmt_str)
        return fmt_str.format(self.value)

    def save_values(self):
        self.saved_values = []  # marks the column so that values will be saved here


class TabDelimitedLogWriter:
    # Creates a columnar log file separated by tabs.
    # Provides convenient functions for writing data.

    def __init__(self, filename):
        self.filename = filename
        self.file = None
        self.columns = {}
        self.line_count = 0

    def create_file(self, append=False):
        self.file = open(self.filename, 'a' if append else 'w')

    def close(self):
        self.file.close()
        self.file = None

    def create_or_update_file(self):
        # Read the existing log file starting date and time; if nothing in file, create a new file.
        # Returns 1 if a new file is created, 0 if not.

        dt = self.file_start_date_time(self.filename)
        if dt is None:
            print(f'# Creating new log file {self.filename}')
            self.file = open(self.filename, 'w')
            return 1

        # Check the current date; if it matches the log file, just append to existing log file
        (log_date, log_time) = dt
        ts = datetime.now()
        current_date = ts.strftime('%Y-%m-%d')

        if log_date == current_date:
            print(f'# Appending to existing log file {self.filename}')
            self.file = open(self.filename, 'a')
            return 0

        # It is a new day, so compress the existing log file with its starting date and time in the filename
        gzip_filename = f'Log_{log_date}_{log_time}.gz'
        print(f'# Archiving and compressing existing log file {self.filename} as {gzip_filename}...')

        with open(self.filename, 'rb') as f_in:
            with gzip.open(gzip_filename, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Create a new log file, overwriting the old one which has just been archived
        print(f'# Creating new log file {self.filename}')
        self.file = open(self.filename, 'w')
        return 1

    @staticmethod
    def file_start_date_time(filename):
        # Returns the starting date and time of the log file by reading the first row of data.
        # Returns None if it cannot read the file or the file contains no date or time information.
        words = None
        try:
            with open(filename, 'r') as f:
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

    def log_header(self):
        for name in self.columns:
            self.file.write(f'{name}\t')
        self.file.write('\n')
        self.line_count += 1
        self.file.flush()

    def set_row_value(self, name, value):
        self.columns[name].value = value

    def set_row_values(self, names, values):
        for n, v in zip(names, values):
            self.set_row_value(n, v)

    def log_row(self):
        for name, c in self.columns.items():
            if name == 'Timestamp':
                ts = datetime.now()
                formatted_timestamp = ts.strftime('%Y-%m-%d %H:%M:%S')
                self.file.write(f'{formatted_timestamp}\t')
            else:
                self.file.write(f'{c.value_string()}\t')
        self.file.write('\n')
        self.line_count += 1
        self.file.flush()


class TabDelimitedLogReader:
    # Reads a columnar log file separated by tabs

    def __init__(self, filename):
        self.filename = filename
        self.file = None
        self.columns = {}
        self.line_count = 0
        self.reading_gzip = False

    def open_file(self):
        # Reads an existing file one row at a time
        self.file = open(self.filename, 'r')
        header = self.read_next_line()
        for name in header:
            self.columns[name] = Column(name)

    def open_gzip_file(self):
        # Reads an existing gzip compressed file one row at a time
        self.file = gzip.open(self.filename, 'rb')
        self.reading_gzip = True

        header = self.read_next_line()
        for name in header:
            self.columns[name] = Column(name)

    def save_column(self, name, save=True):
        # Marks the column so that it saves each value in the file as it is read
        self.columns[name].saved_values = [] if save else None

    def read_whole_file(self):
        # Reads the whole file in; useful for saving columns for later processing
        while not self.read_next_row():
            print(f'Line {self.line_count}')

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

        for index, cname in enumerate(self.columns):
            c = self.columns[cname]
            c.value = values[index]
            if c.saved_values is not None:
                c.saved_values.append(values[index])
            # print(index, cname, values[index])
        return 0

    def get_string_value(self, name):
        # Returns the current value for the specified column as a string.
        try:
            return self.columns[name].value
        except KeyError:
            return ''

    def get_int_value(self, name):
        # Returns the current value for the specified column as an integer.
        try:
            return int(self.columns[name].value)
        except KeyError:
            return 0

    def get_float_value(self, name):
        # Returns the current value for the specified column as a float.
        try:
            return float(self.columns[name].value)
        except KeyError:
            return 0.0

    def read_next_line(self):
        # Reads the next line from the file and splits it into a tuple
        line = self.file.readline().rstrip()
        self.line_count += 1
        if self.reading_gzip:
            line = line.decode('utf-8')
        return line.split('\t')


if __name__ == "__main__":
    # Execute main() if this file is executed directly

    reader = TabDelimitedLogReader('ess.log.gz')
    reader.open_gzip_file()
    reader.save_column('Grid Power (W)')
    reader.read_whole_file()
    print(reader.columns['Grid Power (W)'].saved_values)
