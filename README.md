**Cerbo-modbus-display-log project
**


Communicates with a Victron ESS controlled by the Cerbo GX device using ModbusTCP.
Displays an ANSI status screen in a terminal window and logs overall status of the entire system every second.

Python 3.10.10 was used to test this code, and there are no external dependencies :-) yay!

Important Note: The ess_gx.py application is specific to ricardocello Victron setup and should be used as an example

of how to implement a tool to monitor a Cerbo GX or other VenusOS device locally using ModbusTCP.

See https://www.victronenergy.com/upload/documents/CCGX-Modbus-TCP-register-list-3.60.xlsx for a list

of all of the Modbus registers provided by VenusOS.

Individual device files contain unit tests that demonstrate pulling various kinds of data from the Cerbo.

Some of these should execute without any modification on any system.

See settings_gx.py for Modbus Unit Ids for all devices in the system. These will vary depending on

how the Victron system is configured.

High Level Cerbo Device Files 

ess_gx.py        Main application to show status updates and log data at 1 Hz, specific to ricardocello

settings_gx.py   Modbus Unit Ids defined for the system, and IP address of the Cerbo GX

cerbo_gx.py        Base class for all other devices

system_gx.py       Handles the high-level system device on the Cerbo GX

acload_gx.py       Handles an energy meter used in an AC Load role; tested with emulated VM-3P75CT meters

battery_gx.py      Handles a VE.Can (CANBus) battery BMS; only tested with EG4-LL v1 batteries

grid_gx.py         Handles a Grid Meter device

mppt_gx.py         Handles Smart Solar VE.Can MPPTs, specific to ricardocello 250/70 and 250/100 configuration

quattro_gx.py      Handles split-phase Quattos (or Multiplus or Multiplus-II), only split=phase is supported

shunt_gx.py        Handles Victron shunts used as battery monitor and as a DC Source

temperature_gx.py  Handles temperature sensors

I/O Files

color_status_display.py   Implements a class to conveniently display columnar data in an ANSI terminal window

tab_delimited_log.py      Implements a tab delimited file logging and archiving mechanism

modbus_tcp_client.py      A standalone implementation of a ModbusTCP client to talk to the Cerbo GX;
                          this is NOT based on pyModbus and can be used standalone to talk to any ModbusTCP device

