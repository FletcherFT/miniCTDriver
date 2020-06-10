import re
import threading
import time

import serial

"""
List of properties that can be get and/or set as regular expressions.
"M[1,2,4,8]" - Set the miniCT into continuous read mode at a set rate (hZ)
"S" - Returns a single reading
"#001;\d+" - Sets the 485 address. (485 address Setter)
"#002" - Returns the address. (485 address Getter)
"#004" - Returns the header info. (Header info Getter)
"#005;[ON|OFF]" - Sets the address mode (Address mode Setter)
"#006" - Gets the address mode (Address mode Getter)
"#015" - Return last result (Last Getter)
"#026;\w" - Sets the output string separator (delimiter Setter)
"#027" - Gets the output string separator (delimiter Getter)
"#028" - Set the device into run mode (Run mode setter)
"#032" - Get the software version (Version getter)
"#034" - Get the unit serial number (Serial getter)
"#039;M[1,2,4,8] - Set mode without putting into run mode (Mode set no run)
"#040" - Get operating mode.
"#059;\d+ - Set the baudrate
"#082;[3,CSV,SB,RES]" - Set the output format for readings.
"#089" - Get the output format.
"#091;[ON,OFF]" - Sets miniCT startup mode.
"#102;[ON,OFF]" - Sets 485 mode.
"#103" - Sends 485 mode.
"""


