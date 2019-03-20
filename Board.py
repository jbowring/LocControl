from smbus2 import SMBus, i2c_msg
from AD5933 import AD5933
from math import sqrt, atan, pi, isnan
from time import sleep
import numpy
import pigpio
from scipy.interpolate import griddata
import struct
from datetime import datetime


class QuitNow(InterruptedError):
    """raise this when board operation has been ordered to stop"""

class PortDisconnectedError(ConnectionError):
    """raise when access to a disconnected port is requested"""

class Board:
    __gpio = pigpio.pi()

    class CalibrationConstants:
        fs = numpy.asarray([])
        ms = numpy.asarray([])
        gfs = numpy.asarray([])
        po_fs = numpy.asarray([])
        pos = numpy.asarray([])

    def __init__(self, address, i2c_port=1):
        Board.__gpio.set_mode(4, pigpio.OUTPUT)
        Board.__gpio.write(4, 1)
        Board.reset()

        self.__address = address
        self.__bus = SMBus(i2c_port)
        self.select()
        self.ad5933 = AD5933(self.__bus)
        self.ad5933.set_settle_cycles(100)  # TODO: Decide final value
        self.mux = self.Mux(self.__bus, address)
        self.eeprom = self.Eeprom(self.__bus)

        self.interp_1x = self.CalibrationConstants()
        self.interp_5x = self.CalibrationConstants()

        self.interp2d_1x = None
        self.interp2d_5x = None

        self.quit_now = False

    def address(self):
        return self.__address

    def load_calibration_constants(self):
        calibration_constants = self.eeprom.read_calibration_constants()
        cal_1x, cal_5x = calibration_constants[1], calibration_constants[5]
        for is_1x in (True, False):
            phase_offset_frequencies = []
            phase_offsets = []
            frequencies = []
            magnitudes = []
            gain_factors = []
            for frequency, pair in sorted((cal_1x if is_1x else cal_5x).items()):
                for key, value in sorted(pair.items()):
                    if key == 0:
                        phase_offset_frequencies.append(frequency)
                        phase_offsets.append(value)
                    else:
                        frequencies.append(frequency)
                        magnitudes.append(key)
                        gain_factors.append(value)

            if is_1x:
                self.interp_1x.fs = numpy.asarray(frequencies)
                self.interp_1x.ms = numpy.asarray(magnitudes)
                self.interp_1x.gfs = numpy.asarray(gain_factors)
                self.interp_1x.po_fs = numpy.asarray(phase_offset_frequencies)
                self.interp_1x.pos = numpy.asarray(phase_offsets)
            else:
                self.interp_5x.fs = numpy.asarray(frequencies)
                self.interp_5x.ms = numpy.asarray(magnitudes)
                self.interp_5x.gfs = numpy.asarray(gain_factors)
                self.interp_5x.po_fs = numpy.asarray(phase_offset_frequencies)
                self.interp_5x.pos = numpy.asarray(phase_offsets)

    @staticmethod
    def reset():
        Board.__gpio.gpio_trigger(4, 10, 0)

    def select(self):
        Board.reset()
        self.__bus.i2c_rdwr(i2c_msg.write(0x70 + self.__address, [0xf0]))

    def deselect(self):
        self.__bus.i2c_rdwr(i2c_msg.write(0x70 + self.__address, [0x00]))

    class Mux:
        class Port:
            class Channel:
                class Terminal:
                    def __init__(self, port, channel, is_reference):
                        self.port = port
                        self.channel = channel
                        self.is_reference = is_reference

                def __init__(self, port, channel):
                    self.enabled = True
                    self.impedance = self.Terminal(port, channel, False)
                    self.reference = self.Terminal(port, channel, True)
                    self.__current = 0

                def __iter__(self):
                    return iter([self.impedance, self.reference])

                # def __next__(self):
                #     if self.__current == 2:
                #         raise StopIteration
                #     self.__current += 1
                #     return self.impedance if self.__current == 1 else self.reference

            def __init__(self, port):
                self.enabled = True
                self.__port = port
                self.channel1 = self.Channel(port, 1)
                self.channel2 = self.Channel(port, 2)
                self.channel3 = self.Channel(port, 3)
                self.channel4 = self.Channel(port, 4)
                self.channel5 = self.Channel(port, 5)
                self.channel6 = self.Channel(port, 6)
                self.channel7 = self.Channel(port, 7)
                self.channel8 = self.Channel(port, 8)
                self.__current = 0

            def __iter__(self):
                return iter([
                    self.channel1,
                    self.channel2,
                    self.channel3,
                    self.channel4,
                    self.channel5,
                    self.channel6,
                    self.channel7,
                    self.channel8
                ])

            # def __next__(self):
            #     if self.__current == 8:
            #         raise StopIteration
            #     else:
            #         self.__current += 1
            #         return self.Channel(self.__port, self.__current)

        port1 = Port(1)
        port2 = Port(2)
        port3 = Port(3)
        port4 = Port(4)

        def __iter__(self):
            return iter([self.port1, self.port2, self.port3, self.port4])

        # def __next__(self):
        #     if self.__current == 4:
        #         raise StopIteration
        #     self.__current += 1
        #     return self.Port(self.__current)

        def __init__(self, bus, board_address):
            self.__bus = bus
            self.__board_address = board_address
            self.__current = 0
            self.__selected = None

        def _select_legacy(self, terminal):
            print('Selecting {0} terminal on port {1} on channel {2}'.format(
                'reference' if terminal.is_reference else 'impedance', terminal.port, terminal.channel))
            port = terminal.port - 1
            for i in range(4):
                if i != port:
                    self.__bus.i2c_rdwr(i2c_msg.write(0x44 + i, [0x00]))

            data = (0b1 << (((terminal.channel - 1) // 4) * 2) + (1 if terminal.is_reference else 0)) | (
                    0b10000 << ((terminal.channel - 1) % 4))
            # print('{:08b}'.format(data))
            self.__bus.i2c_rdwr(i2c_msg.write(0x44 + port, [data]))

        def select(self, terminal):
            self.__selected = None

            print('Selecting {0} terminal on port {1} on channel {2}'.format(
                'reference' if terminal.is_reference else 'impedance', terminal.port, terminal.channel))

            # select i2c channel 4 to talk to master mux
            self.__bus.i2c_rdwr(i2c_msg.write(0x70 + self.__board_address, [0xf1]))

            # select port on master mux
            self.__bus.i2c_rdwr(i2c_msg.write(0x44, [0b10001000 >> (terminal.port - 1)]))

            # calculate pair index of each half-mux (0-3)
            pair = (((terminal.channel - 1) * 2) + (1 if terminal.is_reference else 0)) % 4

            if terminal.channel in [1, 2, 5, 6]:
                data = 0b00001000 >> pair
            else:
                data = 0b00010000 << pair

            # select i2c channel to talk to slave muxes
            self.__bus.i2c_rdwr(i2c_msg.write(0x70 + self.__board_address, [(0b10000 >> terminal.port) | 0xf0]))

            try:
                # select channels on slave muxes
                self.__bus.i2c_rdwr(i2c_msg.write(0x46, [data if 1 <= terminal.channel <= 4 else 0b00000000]))
                self.__bus.i2c_rdwr(i2c_msg.write(0x47, [data if 5 <= terminal.channel <= 8 else 0b00000000]))
            except OSError:
                raise PortDisconnectedError(121, 'Board {0}, port {1} breakout board is not connected'.format(self.__board_address, terminal.port))

            self.__selected = terminal

        def selected(self):
            return self.__selected

    class Eeprom:
        def __init__(self, bus):
            self.__bus = bus

        def write_calibration_constants(self, gain_ranges: dict):
            self.__write(0x0000, self._encode(gain_ranges))
            assert self.read_calibration_constants() == gain_ranges, 'Calibration constants read check failed!'

        def read_calibration_constants(self):
            return self._decode(self.__read(0x0000, 65535))

        @staticmethod
        def _encode(gain_ranges: dict):
            first = lambda d : d[list(d.keys())[0]]

            for gain_range in gain_ranges.values():
                # assert all frequencies in all ranges are equal
                assert gain_range.keys() == first(gain_ranges).keys()
                # assert phase offset (i.e. key 0.0) exists in all dictionaries in all ranges
                assert all(0.0 in freq_dict for freq_dict in gain_range.values())
                # assert all dictionaries within a gain range are of equal size
                assert len(set(len(freq_dict) for freq_dict in gain_range.values())) == 1

            # assert all gain range keywords are 4-byte integers
            assert all(1 <= int(keyword) <= 2**32 for keyword in gain_ranges.keys())
            # assert all gain range keywords are unique
            assert len(set(int(keyword) for keyword in gain_ranges.keys())) == len(gain_ranges.keys())

            start_freq = sorted(first(gain_ranges).keys())[0]
            increment_freq = sorted(first(gain_ranges).keys())[1] - start_freq
            count = len(first(gain_ranges))

            output = bytearray(struct.pack('iii', int(start_freq), int(increment_freq), int(count)))

            # pack pairs of range number and calibration resistor count
            for keyword, data in sorted(gain_ranges.items()):
                output.extend(struct.pack('ii', int(keyword), int(len(first(data)) - 1)))

            # four-byte break
            output.extend(struct.pack('i', 0))

            # put phase offset (mag 0.0) constant first, then pairs of magnitude and gain factor
            for _, data in sorted(gain_ranges.items()):
                for _, pairs in sorted(data.items()):
                    output.extend(struct.pack('d', pairs[0.0]))
                    for mag, gf in pairs.items():
                        if mag != 0.0:
                            output.extend(struct.pack('dd', mag, gf))

            # check output not too big for EEPROM
            print(len(output))
            assert len(output) <= 2**16
            return output

        @staticmethod
        def _decode(data: bytearray):
            start_freq, increment_freq, count = struct.unpack_from('iii', data)
            frequencies = range(start_freq, start_freq + (increment_freq * count), increment_freq)

            sizes = {}
            for i in range(12, len(data), 8):
                # four-byte break
                if struct.unpack_from('i', data, i)[0] == 0:
                    # skip over it
                    i += 4
                    break
                sizes.update((struct.unpack_from('ii', data, i), ))

            output = {}
            for name, size in sorted(sizes.items()):
                output[name] = {}
                for frequency in frequencies:
                    # noinspection PyUnboundLocalVariable
                    output[name][frequency] = {0.0: struct.unpack_from('d', data, i)[0]}
                    for i in range(i + 8, i + (size * 2 * 8), 16):
                        output[name][frequency].update((struct.unpack_from('dd', data, i), ))
                    i += 16

            return output

        def __write(self, start_address, data: bytes):
            assert 0x0000 <= start_address <= 0xffff and start_address + len(data) - 1 <= 0xffff
            address = start_address
            while address - start_address < len(data):
                self.__block_write(address, data[address-start_address:(address-start_address) + (128-(address % 128))])
                address += (128 - (address % 128))

        def __read(self, address, n_bytes):
            self.__block_write(address, bytes())
            i = 0
            output = bytearray()
            while i < n_bytes:
                increment = min(n_bytes-i, 4096)
                read = i2c_msg.read(0x50, increment)
                i += increment
                self.__bus.i2c_rdwr(read)
                output.extend(list(read))
            return output

        def __block_write(self, address, data: bytes):
            assert 0x0000 <= address <= 0xffff and len(data) <= 128 - (address % 128)
            self.__bus.i2c_rdwr(i2c_msg.write(0x50, [address >> 8, address & 0xff, *data]))
            if len(data) > 0:
                sleep(0.005)

        # def block_read(self, address, n_bytes):
        #     # self.block_write(address, bytes())
        #     read = i2c_msg.read(0x50, n_bytes)
        #     self.__bus.i2c_rdwr(i2c_msg.write(0x50, [address >> 8, address & 0xff]), read)
        #     return list(read)

    def _calibrate_1x_sweep_legacy(self, port: Mux.Port):
        cal_resistors = {
            100: port.channel1.impedance,
            220: port.channel2.impedance,
            499: port.channel3.impedance
        }

        self.ad5933.set_pga_multiplier(False)
        return self._calibrate_sweep_legacy(cal_resistors)

    def _calibrate_5x_sweep_legacy(self, port: Mux.Port):
        cal_resistors = {
            499: port.channel3.impedance,
            1000: port.channel4.impedance,
            3300: port.channel1.reference,
            6800: port.channel5.impedance,
            10000: port.channel5.reference
        }

        self.ad5933.set_pga_multiplier(True)
        return self._calibrate_sweep_legacy(cal_resistors)

    def _calibrate_sweep_legacy(self, cal_resistors):
        calibrated = {}

        for cal_res, cal_port in sorted(cal_resistors.items()):
            # noinspection PyProtectedMember
            self.mux._select_legacy(cal_port)

            sweep = self.sweep_raw(start=1000, increment=396, steps=250, repeats=10)  # REVERT: 500 steps, 100 repeats

            if len(calibrated) == 0:
                for freq in sweep.keys():
                    calibrated[freq] = {}

            for (freq, (magnitude, phase)) in sweep.items():
                calibrated[freq][magnitude] = 1 / (cal_res * magnitude)

            if cal_res == sorted(cal_resistors.keys())[len(cal_resistors) // 2]:
                for (freq, (magnitude, phase)) in sweep.items():
                    calibrated[freq][0.0] = phase

        return calibrated

    def calibrate_1x_sweep(self, port: Mux.Port):
        cal_resistors = {
            100: port.channel1.impedance,
            220: port.channel1.reference,
            499: port.channel2.impedance
        }

        self.ad5933.set_pga_multiplier(False)
        return self._calibrate_sweep(cal_resistors)

    def calibrate_5x_sweep(self, port: Mux.Port):
        cal_resistors = {
            499: port.channel2.impedance,
            1000: port.channel2.reference,
            3300: port.channel3.impedance,
            6800: port.channel3.reference,
            10000: port.channel4.impedance
        }

        self.ad5933.set_pga_multiplier(True)
        return self._calibrate_sweep(cal_resistors)

    def _calibrate_sweep(self, cal_resistors):
        calibrated = {}

        for cal_res, cal_port in sorted(cal_resistors.items()):
            self.mux.select(cal_port)

            sweep = self.sweep_raw(start=1000, increment=220, steps=450, repeats=100)  # REVERT: 450 steps, 100 repeats

            if len(calibrated) == 0:
                for freq in sweep.keys():
                    calibrated[freq] = {}

            for (freq, (magnitude, phase)) in sweep.items():
                calibrated[freq][magnitude] = 1 / (cal_res * magnitude)

            if cal_res == sorted(cal_resistors.keys())[len(cal_resistors) // 2]:
                for (freq, (magnitude, phase)) in sweep.items():
                    calibrated[freq][0.0] = phase

        return calibrated

    def calibrate(self, port):
        self.eeprom.write_calibration_constants({1: self.calibrate_1x_sweep(port), 5: self.calibrate_5x_sweep(port)})

    # def print_impedance_loop(self, calibrated_magnitudes, phase_offset, do_sleep=True, sleep_time=0.1):
    #     self.ad5933.start_output()
    #     self.ad5933.start_sweep()
    #     real = []
    #     imag = []
    #
    #     while len(real) < 10:
    #         if do_sleep:
    #             sleep(sleep_time)
    #         if self.ad5933.data_ready():
    #             real.append(self.ad5933.real_data.read_signed())
    #             imag.append(self.ad5933.imag_data.read_signed())
    #             self.ad5933.repeat_freq()
    #
    #     real = sum(real) / len(real)
    #     imag = sum(imag) / len(imag)
    #
    #     magnitude = sqrt((real ** 2) + (imag ** 2))
    #     print(magnitude)
    #     gain_factor = numpy.interp([magnitude], list(calibrated_magnitudes.keys()),
    #                                list(calibrated_magnitudes.values()))
    #     print(gain_factor)
    #     impedance = (5 if self.ad5933.get_pga_multiplier() else 1) / (gain_factor * magnitude)
    #     phase = atan(imag / real) * 360 / (2 * pi) - phase_offset
    #
    #     if impedance > 510 and not self.ad5933.get_pga_multiplier():
    #         self.ad5933.set_pga_multiplier(True)
    #         impedance, phase = self.print_impedance_loop(calibrated_magnitudes, phase_offset, do_sleep, sleep_time)
    #     elif impedance < 505 and self.ad5933.get_pga_multiplier():
    #         self.ad5933.set_pga_multiplier(False)
    #         impedance, phase = self.print_impedance_loop(calibrated_magnitudes, phase_offset, do_sleep, sleep_time)
    #     else:
    #         print(('x5' if self.ad5933.get_pga_multiplier() else 'x1') + ': {0:.3f} kΩ\t{1:.2f}˚'.format(
    #             int(impedance) / 1000, phase))
    #     self.ad5933.reset()
    #     return impedance, phase

    # def get_measurement(self, force_pga=False, return_raw=False, repeats=10):
    #     real = []
    #     imag = []
    #
    #     sleep_time = (32 * 1024 / self.ad5933.clock()) + (self.ad5933.get_settle_cycles() / self.ad5933.output_freq())
    #
    #     timeouts = 0
    #     while len(real) < repeats:
    #         sleep(sleep_time)
    #         if self.ad5933.data_ready():
    #             real.append(self.ad5933.real_data.read_signed())
    #             imag.append(self.ad5933.imag_data.read_signed())
    #
    #             # REVERT: Remove
    #             # print('{0}:\t{1}\t{2}'.format(self.ad5933.output_freq(), self.ad5933.real_data.read_signed(), self.ad5933.imag_data.read_signed()))
    #
    #             if len(real) < repeats:
    #                 self.ad5933.repeat_freq()
    #         else:
    #             timeouts += 1
    #             if timeouts > repeats:
    #                 raise TimeoutError('Failed more than {0} sleep-measure cycles with timeout'.format(repeats))
    #             self.ad5933.repeat_freq()
    #             sleep(0.001*timeouts)
    #
    #     if timeouts != 0:
    #         print('{0} timeouts'.format(timeouts))
    #
    #     # REVERT: Remove
    #     # magnitude = []
    #     # for i in range(len(real)):
    #     #     magnitude.append(sqrt((real[i] ** 2) + (imag[i] ** 2)))
    #     # magnitude = gmean(magnitude)
    #
    #     real = sum(real) / len(real)
    #     imag = sum(imag) / len(imag)
    #
    #     # REVERT: Remove
    #     # print('Average\t{0}\t{1}'.format(real, imag))
    #     # print()
    #
    #     try:
    #         phase = atan(imag / real)
    #     except ZeroDivisionError:
    #         phase = atan(imag * float('Inf'))
    #
    #     phase *= 360 / (2 * pi)
    #     magnitude = sqrt((real ** 2) + (imag ** 2))
    #
    #     if return_raw:
    #         return magnitude, phase
    #
    #     phase -= self.phase_offset  # TODO: Proper phase offsets
    #
    #     if self.ad5933.get_pga_multiplier():
    #         keys = sorted(self.cal_magnitudes_5x.keys())
    #         impedance = 5 / (magnitude * numpy.interp([magnitude], keys, [self.cal_magnitudes_5x[key] for key in keys]))
    #         if impedance < 500:
    #             self.ad5933.set_pga_multiplier(False)
    #             (impedance, phase) = self.get_measurement(True)
    #     else:
    #         keys = sorted(self.cal_magnitudes_1x.keys())
    #         impedance = 1 / (magnitude * numpy.interp([magnitude], keys, [self.cal_magnitudes_1x[key] for key in keys]))
    #         if not force_pga and impedance > 500:
    #             self.ad5933.set_pga_multiplier(True)
    #             (impedance, phase) = self.get_measurement()
    #
    #     print(str(self.ad5933.output_freq()) + ' Hz: {0:.3f} kΩ\t{1:.2f}˚'.format(int(impedance) / 1000, phase))
    #
    #     return impedance, phase

    # def get_measurement(self, force_pga=False, return_raw=False, repeats=10):
    #     real = []
    #     imag = []
    # 
    #     sleep_time = (32 * 1024 / self.ad5933.clock()) + (self.ad5933.get_settle_cycles() / self.ad5933.output_freq())
    # 
    #     timeouts = 0
    #     while len(real) < repeats:
    #         sleep(sleep_time)
    #         if self.ad5933.data_ready():
    #             real.append(self.ad5933.real_data.read_signed())
    #             imag.append(self.ad5933.imag_data.read_signed())
    # 
    #             if len(real) < repeats:
    #                 self.ad5933.repeat_freq()
    #         else:
    #             timeouts += 1
    #             if timeouts > repeats:
    #                 raise TimeoutError('Failed more than {0} sleep-measure cycles with timeout'.format(repeats))
    #             self.ad5933.repeat_freq()
    #             sleep(0.001*timeouts)
    # 
    #     if timeouts != 0:
    #         print('{0} timeouts'.format(timeouts))
    # 
    #     real = sum(real) / len(real)
    #     imag = sum(imag) / len(imag)
    # 
    #     try:
    #         phase = atan(imag / real)
    #     except ZeroDivisionError:
    #         phase = atan(imag * float('Inf'))
    # 
    #     phase *= 360 / (2 * pi)
    #     magnitude = sqrt((real ** 2) + (imag ** 2))
    # 
    #     if return_raw:
    #         return magnitude, phase
    # 
    #     phase -= self.phase_offset  # TODO: Proper phase offsets
    # 
    #     if self.ad5933.get_pga_multiplier():
    #         gf = float(griddata((self.interp_5x['freqs'], self.interp_5x['mags']), self.interp_5x['gfs'],
    #                       (self.ad5933.output_freq(), magnitude)))
    #         if isnan(gf):
    #             gf = float(griddata((self.interp_5x['freqs'], self.interp_5x['mags']), self.interp_5x['gfs'],
    #                                 (self.ad5933.output_freq(), magnitude), method='nearest'))
    #         # gf = self.interp2d_5x(self.ad5933.output_freq(), magnitude)
    #         impedance = 5 / (magnitude * gf)
    #         if impedance < 500:
    #             self.ad5933.set_pga_multiplier(False)
    #             (impedance, phase) = self.get_measurement(True)
    #     else:
    #         gf = griddata((self.interp_1x['freqs'], self.interp_1x['mags']), self.interp_1x['gfs'],
    #                       (self.ad5933.output_freq(), magnitude))
    #         if isnan(gf):
    #             gf = float(griddata((self.interp_1x['freqs'], self.interp_1x['mags']), self.interp_1x['gfs'],
    #                                 (self.ad5933.output_freq(), magnitude), method='nearest'))
    #         # gf = self.interp2d_1x(self.ad5933.output_freq(), magnitude)
    #         impedance = 1 / (magnitude * gf)
    #         if not force_pga and impedance > 500:
    #             self.ad5933.set_pga_multiplier(True)
    #             (impedance, phase) = self.get_measurement()
    # 
    # 
    #     self.raw[self.ad5933.output_freq()] = {magnitude: gf}
    #     # print(str(self.ad5933.output_freq()) + ' Hz: {0:.3f} kΩ\t{1:.2f}˚\tmag {2}\tgf {3}'.format(impedance / 1000, phase, magnitude, gf))
    # 
    #     return impedance, phase

    def get_measurement(self, repeats=10):
        real = []
        imag = []

        # sleep(3)  # REVERT: Remove

        # REVERT:    (32 * 1024 / ...
        sleep_time = (16 * 1024 / self.ad5933.clock()) + (self.ad5933.get_settle_cycles() / self.ad5933.output_freq())

        timeouts = 0
        while len(real) < repeats:
            if self.quit_now:
                raise QuitNow('Board {0} quitting'.format(self.__address))
            sleep(sleep_time)
            if self.ad5933.data_ready():
                real.append(self.ad5933.real_data.read_signed())
                imag.append(self.ad5933.imag_data.read_signed())

                if len(real) < repeats:
                    self.ad5933.repeat_freq()
            else:
                timeouts += 1
                if timeouts > repeats:
                    raise TimeoutError('Failed more than {0} sleep-measure cycles with timeout'.format(repeats))
                self.ad5933.repeat_freq()
                sleep(0.001*timeouts)

        if timeouts != 0:
            print('{0} timeouts'.format(timeouts))

        real = sum(real) / len(real)
        imag = sum(imag) / len(imag)

        # REVERT: remove
        self.real.append(real)
        self.imag.append(imag)

        try:
            phase = atan(imag / real)
        except ZeroDivisionError:
            phase = atan(imag * float('Inf'))

        if real < 0:
            phase += pi
        elif imag < 0:
            phase += 2*pi

        # if real < 0:
            # if imag > 0:
            #     phase += pi
            # if imag < 0:
            #     phase -= pi

        phase *= 360 / (2 * pi)
        magnitude = sqrt((real ** 2) + (imag ** 2))

        return magnitude, phase
    
    # def get_measurement_dual_range(self, repeats=10):
    #     self.ad5933.set_pga_multiplier(False)
    #     result_1x = self.get_measurement(repeats)
    #     self.ad5933.set_pga_multiplier(True)
    #     self.ad5933.repeat_freq()
    #     result_5x = self.get_measurement(repeats)
    #     return result_1x, result_5x

    # def sweep(self, start, increment, steps, return_raw=False, repeats=10):
    #     assert(1000 <= start <= 100000 and increment >= 0 and 0 <= steps <= 511)
    #     cutoff = 12000
    #     int_start = start
    #     int_steps = steps
    #     results = {}
    #     if start < cutoff:
    #         self.ad5933.set_external_oscillator(True)
    #         ext_steps = min(steps, ((cutoff-1) - start) // increment)
    #         self.ad5933.set_start_increment_steps(start, increment, ext_steps)
    #         self.ad5933.start_output()
    #         self.ad5933.start_sweep()
    #         results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         while not self.ad5933.sweep_complete():
    #             self.ad5933.increment_freq()
    #             results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         self.ad5933.reset()
    #         int_start += (ext_steps + 1) * increment
    #         int_steps -= ext_steps + 1
    #
    #     if (start + (increment * steps)) >= cutoff:
    #         self.ad5933.set_external_oscillator(False)
    #         self.ad5933.set_start_increment_steps(int_start, increment, int_steps)
    #         self.ad5933.start_output()
    #         self.ad5933.start_sweep()
    #         results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         while not self.ad5933.sweep_complete():
    #             self.ad5933.increment_freq()
    #             results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         self.ad5933.reset()
    #
    #     return results

    # def sweep(self, start, increment, steps, return_raw=False, repeats=10):
    #     assert(1000 <= start <= 100000 and increment >= 0 and 0 <= steps <= 511)
    #     ext_limit = 11999
    #     int_start = start
    #     int_steps = steps
    #     results = {}
    #     if start <= ext_limit:
    #         self.ad5933.set_external_oscillator(True)
    #         ext_steps = min(steps, (ext_limit - start) // increment)
    #         self.ad5933.set_start_increment_steps(start, increment, ext_steps)
    #         self.ad5933.start_output()
    #         self.ad5933.start_sweep()
    #         results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         while not self.ad5933.sweep_complete():
    #             self.ad5933.increment_freq()
    #             results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         self.ad5933.reset()
    #         int_start += (ext_steps + 1) * increment
    #         int_steps -= ext_steps + 1
    # 
    #     if (start + (increment * steps)) > ext_limit:
    #         self.ad5933.set_external_oscillator(False)
    #         self.ad5933.set_start_increment_steps(int_start, increment, int_steps)
    #         self.ad5933.start_output()
    #         self.ad5933.start_sweep()
    #         results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         while not self.ad5933.sweep_complete():
    #             self.ad5933.increment_freq()
    #             results[self.ad5933.output_freq()] = self.get_measurement(return_raw=return_raw, repeats=repeats)
    #         self.ad5933.reset()
    # 
    #     return results

    def sweep(self, start, increment, steps, repeats=10):
        then = datetime.now()
        assert(1000 <= start <= 100000 and increment >= 0 and 0 <= steps <= 511)

        self.ad5933.set_pga_multiplier(False)
        results_1x = self.sweep_raw(start, increment, steps, repeats)
        self.ad5933.set_pga_multiplier(True)
        results_5x = self.sweep_raw(start, increment, steps, repeats)

        results = {}
        for (frequency, pair_1x), (_, pair_5x) in zip(sorted(results_1x.items()), sorted(results_5x.items())):
            results[frequency] = (pair_1x, pair_5x)

        print('Sweep duration: ',  datetime.now() - then)
        return self.adjust(results)

    def sweep_raw(self, start, increment, steps, repeats):
        assert(1000 <= start <= 100000 and increment >= 0 and 0 <= steps <= 511)
        # REVERT: remove
        self.real = []
        self.imag = []

        ext_limit = 11999
        int_start = start
        int_steps = steps
        results = {}
        if start <= ext_limit:
            self.ad5933.set_external_oscillator(True)
            ext_steps = min(steps, (ext_limit - start) // increment)
            self.ad5933.set_start_increment_steps(start, increment, ext_steps)
            # print('External: {0} + {1} * {2}'.format(start, increment, ext_steps))  # REVERT: remove
            self.ad5933.start_output()
            self.ad5933.start_sweep()
            results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            while not self.ad5933.sweep_complete() and ext_steps != 0:
                self.ad5933.increment_freq()
                results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            self.ad5933.reset()
            int_start += (ext_steps + 1) * increment
            int_steps -= ext_steps + 1

        if (start + (increment * steps)) > ext_limit:
            self.ad5933.set_external_oscillator(False)
            self.ad5933.set_start_increment_steps(int_start, increment, int_steps)
            # print('Internal: {0} + {1} * {2}'.format(int_start, increment, int_steps))  # REVERT: remove
            self.ad5933.start_output()
            self.ad5933.start_sweep()
            results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            while not self.ad5933.sweep_complete() and self.ad5933.output_freq() <= (100000 - increment) and int_steps != 0:
                self.ad5933.increment_freq()
                results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            self.ad5933.reset()

        return results
    
    def adjust(self, results):
        self.magnitudes = []
        frequencies = []
        magnitudes_1x = []
        phases_1x = []
        magnitudes_5x = []
        phases_5x = []
        for frequency, ((magnitude_1x, phase_1x), (magnitude_5x, phase_5x)) in sorted(results.items()):
            frequencies.append(frequency)
            magnitudes_1x.append(magnitude_1x)
            phases_1x.append(phase_1x)
            magnitudes_5x.append(magnitude_5x)
            phases_5x.append(phase_5x)

        gfs_1x = griddata((self.interp_1x.fs, self.interp_1x.ms), self.interp_1x.gfs, (frequencies, magnitudes_1x))  # REVERT: remove nearest
        gfs_nearest = griddata((self.interp_1x.fs, self.interp_1x.ms), self.interp_1x.gfs, (frequencies, magnitudes_1x),
                               method='nearest')
        for i in range(len(gfs_1x)):
            if isnan(gfs_1x[i]):
                gfs_1x[i] = gfs_nearest[i]
        phase_offsets_1x = griddata(self.interp_1x.po_fs, self.interp_1x.pos, frequencies)
                
        gfs_5x = griddata((self.interp_5x.fs, self.interp_5x.ms), self.interp_5x.gfs, (frequencies, magnitudes_5x))  # REVERT: remove nearest
        gfs_nearest = griddata((self.interp_5x.fs, self.interp_5x.ms), self.interp_5x.gfs, (frequencies, magnitudes_5x),
                               method='nearest')
        for i in range(len(gfs_5x)):
            if isnan(gfs_5x[i]):
                gfs_5x[i] = gfs_nearest[i]
        phase_offsets_5x = griddata(self.interp_5x.po_fs, self.interp_5x.pos, frequencies,
                               method='nearest')  # REVERT: remove nearest
                
        results = {}
        for f, m_1x, gf_1x, p_1x, po_1x, m_5x, gf_5x, p_5x, po_5x in zip(frequencies, magnitudes_1x, gfs_1x, phases_1x,
                                                                         phase_offsets_1x, magnitudes_5x, gfs_5x,
                                                                         phases_5x, phase_offsets_5x):
            m = m_1x
            gf = gf_1x
            debug_phase = p_1x
            debug_phase_offset = po_1x
            impedance = 1 / (m_1x * gf_1x)
            phase = p_1x - po_1x
            if impedance > 500:
                m = m_5x
                gf = gf_5x
                impedance = 1 / (m_5x * gf_5x)
                phase = p_5x - po_5x
                debug_phase = p_5x
                debug_phase_offset = po_5x

            phase = (-1 if phase < 0 else 1) * (abs(phase) % 180)
            # print('Phase: {0}\t Offset: {1}\tFinal: {2}'.format(debug_phase, debug_phase_offset, phase))
            results[f] = (impedance, phase)
            self.magnitudes.append(m)

        return results


    def spi_write(self):
        self.__spi_chip_select()
        self.__spi_chip_deselect()

    def __spi_chip_select(self):
        self.__gpio.set_mode(2, pigpio.OUTPUT)
        self.__gpio.write(2, 0)

    def __spi_chip_deselect(self):
        self.__gpio.write(2, 1)
        self.__gpio.set_mode(2, pigpio.ALT0)
