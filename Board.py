from smbus2 import SMBus, i2c_msg
from AD5933 import AD5933
from math import sqrt, atan, pi
from time import sleep
import numpy
import pigpio


class Board:
    __gpio = pigpio.pi()

    def __init__(self, address, i2c_port=1):
        self.address = address
        self._bus = SMBus(i2c_port)
        self.select()
        self.ad5933 = AD5933(self._bus)
        self.ad5933.set_settle_cycles(100)
        self.mux = self.Mux(self._bus)
        self.eeprom = self.Eeprom(self._bus)
        Board.__gpio.set_mode(4, pigpio.OUTPUT)
        Board.__gpio.write(4, 1)

        # TODO: Get calibration from eeprom
        self.cal_magnitudes_1x = None
        self.cal_magnitudes_5x = None
        self.phase_offset = None

    @staticmethod
    def reset():
        Board.__gpio.gpio_trigger(4, 10, 0)

    def select(self):
        self._bus.i2c_rdwr(i2c_msg.write(0x70 + self.address, [0xff]))

    def deselect(self):
        self._bus.i2c_rdwr(i2c_msg.write(0x70 + self.address, [0x00]))

    class Mux:
        def __init__(self, bus):
            self._bus = bus
            self.port1 = self.Port(1)
            self.port2 = self.Port(2)
            self.port3 = self.Port(3)
            self.port4 = self.Port(4)

        class Port:
            def __init__(self, port):
                self.enabled = True
                self.channel1 = self.Channel(port, 1)
                self.channel2 = self.Channel(port, 2)
                self.channel3 = self.Channel(port, 3)
                self.channel4 = self.Channel(port, 4)
                self.channel5 = self.Channel(port, 5)
                self.channel6 = self.Channel(port, 6)
                self.channel7 = self.Channel(port, 7)
                self.channel8 = self.Channel(port, 8)

            class Channel:
                def __init__(self, port, channel):
                    self.enabled = True
                    self.impedance = self.Terminal(port, channel, False)
                    self.reference = self.Terminal(port, channel, True)

                class Terminal:
                    def __init__(self, port, channel, is_reference):
                        self.port = port
                        self.channel = channel
                        self.is_reference = is_reference

        def select(self, terminal):
            print('Selecting {0} terminal on port {1} on channel {2}'.format(
                'reference' if terminal.is_reference else 'impedance', terminal.port, terminal.channel))
            port = terminal.port - 1
            for i in range(4):
                if i != port:
                    self._bus.i2c_rdwr(i2c_msg.write(0x44 + i, [0x00]))

            data = (0b1 << (((terminal.channel - 1) // 4) * 2) + (1 if terminal.is_reference else 0)) | (
                    0b10000 << ((terminal.channel - 1) % 4))
            # print('{:08b}'.format(data))
            self._bus.i2c_rdwr(i2c_msg.write(0x44 + port, [data]))

    class Eeprom:
        def __init__(self, bus):
            self._bus = bus

    def calibrate_1x(self, port: Mux.Port):
        cal_resistors = {
            100: port.channel1.impedance,
            220: port.channel2.impedance,
            499: port.channel3.impedance
        }

        self.ad5933.set_pga_multiplier(False)
        return self._calibrate(cal_resistors)

    def calibrate_5x(self, port: Mux.Port):
        cal_resistors = {
            499: port.channel3.impedance,
            1000: port.channel4.impedance,
            3300: port.channel1.reference,
            6800: port.channel5.impedance,
            10000: port.channel5.reference
        }

        self.ad5933.set_pga_multiplier(True)
        return self._calibrate(cal_resistors)

    def _calibrate(self, cal_resistors):
        calibrated_magnitudes = {}
        calibrated_magnitudes_with_res = {}

        for cal_res, cal_port in sorted(cal_resistors.items()):
            self.mux.select(cal_port)
            real = []
            imag = []
            for i in range(0, 100):
                self.ad5933.start_output()
                self.ad5933.start_sweep()

                sleep(0.1)
                while not self.ad5933.data_ready():
                    sleep(0.1)

                real.append(self.ad5933.real_data.read_signed())
                imag.append(self.ad5933.imag_data.read_signed())
                self.ad5933.repeat_freq()

            real = sum(real) / len(real)
            imag = sum(imag) / len(imag)
            phase = atan(imag / real) * 360 / (2 * pi)
            magnitude = sqrt((real ** 2) + (imag ** 2))
            gain_factor = (5 if self.ad5933.get_pga_multiplier() else 1) / (cal_res * magnitude)

            calibrated_magnitudes[magnitude] = gain_factor
            calibrated_magnitudes_with_res[magnitude] = {cal_res, gain_factor}
            print(gain_factor)
            print(phase)

        return calibrated_magnitudes, calibrated_magnitudes_with_res

    def print_impedance_loop(self, calibrated_magnitudes, phase_offset, do_sleep=True, sleep_time=0.1):
        self.ad5933.start_output()
        self.ad5933.start_sweep()
        real = []
        imag = []

        while len(real) < 10:
            if do_sleep:
                sleep(sleep_time)
            if self.ad5933.data_ready():
                real.append(self.ad5933.real_data.read_signed())
                imag.append(self.ad5933.imag_data.read_signed())
                self.ad5933.repeat_freq()

        real = sum(real) / len(real)
        imag = sum(imag) / len(imag)

        magnitude = sqrt((real ** 2) + (imag ** 2))
        print(magnitude)
        gain_factor = numpy.interp([magnitude], list(calibrated_magnitudes.keys()),
                                   list(calibrated_magnitudes.values()))
        print(gain_factor)
        impedance = (5 if self.ad5933.get_pga_multiplier() else 1) / (gain_factor * magnitude)
        phase = atan(imag / real) * 360 / (2 * pi) - phase_offset

        if impedance > 510 and not self.ad5933.get_pga_multiplier():
            self.ad5933.set_pga_multiplier(True)
            impedance, phase = self.print_impedance_loop(calibrated_magnitudes, phase_offset, do_sleep, sleep_time)
        elif impedance < 505 and self.ad5933.get_pga_multiplier():
            self.ad5933.set_pga_multiplier(False)
            impedance, phase = self.print_impedance_loop(calibrated_magnitudes, phase_offset, do_sleep, sleep_time)
        else:
            print(('x5' if self.ad5933.get_pga_multiplier() else 'x1') + ': {0:.3f} kΩ\t{1:.2f}˚'.format(
                int(impedance) / 1000, phase))
        self.ad5933.reset()
        return impedance, phase

    def get_measurement(self, force_pga=False):
        real = []
        imag = []
        sleep_time = (32 * 1024 / self.ad5933.clock()) + (self.ad5933.get_settle_cycles() / self.ad5933.output_freq())

        timeouts = 0
        while len(real) < 10:
            sleep(sleep_time)
            if self.ad5933.data_ready():
                real.append(self.ad5933.real_data.read_signed())
                imag.append(self.ad5933.imag_data.read_signed())
                if len(real) < 10:
                    self.ad5933.repeat_freq()
            else:
                timeouts += 1
                if timeouts > 10:
                    raise TimeoutError('Failed more than 10 sleep-measure cycles with timeout')
                self.ad5933.repeat_freq()
                sleep(0.001*timeouts)

        real = sum(real) / len(real)
        imag = sum(imag) / len(imag)

        phase = atan(imag / real) * 360 / (2 * pi) - self.phase_offset
        magnitude = sqrt((real ** 2) + (imag ** 2))

        if self.ad5933.get_pga_multiplier():
            keys = sorted(self.cal_magnitudes_5x.keys())
            impedance = 5 / (magnitude * numpy.interp([magnitude], keys, [self.cal_magnitudes_5x[key] for key in keys]))
            if impedance < 500:
                self.ad5933.set_pga_multiplier(False)
                (impedance, phase) = self.get_measurement(True)
        else:
            keys = sorted(self.cal_magnitudes_1x.keys())
            impedance = 1 / (magnitude * numpy.interp([magnitude], keys, [self.cal_magnitudes_1x[key] for key in keys]))
            if not force_pga and impedance > 500:
                self.ad5933.set_pga_multiplier(True)
                (impedance, phase) = self.get_measurement()

        print(str(self.ad5933.output_freq()) + ' Hz: {0:.3f} kΩ\t{1:.2f}˚'.format(int(impedance) / 1000, phase))

        return impedance, phase

    # TODO: Check sweep doesn't go OOB
    def sweep(self, start, increment, steps):
        assert(1000 <= start <= 100000 and increment > 0 and 0 <= steps <= 511)
        int_start = start
        int_steps = steps
        if start < 5000:
            self.ad5933.set_external_oscillator(True)
            ext_steps = (4999 - start) // increment
            self.ad5933.set_start_increment_steps(start, increment, ext_steps)
            self.ad5933.start_output()
            self.ad5933.start_sweep()
            self.get_measurement()
            while not self.ad5933.sweep_complete():
                self.ad5933.increment_freq()
                self.get_measurement()
            self.ad5933.reset()
            int_start += (ext_steps + 1) * increment
            int_steps -= ext_steps + 1

        if (start + (increment * steps)) >= 5000:
            self.ad5933.set_external_oscillator(False)
            self.ad5933.set_start_increment_steps(int_start, increment, int_steps)
            self.ad5933.start_output()
            self.ad5933.start_sweep()
            self.get_measurement()
            while not self.ad5933.sweep_complete():
                self.ad5933.increment_freq()
                self.get_measurement()
            self.ad5933.reset()