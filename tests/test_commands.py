from minict.minict import MiniCTDriver
import time

if __name__ == "__main__":
    # Initialise the driver
    A = MiniCTDriver("COM4", 38400, timeout=0.5)
    # Start serial communication
    A.start()
    A.interrupt()
    A.continuous(8)
    time.sleep(1)
    # Get the configuration settings
    A.get_header()
    # Do a configuration Test
    # Set the output format
    A.set_output_format("CSV")
    A.set_startup_mode(True)
    A.set_mode(8)
    A.set_delimiter("BBBB")
    A.set_485_address(2)
    A.set_485_mode(False)
    A.set_run_mode()
    for _ in range(10):
        A.get_measurements()
        time.sleep(0.2)
    A.interrupt()
    A.set_baud(38400)
    A.config()
    A.set_run_mode()
    for _ in range(10):
        A.get_measurements()
    A.stop()