class MiniCTDriver:
    """
    Class that interfaces with miniCT CTD via serial object inheritance.
    """

    def __init__(self, dev, baud=19200, timeout=0.5):
        # Initialise the serial object
        self.ser = serial.Serial(port=dev,
                                 baudrate=baud,
                                 bytesize=serial.EIGHTBITS,
                                 parity=serial.PARITY_NONE,
                                 stopbits=serial.STOPBITS_ONE,
                                 timeout=timeout,
                                 xonxoff=True,
                                 rtscts=False,
                                 write_timeout=None,
                                 dsrdtr=False,
                                 inter_byte_timeout=None,
                                 exclusive=None)
        # Start a thread for reading values
        self._listener = threading.Thread(target=self._receive_pkt, name="Thread-SerialListener")
        self._running = False  # True if driver has been started
        self._state = False  # True if driver has been put into read mode, false if in interrupt mode
        self._delimiter = ""  # Separator character for data
        self._available = False  # Flag for if new data is available
        self._values = []  # Data
        self._command = ""  # Last command sent
        self._output_format = ""  # Output format of data
        self._configured = False  # flag to check if driver has been configured
        self._lock = threading.Lock()
        # Dictionary containing configuration data
        self._datagram = {"header": {},
                          "address": "",
                          "address_mode": "",
                          "last_result": "",
                          "delimiter": "",
                          "run_mode": "",
                          "software_version": "",
                          "serial_number": "",
                          "operating_mode": "",
                          "output_format": ""}
        # Lookup table for what operation to apply to each packet type
        self._LUT = {"#002": {"name": "address", "op": str},
                     "#004": {"name": "header", "op": self._parse_header},
                     "#006": {"name": "address_mode", "op": str},
                     "#015": {"name": "last_result", "op": str},
                     "#027": {"name": "delimiter", "op": self._parse_delimiter},
                     "#029": {"name": "run_mode", "op": str},
                     "#032": {"name": "software_version", "op": str},
                     "#034": {"name": "serial_number", "op": str},
                     "#040": {"name": "operating_mode", "op": str},
                     "#089": {"name": "output_format", "op": str},
                     }

    def start(self):
        """Open serial port and start reading."""
        self._running = True
        if self.ser.closed:
            self.ser.open()
        self._listener.start()

    def config(self):
        """Fetch configuration information from the device."""
        assert self._running, "Call start method first!"
        # Get header information
        self.get_header()
        self.get_485_address()
        self.get_address_mode()
        self.get_last_result()
        self.get_delimiter()
        self.get_run_mode()
        self.get_version()
        self.get_mode()
        self.get_output_format()

    def stop(self):
        """Stop the serial port joining thread."""
        if self._running:
            self._running = False
            self._listener.join()

    def _receive_pkt(self):
        num_regex = re.compile("^\d")  # if a number
        int_regex = re.compile("^>")  # if an interrupt
        com_regex = re.compile(".*(#\d{3})")  # if a command acknowledgement
        # datagrams can be identified by the start characters
        while self._running:
            try:
                # if something detected on the serial port
                if self.ser.in_waiting:
                    # Datagrams are sent with newline delimiting
                    self._lock.acquire()
                    buff = self.ser.readline()
                    self._lock.release()
                    # Process the buffer into a data packet
                    packet = buff.decode().rstrip()
                    # TODO debugging statement here
                    # print(packet)
                    # Last value to check
                    self._last = packet
                    # if the packet starts with "#", then it is an acknowledgement of a command.
                    if re.match(com_regex, packet):
                        # get the command number
                        self._command = com_regex.search(packet).group(1)
                    elif re.match(int_regex, packet):
                        # make sure the driver is in interrupt mode
                        self._state = False
                        self._command = ""
                    # Otherwise, parse the data based on the last known command.
                    else:
                        # If the driver is in read mode and the packet starts with a number, then measurement reading.
                        if self._state and re.match(num_regex, packet):
                            self._parse_values(packet)
                        # If the driver is in interrupt mode, process the packet according to the last command.
                        elif not self._state:
                            # Parse the packet according to the lookup table
                            self._parse_packet(packet)
                time.sleep(0.01)
            except serial.SerialException:
                pass
            except ValueError:
                pass
        self.ser.close()

    def _parse_packet(self, packet):
        # if it's a single command then process like it's a number
        if self._command == "S":
            self._parse_values(packet)
        elif len(self._command) > 0:
            try:
                self._datagram[self._LUT[self._command]["name"]] = self._LUT[self._command]["op"](packet)
            except KeyError:
                pass

    def _parse_header(self, packet):
        name, value = packet.split(":")
        self._datagram["header"][name.strip()] = value.strip()
        return self._datagram["header"]

    def _parse_delimiter(self, packet):
        self._datagram["delimiter"] = packet.strip('"')
        return self._datagram["delimiter"]

    def _parse_values(self, packet):
        if self._datagram["output_format"] in ["3", "SB"]:
            self._values = [float(value) for value in packet.split(self._datagram["delimiter"])]
        elif self._datagram["output_format"] == "CSV":
            self._values = [float(value) for value in packet.split(self._datagram["delimiter"])][::3]
        elif self._datagram["output_format"] == "RES":
            self._values = [float(value) for value in packet.split(self._datagram["delimiter"])[2:4]]
        self._available = True

    def _send_pkt(self, pkt):
        if len(pkt) < 4 or pkt[-4:] != "\r\n":
            pkt += "\r\n"
        self._lock.acquire()
        self.ser.write(pkt.encode())
        self._lock.release()

    def interrupt(self):
        # to interrupt, first check if the driver is already in interrupt mode
        if self._state:
            # send the interruption symbol
            self._send_pkt("#")
            # block until the receiver thread has received the interruption acknowledgement
            while self._state:
                time.sleep(0.01)

    def _check_ack(self, val):
        while not val == self._command:
            time.sleep(0.01)

    def continuous(self, rate):
        self._state = True
        self._send_pkt("M{}".format(rate))

    def single(self):
        self._send_pkt("S")

    def set_485_address(self, address):
        self.interrupt()
        self._send_pkt("#001;{}".format(address))
        # self._check_ack("#001;{}".format(address))

    def get_485_address(self):
        self.interrupt()
        self._send_pkt("#002")
        self._check_ack("#002")

    def get_header(self):
        self.interrupt()
        self._send_pkt("#004")
        self._check_ack("#004")

    def set_address_mode(self, state):
        state = "ON" if state else "OFF"
        self.interrupt()
        self._send_pkt("#005;{}".format(state))
        # self._check_ack("#005;{}".format(state))

    def get_address_mode(self):
        self.interrupt()
        self._send_pkt("#006")
        self._check_ack("#006")

    def get_last_result(self):
        self.interrupt()
        self._send_pkt("#015")
        self._check_ack("#015")

    def set_delimiter(self, delim):
        self._delimiter = delim
        self.interrupt()
        self._send_pkt("#026;{}".format(delim))
        # self._check_ack("#026;{}".format(delim))

    def get_delimiter(self):
        self.interrupt()
        self._send_pkt("#027")
        self._check_ack("#027")

    def set_run_mode(self):
        self.interrupt()
        self._send_pkt("#028")
        self._state = True
        # self._check_ack("#028")

    def get_run_mode(self):
        self.interrupt()
        self._send_pkt("#029")
        self._check_ack("#029")

    def get_version(self):
        self.interrupt()
        self._send_pkt("#032")
        self._check_ack("#032")

    def get_serial(self):
        self.interrupt()
        self._send_pkt("#034")
        self._check_ack("#034")

    def set_mode(self, value):
        assert value in [1, 2, 4, 8], "M value must be one of [1, 2, 4, 8]."
        self.interrupt()
        self._send_pkt("#039;M{}".format(value))
        # self._check_ack("#039;M{}".format(value))

    def get_mode(self):
        self.interrupt()
        self._send_pkt("#040")
        self._check_ack("#040")

    def set_baud(self, baud):
        assert baud in [2400, 4800, 9600, 19200, 38400], "Baudrate must be one of [2400, 4800, 9600, 19200, 38400]."
        if not baud == self.ser.baudrate:
            self.interrupt()
            self._send_pkt("#059;{}".format(baud))
            time.sleep(1)
            self.stop()
            print("Reopening with baudrate: {}".format(baud))
            self.__init__(self.ser.port, baud, timeout=0.5)
            self.start()
        # self._check_ack("#059;{}".format(baud))

    def set_output_format(self, output_format):
        assert output_format in [3, "CSV", "SB", "RES"], 'Precision must be one of [3, "CSV", "SB", "RES"]'
        self.interrupt()
        self._send_pkt("#082;{}".format(output_format))
        # self._check_ack(str(output_format))
        self._output_format = str(output_format)
        if output_format == 3:
            self._delimiter = "\t"
        elif output_format in ["CSV", "SB", "RES"]:
            self._delimiter = ","

    def get_output_format(self):
        self.interrupt()
        self._send_pkt("#089")
        self._check_ack("#089")

    def set_startup_mode(self, state):
        state = "ON" if state else "OFF"
        self.interrupt()
        self._send_pkt("#091;{}".format(state))
        # self._check_ack("#091;{}".format(state))

    def set_485_mode(self, state):
        state = "ON" if state else "OFF"
        self.interrupt()
        self._send_pkt("#102;{}".format(state))
        # self._check_ack("#102;{}".format(state))

    def send_485_mode(self):
        self.interrupt()
        self._send_pkt("#103")
        # self._check_ack("#103")

    def get_measurements(self):
        if self._available:
            self._available = False
            return self._values
        return False
