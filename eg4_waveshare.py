# -------------------------------------------------------------------------------------------------------------------
# Implements a class to communicate with a rack of EG4-LL batteries via a Waveshare ethernet device
# and RS-485 Modbus RTU. The Waveshare device automatically translates from ModbusTCP to/from ModbusRTU.
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
import struct
from modbus_tcp_client import ModbusTCPClient


class EG4Waveshare:
    def __init__(self, addr='192.168.112.104', uid=1):
        self.ip_address = addr
        self.client = ModbusTCPClient(unit_id=uid)
        self.errors = ModbusTCPClient.errors

        self.model = ''
        self.firmware_version = ''
        self.serial_number = ''

        self.voltage = 0.0                # Volts
        self.current = 0.0                # Amps
        self.cell_voltages = [0.0] * 16   # Volts
        self.min_cell_voltage = 0.0       # Volts
        self.max_cell_voltage = 0.0       # Volts
        self.max_deviation = 0.0          # Volts
        self.pcb_temp = -273.0            # deg C
        self.avg_temp = -273.0
        self.max_temp = -273.0

        self.capacity_remaining, self.max_charge_current, self.soh, self.soc = [0] * 4
        self.status, self.warn, self.protect, self.error = [0] * 4
        self.cycle_count = 0
        self.full_capacity = 0         # Ah
        self.temps = [-273] * 6        # Deg C
        self.number_of_cells = 0
        self.designed_capacity = 0.0   # Ah
        self.balance = 0

        self.status_str = ''
        self.warning_str = ''
        self.protection_str = ''
        self.error_str = ''
        self.balance_str_1_8 = ''
        self.balance_str_9_16 = ''

    async def read_info(self, uid=1):
        self.client.set_unit_id(uid)
        r = await self.read(105, 23)

        self.model = self.make_string(r[0:12])
        self.firmware_version = self.make_string(r[12:15])
        self.serial_number = self.make_string(r[15:23])

    async def read_current_state(self, uid=1):
        self.client.set_unit_id(uid)
        r = await self.read(0, 39)

        self.voltage = 0.01 * r[0]                           # Volts
        self.current = 0.01 * self.make_signed(r[1])         # Amps
        self.cell_voltages = [v / 1000.0 for v in r[2:18]]   # Volts
        self.min_cell_voltage = min(self.cell_voltages)
        self.max_cell_voltage = max(self.cell_voltages)
        self.max_deviation = self.max_cell_voltage - self.min_cell_voltage  # Volts

        self.pcb_temp = self.make_signed(r[18])              # deg C
        self.avg_temp = self.make_signed(r[19])
        self.max_temp = self.make_signed(r[20])

        self.capacity_remaining, self.max_charge_current, self.soh, self.soc = r[21:25]
        self.status, self.warn, self.protect, self.error = r[25:29]
        self.cycle_count = self.make_unsigned32(r[29:31])
        self.full_capacity = self.make_unsigned32(r[31:33]) / 3600000.0  # Ah

        temps = [r[33] // 256, r[33] % 256, r[34] // 256, r[34] % 256, r[35] // 256, r[35] % 256]
        self.temps = [(t if t < 128 else -256 + t) for t in temps]

        self.number_of_cells = r[36]
        self.designed_capacity = 0.1 * r[37]   # Ah
        self.balance = r[38]

        match self.status & 0x000f:
            case 0x0000:
                self.status_str = 'Stand By'
            case 0x0001:
                self.status_str = 'Charging'
            case 0x0002:
                self.status_str = 'Discharging'
            case 0x0004:
                self.status_str = 'Protect'
            case 0x0008:
                self.status_str = 'Charging Limit'
            case _:
                self.status_str = 'Unknown'

        if self.status & 0x8000:
            self.status_str += ', Heat On'

        self.warning_str = ''
        if self.warn & 0x0001:
            self.warning_str += '|Pack Over-Voltage'
        if self.warn & 0x0002:
            self.warning_str += '|Cell Over-Voltage'
        if self.warn & 0x0004:
            self.warning_str += '|Pack Under-Voltage'
        if self.warn & 0x0008:
            self.warning_str += '|Cell Under-Voltage'
        if self.warn & 0x0010:
            self.warning_str += '|Charge Over-Current'
        if self.warn & 0x0020:
            self.warning_str += '|Discharge Over-Current'
        if self.warn & 0x0040:
            self.warning_str += '|Abnormal Temperature'
        if self.warn & 0x0080:
            self.warning_str += '|MOSFETs Overheating'
        if self.warn & 0x0100:
            self.warning_str += '|Charge Over-Temperature'
        if self.warn & 0x0200:
            self.warning_str += '|Discharge Over-Temperature'
        if self.warn & 0x0400:
            self.warning_str += '|Charge Under-Temperature'
        if self.warn & 0x0800:
            self.warning_str += '|Discharge Under-Temperature'
        if self.warn & 0x1000:
            self.warning_str += '|Low Capacity'
        if self.warn & 0x2000:
            self.warning_str += '|Other Error'
        if self.warn & 0x4000:
            self.warning_str += '|Unknown 0x4000'
        if self.warn & 0x8000:
            self.warning_str += '|Unknown 0x8000'
        if self.warning_str == '':
            self.warning_str = 'None'

        self.protection_str = ''
        if self.protect & 0x0001:
            self.protection_str += '|Pack Over-Voltage'
        if self.protect & 0x0002:
            self.protection_str += '|Cell Over-Voltage'
        if self.protect & 0x0004:
            self.protection_str += '|Pack Under-Voltage'
        if self.protect & 0x0008:
            self.protection_str += '|Cell Under-Voltage'
        if self.protect & 0x0010:
            self.protection_str += '|Charge Over-Current'
        if self.protect & 0x0020:
            self.protection_str += '|Discharge Over-Current'
        if self.protect & 0x0040:
            self.protection_str += '|Abnormal Temperature'
        if self.protect & 0x0080:
            self.protection_str += '|MOSFETs Overheating'
        if self.protect & 0x0100:
            self.protection_str += '|Charge Over-Temperature'
        if self.protect & 0x0200:
            self.protection_str += '|Discharge Over-Temperature'
        if self.protect & 0x0400:
            self.protection_str += '|Charge Under-Temperature'
        if self.protect & 0x0800:
            self.protection_str += '|Discharge Under-Temperature'
        if self.protect & 0x1000:
            self.protection_str += '|Float Stopped'
        if self.protect & 0x2000:
            self.protection_str += '|Discharge Short Circuit'
        if self.protect & 0x4000:
            self.protection_str += '|Unknown 0x4000'
        if self.protect & 0x8000:
            self.protection_str += '|Unknown 0x8000'
        if self.protection_str == '':
            self.protection_str = 'None'

        self.error_str = ''
        if self.error & 0x0001:
            self.error_str += '|Voltage'
        if self.error & 0x0002:
            self.error_str += '|Termperature'
        if self.error & 0x0004:
            self.error_str += '|Current Flow'
        if self.error & 0x0010:
            self.error_str += '|Cell Unbalance'
        if self.error_str == '':
            self.error_str = 'None'

        self.balance_str_1_8 = ''
        self.balance_str_9_16 = ''
        for i in range(8):
            bit = (self.balance >> i) & 1
            self.balance_str_1_8 += '  X   ' if bit else '  O   '

            bit = (self.balance >> (8+i)) & 1
            self.balance_str_9_16 += '  X   ' if bit else '  O   '

    def show_state(self):
        cv_1_8 = cv_9_16 = ''
        for v in self.cell_voltages[0:8]:
            cv_1_8 += f'{v:.3f} '
        for v in self.cell_voltages[8:16]:
            cv_9_16 += f'{v:.3f} '

        print(f'---------------------------------------------------------------------------------')
        print(f'Unit Id:                {self.client.unit_id}')
        print(f'Model:                  {self.model}')
        print(f'Firmware Version:       {self.firmware_version}')
        print(f'Serial Number:          {self.serial_number}')
        print(f'State of Charge:        {self.soc} %')
        print(f'Voltage:                {self.voltage:.1f} V')
        print(f'Current:                {self.current:.1f} A')
        print(f'Maximum Charge Current: {self.max_charge_current} A')
        print(f'Cell Voltages:          {cv_1_8}V')
        print(f'Balancing Status:       {self.balance_str_1_8}')
        print(f'Cell Voltages:          {cv_9_16}V')
        print(f'Balancing Status:       {self.balance_str_9_16}')
        print(f'Min/Max Cell Voltage:   {self.min_cell_voltage:.3f} {self.max_cell_voltage:.3f}')
        print(f'Min/Max Cell Deviation: {self.max_deviation:.3f} V')
        print(f'Temperatures:           PCB {self.pcb_temp} Avg {self.avg_temp} Max {self.max_temp} deg C')
        print(f'Temperatures:           {self.temps[0]} {self.temps[1]} {self.temps[2]} {self.temps[3]} '
              f'{self.temps[4]} {self.temps[5]} deg C')
        print(f'Status:                 {self.status_str}')
        print(f'Warnings:               {self.warning_str}')
        print(f'Protection:             {self.protection_str}')
        print(f'Errors:                 {self.error_str}')
        print(f'Cycle Count:            {self.cycle_count}')
        print(f'Number of Cells:        {self.number_of_cells}')
        print(f'State of Health:        {self.soh} %')
        print(f'Remaining Capacity:     {self.capacity_remaining} Ah')
        print(f'Full Capacity:          {self.full_capacity:.1f} Ah')
        print(f'Designed Capacity:      {self.designed_capacity:.1f} Ah')

    async def connect(self):
        # Connects to the Waveshare device
        return await self.client.connect(self.ip_address)

    async def disconnect(self):
        # Disconnects from the Waveshare device
        await self.client.close()

    async def read(self, reg, num):
        # Reads 16-bit unsigned modbus registers
        return await self.client.read_registers(reg, num)

    async def read_uint(self, reg):
        # Reads a 16-bit unsigned modbus register
        return await self.client.read_uint(reg)

    async def read_int(self, reg):
        # Reads a 16-bit signed modbus register
        return await self.client.read_int(reg)

    async def write_uint(self, reg, value):
        # Writes a 16-bit unsigned modbus register
        await self.client.write_uint(reg, value)

    async def write_int(self, reg, value):
        # Writes a 16-bit signed modbus register
        await self.client.write_int(reg, value)

    @staticmethod
    def make_signed(value):
        # Reinterprets an unsigned 16-bit value as signed
        return ModbusTCPClient.make_signed(value)

    @staticmethod
    def make_signed32(values):
        # Returns a signed 32-bit value given two unsigned 16-bit register values
        return ModbusTCPClient.make_signed32(values)

    @staticmethod
    def make_unsigned32(values):
        # Returns an unsigned 32-bit value given two unsigned 16-bit register values
        return ModbusTCPClient.make_unsigned32(values)

    @staticmethod
    def make_string(values):
        # Returns an ascii string from the register values
        b = struct.pack(f'>{len(values)}H', *values)
        return b.decode('ascii')

    async def main(self, uid=1):
        # Unit test code to retreive info from a single battery

        # Connect to the Waveshare device
        r = await self.connect()
        if r:
            print(f'# Unable to connect to Waveshare device at {self.ip_address}')
            return

        # Read model, fw version, serial number
        await self.read_info(uid)

        # Read status
        while True:
            await self.read_current_state(uid)
            self.show_state()
            time.sleep(1.0)

    async def main_rack(self):
        # Unit test code to retreive info from 3 batteries

        # Connect to the Waveshare device
        r = await self.connect()
        if r:
            print(f'# Unable to connect to Waveshare device at {self.ip_address}')
            return

        # Read model, fw version, serial number
        await self.read_info(1)

        # Read status
        while True:
            try:
                await self.read_current_state(1)
                self.show_state()
                time.sleep(0.33)

                await self.read_current_state(2)
                self.show_state()
                time.sleep(0.33)

                await self.read_current_state(3)
                self.show_state()
                time.sleep(0.33)

            except ModbusTCPClient.Disconnected:
                print('*********** Reconnecting ***************')
                r = await self.connect()


if __name__ == "__main__":
    # Execute the unit test code if this file is executed directly
    eg4w = EG4Waveshare(addr='192.168.112.104')
    unit_id = 1

    n = len(sys.argv)
    if n > 1:
        unit_id = int(sys.argv[1])
        asyncio.run(eg4w.main(uid=unit_id))
    else:
        asyncio.run(eg4w.main_rack())
