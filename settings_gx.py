# -------------------------------------------------------------------------------------------------------------------
# Defines all custom settings for communicating with a Cerbo GX or other GX Device
#
# See https://www.victronenergy.com/upload/documents/CCGX-Modbus-TCP-register-list-3.60.xlsx
#
# Device Instances can be found in VRM under Device List,
# and in the Console under ModbusTCP Services.
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

# IP Address of the Cerbo GX (or other Venus OS device)
GX_IP_ADDRESS = '192.168.169.55'

# Unit Ids and Device Instances of specific devices in the system
# These are different for every system, and need to be configured
CANBUS_BMS = 225            # Device Instance 512 (EG4-LL Rack)
VEBUS_INVERTERS = 227       # Device Instance 276 (Quattros)
VECAN_MPPT_1 = 100          # SmartSolar MPPT VE.Can 250/70
VECAN_MPPT_2 = 1            # SmartSolar MPPT VE.Can 250/100
GRID_METER = 32             # Emulated EM530 Composite Grid Meter
ACLOAD_METER_1 = 42         # Emulated VM-3P75CT for Addition Energy Meter via UDP
ACLOAD_METER_2 = 43         # Emulated VM-3P75CT for Main House Energy Meter via UDP
ACLOAD_METER_3 = 45         # Emulated VM-3P75CT for Well and Septic Pumps using Shelly EM-50
TEMPERATURE_1 = 20          # Ruuvi Tag
TEMPERATURE_2 = 24          # Chargeverter Temperature Sensor
TEMPERATURE_3 = 25          # Rack Temperature Sensor
