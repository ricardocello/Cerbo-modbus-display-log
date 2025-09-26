# -------------------------------------------------------------------------------------------------------------------
# Implements a base class to implement ModbusTCPClient register read and write functions for the Cerbo GX.
# This class is to be used to communicate with all devices attached to the Cerbo GX.
# Derived classes include System, Battery, Quattros, GridMeter, etc.
#
# This code assumes a split-phase system, and will need modifications to support three-phase systems.
# L3 is specifically ignored everywhere in this code for convenience.
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

import settings_gx
from modbus_tcp_client import ModbusTCPClient


class CerboGX:
    # Derive specific attached devices from this base class

    def __init__(self, addr=settings_gx.GX_IP_ADDRESS, uid=100):
        self.ip_address = addr
        self.unit_id = uid
        self.client = ModbusTCPClient(unit_id=uid)
        self.errors = ModbusTCPClient.errors

    async def connect(self):
        # Connects to the Cerbo GX
        return await self.client.connect(self.ip_address)

    async def disconnect(self):
        # Disconnects from the Cerbo GX
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
