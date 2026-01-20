# -------------------------------------------------------------------------------------------------------------------
# Implements a class for communicating with a ModbusTCP server device over a TCP socket.
# This is an asyncio implementation with no external dependencies :-)
# This implementation has been successfully tested with Python 3.10.10.
#
# The Unit Id defaults to 1, be sure to change it as necessary.
# By default, reads are performed with Function Code 3 (Read Holding Registers).
# Change self.read_function to 4 (Read Input Registers) for devices that need it.
# Timeouts for both connection and reading are implemented for robustness.
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

import struct
import asyncio


class ModbusTCPClient:
    # ----- Settings -----
    DEBUG = False
    DEFAULT_PORT = 502               # 502 is for ModbusTCP
    CONNECT_TIMEOUT = 2.0            # seconds
    READ_TIMEOUT = 1.0               # seconds
    WRITE_TIMEOUT = 1.0              # seconds
    DISCONNECT_POLL = 1.0            # seconds

    errors = ()  # list of error exceptions possible when reading/writing

    @staticmethod
    def dprint(*args, **kwargs):
        if ModbusTCPClient.DEBUG:
            print(*args, **kwargs)

    class Error(Exception):             # Used to indicate a ModbusTCP error
        pass

    class Disconnected(Exception):      # Used to indicate that the previous connection is gone
        pass

    def __init__(self, unit_id=1, read_function_code=3):
        self.reader = None              # created by asyncio.open_connection()
        self.writer = None
        self.connect_callback = None    # user can hook in a callback function when a connection is made
        self.connected = False
        self.request_queue = None       # optional background queued requests
        self.response_queue = None

        self.mbap = bytearray((0, 0, 0, 0, 0, 0, 1))
        self.unit_id = unit_id
        self.set_unit_id(unit_id)
        self.read_function = read_function_code  # Change to 4 for devices needing that instead

        ModbusTCPClient.errors = (asyncio.exceptions.TimeoutError,
                                  asyncio.exceptions.CancelledError,
                                  ModbusTCPClient.Error)

    def set_unit_id(self, unit_id):
        self.unit_id = unit_id
        self.mbap[6] = unit_id

    def set_mbap_length(self, byte_count):
        self.mbap[4] = byte_count >> 8
        self.mbap[5] = byte_count & 0xff

    # ---------------------------------------------------------------------------------------------------------------
    #  Connecting and Disconnecting
    # ---------------------------------------------------------------------------------------------------------------
    async def connect_watchdog(self, ip_addr):
        # Should be run in its own asyncio task to connect to the device, wait for disconnection, and
        # automatically reconnect, forever.
        # This will ensure robust connections that recover from network issues automatically.
        # Alternatively, use connect() and close() directly to manage connections.

        # Run forever
        while True:

            # Try to connect (with timeout)
            r = await self.connect(ip_addr)
            if r:
                await asyncio.sleep(self.CONNECT_TIMEOUT)   # Pause, then try again to connect
                continue

            # Wait until disconnected
            await self.wait_until_disconnected()

            # Disconnected now, pause before attempting to reconnect
            await asyncio.sleep(self.CONNECT_TIMEOUT)

    async def connect(self, ip_addr):
        # Attempts to connect to the ModbusTCP device at the specified address with a timeout.
        # Has no effect if already connected.
        # Returns 0 if successful, 1 if not.

        if self.connected:
            return 0

        try:
            self.dprint(f'# ModbusTCP.connect: Connecting to {ip_addr}...')
            await asyncio.wait_for(self.connect_device(ip_addr), self.CONNECT_TIMEOUT)

        except ModbusTCPClient.Error:
            self.dprint(f'# ModbusTCP.connect: Bad connection with {ip_addr}')
            return 1

        except (OSError, asyncio.exceptions.TimeoutError, asyncio.exceptions.CancelledError):
            self.dprint(f'# ModbusTCP.connect: Timeout connecting to {ip_addr}')
            return 1

        else:
            self.dprint(f'# ModbusTCP.connect: Sucessfully connected to {ip_addr}')
            if self.connect_callback:
                await self.connect_callback()
            self.connected = True
            return 0

    async def connect_device(self, addr, port=DEFAULT_PORT, reg_addr=None):
        # Attempts to connect to the ModbusTCP device at the specified address.
        # If successful, tries to read a register.
        # If it fails to connect or read the register, raises an exception.
        # Every Modbus device is different, so select a register number that is valid.

        self.dprint('# ModbusTCP.connect_device: Opening Connection...')
        self.reader, self.writer = await asyncio.open_connection(addr, port)

        try:
            if reg_addr:
                value = await self.read_uint(reg_addr)
                self.dprint(f'# ModbusTCP.connect_device: Read {value} from address {reg_addr}')

        except (asyncio.exceptions.TimeoutError, asyncio.exceptions.CancelledError) as e:
            # Connected and tried to read, but nothing came back

            self.dprint('# ModbusTCP.connect_device: Closing connection...')
            await self.close()
            await asyncio.sleep(self.CONNECT_TIMEOUT)
            raise ModbusTCPClient.Error(f'# ModbusTCP.connect_device: Timeout waiting for connection {e}')

    def is_connected(self):
        return self.connected

    async def wait_until_disconnected(self):
        # Waits until disconnection occurs (if connected) by polling.
        while self.is_connected():
            await asyncio.sleep(self.DISCONNECT_POLL)

    async def close(self):
        # Closes the connection, waits for completion, marks connected as closed.

        if not self.connected:
            return

        try:
            self.writer.close()
            await self.writer.wait_closed()
        except ConnectionResetError:
            pass

        self.writer = None
        self.reader = None
        self.connected = False

    # ---------------------------------------------------------------------------------------------------------------
    #  Writing Registers
    # ---------------------------------------------------------------------------------------------------------------
    async def write_uint(self, reg, value):
        # Writes the unsigned 16-bit value to the specified register with a timeout.
        await self.write_register(reg, value)

    async def write_int(self, reg, value):
        # Writes the signed 16-bit value to the specified register with a timeout.
        b = struct.pack('h', value)
        await self.write_register(reg, struct.unpack('H', b)[0])

    async def write_register(self, addr, value):
        # Writes the unsigned 16-bit value to the specified address with a timeout.
        return await asyncio.wait_for(self.write_register_no_timeout(addr, value), self.WRITE_TIMEOUT)

    async def write_register_no_timeout(self, addr, value):
        # Writes the unsigned 16-bit value to the specified address.
        #
        # ModbusTCP Write Register: Function 0x06
        #   Command:  <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #             <func> <addr_h> <addr_l> <value_h> <value_l>
        #
        #   Response: <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #             <func> <addr_h> <addr_l> <value_h> <value_l>
        #
        # ModbusTCP Error Response
        #   <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #   <func|0x80> <exc_code>

        self.set_mbap_length(6)
        cmd = struct.pack('>7BBHH', *self.mbap, 0x06, addr, value)

        self.writer.write(cmd)
        await self.writer.drain()

        rsp = await self.reader.readexactly(8)
        if (rsp[7] & 0x80) != 0:
            rsp += await self.reader.readexactly(1)
            raise ModbusTCPClient.Error(f'ModbusTCP Exception 0x{rsp[8]:x}: {rsp.hex()}')

        rsp += await self.reader.readexactly(4)

    async def write_registers(self, addr, values):
        # Writes unsigned 16-bit values to the specified address.
        # values should be an array (tuple or list).
        return await asyncio.wait_for(self.write_registers_no_timeout(addr, values), self.WRITE_TIMEOUT)

    async def write_registers_no_timeout(self, addr, values):
        # Writes unsigned 16-bit values to the specified address.
        # values should be an array (tuple or list).
        #
        # ModbusTCP Write Multiple Registers: Function 0x10
        #   Command:  <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #             <func> <addr_h> <addr_l> <count_h> <count_l> <byte_count>
        #             <data_h> <data_l> ...
        #
        #   Response: <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #             <func> <addr_h> <addr_l> <count_h> <count_l>
        #
        # ModbusTCP Error Response
        #   <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #   <func|0x80> <exc_code>

        count = values.length()
        if count == 0:
            return

        self.set_mbap_length(7+2*count)
        cmd = struct.pack('>7BBHHB', *self.mbap, 0x10, addr, count, 2*count)

        if self.writer is None or self.reader is None:
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (no reader or writer).')

        try:
            self.writer.write(cmd)
            await self.writer.drain()

            rsp = await self.reader.readexactly(8)
            if (rsp[7] & 0x80) != 0:
                rsp += await self.reader.readexactly(1)
                raise ModbusTCPClient.Error(f'ModbusTCP Exception 0x{rsp[8]:x}: {rsp.hex()}')

            rsp += await self.reader.readexactly(4)

        except AttributeError:   # caused by reader or writer being sset to None
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected.')

        except asyncio.IncompleteReadError:  # cause by disconnect
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (incomplete read).')

        except asyncio.exceptions.CancelledError:  # cause by disconnect
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (canceled).')

        except asyncio.exceptions.TimeoutError:  # cause by disconnect
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (timeout).')

    # ---------------------------------------------------------------------------------------------------------------
    #  Reading Registers
    #  Registers can be read directly or queued up and read by a background asycio task.
    # ---------------------------------------------------------------------------------------------------------------
    async def read_watchdog(self):
        # Should be run in its own asyncio task forever.
        #
        # Call background_request() to queue up a request to read some registers.
        # Call read_background() to block and wait for the response.
        #
        # This approach allows requests to be queued to multiple devices nearly simultaneously, for example,
        # enabling full rate communication.
        #
        # This task just sits in the background waiting for requests from the queue, and
        # executing them when they come in.

        self.request_queue = asyncio.Queue(1)
        self.response_queue = asyncio.Queue(1)

        while True:
            (address, count) = await self.request_queue.get()
            regs = None
            if self.connected:
                try:
                    regs = await self.read_registers(address, count)

                except self.errors:
                    self.dprint(f'# read_watchdog: Lost connection with the ModbusTCP server')
                    await self.close()

            await self.response_queue.put(regs)

    async def background_request(self, address, count):
        # Queues a request to read the specified registers.
        # Does not block unless the queue is full.
        # The read_watchdog task must be running.

        await self.request_queue.put((address, count))

    async def read_background(self):
        # Gets the register values from the last queued background_request().
        # Returns None when connection is not available.
        # Should always be paired with a call to background_request().
        # The read_watchdog task must be running.

        return await self.response_queue.get()

    async def read_uint(self, reg):
        # Reads the specified register as an unsigned 16-bit integer with a timeout.
        return await self.read_register(reg)

    async def read_int(self, reg):
        # Reads the specified register as a signed 16-bit integer with a timeout.
        v = await self.read_register(reg)
        return self.make_signed(v)

    async def read_register(self, addr):
        # Returns an unsigned 16-bit register value with a timeout.
        v = await self.read_registers(addr, 1)
        return v[0]

    async def read_registers(self, addr, count):
        # Returns an array of unsigned 16-bit register values by reading with a timeout.
        return await asyncio.wait_for(self.read_registers_no_timeout(addr, count), self.READ_TIMEOUT)

    async def read_registers_no_timeout(self, addr, count):
        # Returns an array of unsigned 16-bit register values.
        #
        # ModbusTCP Read Multiple Registers: Functions 0x03 and 0x04
        #   Command:  <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #             <func> <addr_h> <addr_l> <count_h> <count_l>
        #
        #   Response: <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #             <func> <byte_count> <word_h> <word_l> ...
        #
        # ModbusTCP Error Response
        #   <tid_h> <tid_l> <pid_h> <pid_l> <length_h> <length_l> <unit_id>
        #   <func|0x80> <exc_code>

        self.set_mbap_length(6)
        cmd = struct.pack('>7BBHH', *self.mbap, self.read_function, addr, count)
        # print(cmd.hex())

        if self.writer is None or self.reader is None:
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (no reader or writer).')

        try:
            self.writer.write(cmd)
            await self.writer.drain()

            rsp = await self.reader.readexactly(8)
            if (rsp[7] & 0x80) != 0:
                rsp += await self.reader.readexactly(1)
                raise ModbusTCPClient.Error(f'# ModbusTCP: ModbusTCP Exception 0x{rsp[8]:x}: {rsp.hex()}')

            rsp += await self.reader.readexactly(1+2*count)
            # print(rsp.hex())

        except AttributeError:  # caused by reader or writer being set to None
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected.')

        except asyncio.IncompleteReadError:  # cause by disconnect
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (incomplete read).')

        except asyncio.exceptions.CancelledError:  # cause by disconnect
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (canceled).')

        except asyncio.exceptions.TimeoutError:  # cause by disconnect
            raise ModbusTCPClient.Disconnected(f'# ModbusTCP: Remote server has disconnected (timeout).')

        regs = struct.unpack(f'>{count}H', rsp[9:])
        return regs

    @staticmethod
    def make_signed(value):
        b = struct.pack('H', value)
        return struct.unpack('h', b)[0]

    @staticmethod
    def make_signed32(values):
        b = struct.pack('2H', values[1], values[0])
        return struct.unpack('i', b)[0]

    # ---------------------------------------------------------------------------------------------------------------
    #  Unit Testing
    # ---------------------------------------------------------------------------------------------------------------
    async def main_poll_test(self, addr):
        # Unit Test Example
        # Keep trying to connect, until successful.
        # Retries automatically when disconnected.
        # Continuously reads some registers and displays their values.

        await asyncio.create_task(self.connect_watchdog(addr))

        while True:
            while not self.is_connected():
                await asyncio.sleep(1.0)

            print(f'# Reading Cerbo GX System registers at {addr} for grid input power...')
            while True:
                try:
                    l1_w = await self.read_int(820)   # data is signed 16-bit with no scaling factor
                    l2_w = await self.read_int(821)
                    l3_w = await self.read_int(822)

                    print(f'# Grid Input Power (L1, L2, L3): {l1_w:5} W  {l2_w:5} W  {l3_w:5} W')
                    await asyncio.sleep(1.0)

                except self.errors as e:
                    print(f'{e}')
                    self.dprint(f'# ModbusTCP.main_poll_test: Lost connection with ModbusTCP device at {addr}')
                    await self.close()
                    break


if __name__ == "__main__":
    # Unit Test code for Cerbo GX ModbusTCP System Device

    mc = ModbusTCPClient(unit_id=100)
    asyncio.run(mc.main_poll_test('192.168.169.55'))
