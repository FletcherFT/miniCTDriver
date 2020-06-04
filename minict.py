import serial
import threading
import time
import struct
import re


class Driver:
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
                                 xonxoff=False,
                                 rtscts=False,
                                 write_timeout=None,
                                 dsrdtr=False,
                                 inter_byte_timeout=None,
                                 exclusive=None)
        self._listener = threading.Thread(target=self._receive_pkt, name="Thread-SerialListener")
        self._run = False
        self._state = False
        self._delimiter = "\t"
        self._available = False
        self._values = []

    def start(self):
        self._run = True
        if self.ser.closed:
            self.ser.open()
        self._listener.start()

    def stop(self):
        if self._run:
            self._run = False
            self._listener.join()

    def _receive_pkt(self):
        # listen for start characters
        regex = re.compile(r"^\d")
        while self._run:
            # if something detected on the serial port
            if self.ser.in_waiting:
                buff = self.ser.readline()
                if re.match(regex, buff.decode()):
                    self._values = [float(value) for value in buff.decode().rstrip().split(self._delimiter)]
                    self._available = True
                else:
                    print(buff.decode().rstrip())
        self.ser.close()

    def _send_pkt(self, pkt):
        if len(pkt) < 4 or pkt[-4:] != "\r\n":
            pkt += "\r\n"
        self.ser.write(pkt.encode())

    def interrupt(self):
        if self._state:
            self._send_pkt("#")
            time.sleep(0.5)
        self._state = False

    def continuous(self, rate):
        self._state = True
        self._send_pkt("M{}".format(rate))

    def single(self):
        self._send_pkt("S")

    def set_485_address(self, address):
        self.interrupt()
        self._send_pkt("#001;{}".format(address))

    def get_485_address(self):
        self.interrupt()
        self._send_pkt("#002")

    def get_header(self):
        self.interrupt()
        self._send_pkt("#004")

    def set_address_mode(self, state):
        state = "ON" if state else "OFF"
        self.interrupt()
        self._send_pkt("#005;{}".format(state))

    def get_address_mode(self):
        self.interrupt()
        self._send_pkt("#006")

    def get_last_result(self):
        self.interrupt()
        self._send_pkt("#015")

    def set_delimiter(self, delim):
        self._delimiter = delim
        self.interrupt()
        self._send_pkt("#026;{}".format(delim))

    def get_delimiter(self):
        self.interrupt()
        self._send_pkt("#027")

    def set_run_mode(self):
        self.interrupt()
        self._send_pkt("#028")

    def get_run_mode(self):
        self.interrupt()
        self._send_pkt("#029")

    def get_version(self):
        self.interrupt()
        self._send_pkt("#032")

    def get_serial(self):
        self.interrupt()
        self._send_pkt("#034")

    def set_mode(self, mode, value):
        if mode == "M":
            assert value in [1, 2, 4, 8], "M value must be one of [1, 2, 4, 8]."
        if mode == "B":
            assert value in [1, 2, 3, 4, 5], "B value must be one of [1, 2, 3, 4, 5]."
        self.interrupt()
        self._send_pkt("#039;{}{}".format(mode, value))

    def get_mode(self):
        self.interrupt()
        self._send_pkt("#040")

    def set_baud(self, baud):
        assert baud in [2400, 4800, 9600, 19200, 38400], "Baudrate must be one of [2400, 4800, 9600, 19200, 38400]."
        self.interrupt()
        self._send_pkt("#059;{}".format(baud))

    def set_precision(self, precision):
        assert precision in ["ON", "OFF", 3, 2, "CSV"], 'Precision must be one of ["ON", "OFF", 3, 2, "CSV"]'
        self.interrupt()
        self._send_pkt("#082;{}".format(precision))

    def set_startup_mode(self, state):
        state = "ON" if state else "OFF"
        self.interrupt()
        self._send_pkt("#091;{}".format(state))

    def set_485_mode(self, state):
        state = "ON" if state else "OFF"
        self.interrupt()
        self._send_pkt("#102;{}".format(state))

    def send_485_mode(self):
        self.interrupt()
        self._send_pkt("#103")

    def get_measurements(self):
        if self._available:
            self._available = False
            return self._values
        return False


if __name__ == "__main__":
    A = Driver("COM2", 19200, timeout=0.5)
    A.start()
    A.continuous(4)
    time.sleep(3)
    for i in range(25):
        print(A.get_measurements())
        time.sleep(0.25)
