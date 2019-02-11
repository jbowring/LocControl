from smbus2 import SMBus, i2c_msg
from AD5933 import AD5933
from math import sqrt, atan, pi, isnan
from time import sleep
import numpy
import pigpio
from scipy.interpolate import griddata
import struct


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

        self.address = address
        self.__bus = SMBus(i2c_port)
        self.select()
        self.ad5933 = AD5933(self.__bus)
        self.ad5933.set_settle_cycles(100)  # TODO: Decide final value
        self.mux = self.Mux(self.__bus)
        self.eeprom = self.Eeprom(self.__bus)

        # TODO: Get calibration from eeprom
        self.interp_1x = self.CalibrationConstants()
        self.interp_5x = self.CalibrationConstants()

        self.interp2d_1x = None
        self.interp2d_5x = None

    def load_calibration_constants(self, cal_1x, cal_5x):
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
        self.__bus.i2c_rdwr(i2c_msg.write(0x70 + self.address, [0xff]))

    def deselect(self):
        self.__bus.i2c_rdwr(i2c_msg.write(0x70 + self.address, [0x00]))

    class Mux:
        def __init__(self, bus):
            self.__bus = bus
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
                    self.__bus.i2c_rdwr(i2c_msg.write(0x44 + i, [0x00]))

            data = (0b1 << (((terminal.channel - 1) // 4) * 2) + (1 if terminal.is_reference else 0)) | (
                    0b10000 << ((terminal.channel - 1) % 4))
            # print('{:08b}'.format(data))
            self.__bus.i2c_rdwr(i2c_msg.write(0x44 + port, [data]))

    class Eeprom:
        def __init__(self, bus):
            self.__bus = bus

        @staticmethod
        def _encode(data: dict):
            output = bytearray()
            for frequency, pairs in data.items():
                output.extend(struct.pack('d', frequency))
                for key, value in pairs.items():
                    output.extend(struct.pack('d', key))
                    output.extend(struct.pack('d', value))
            return output

        @staticmethod
        def _decode(data: bytearray, num_pairs):
            output = {}
            for i in range(0, len(data), 8 + (num_pairs * 16)):
                frequency = int(struct.unpack_from('d', data, i)[0])
                output[frequency] = {}
                for j in range(i + 8, (i + 8) + (num_pairs * 16), 16):
                    try:
                        output[frequency].update((struct.unpack_from('dd', data, j), ))
                    except struct.error:
                        break
            return output

    # def calibrate_1x(self, port: Mux.Port):
    #     cal_resistors = {
    #         100: port.channel1.impedance,
    #         220: port.channel2.impedance,
    #         499: port.channel3.impedance
    #     }
    #
    #     self.ad5933.set_pga_multiplier(False)
    #     self.cal_magnitudes_1x = self._calibrate(cal_resistors)
    #
    # def calibrate_5x(self, port: Mux.Port):
    #     cal_resistors = {
    #         499: port.channel3.impedance,
    #         1000: port.channel4.impedance,
    #         3300: port.channel1.reference,
    #         6800: port.channel5.impedance,
    #         10000: port.channel5.reference
    #     }
    #
    #     self.ad5933.set_pga_multiplier(True)
    #     self.cal_magnitudes_5x = self._calibrate(cal_resistors)

    def calibrate_1x_sweep(self, port: Mux.Port):
        cal_resistors = {
            100: port.channel1.impedance,
            220: port.channel2.impedance,
            499: port.channel3.impedance
        }

        self.ad5933.set_pga_multiplier(False)
        return self._calibrate_sweep(cal_resistors)

    def calibrate_5x_sweep(self, port: Mux.Port):
        cal_resistors = {
            499: port.channel3.impedance,
            1000: port.channel4.impedance,
            3300: port.channel1.reference,
            6800: port.channel5.impedance,
            10000: port.channel5.reference
        }

        self.ad5933.set_pga_multiplier(True)
        return self._calibrate_sweep(cal_resistors)

    # def _calibrate(self, cal_resistors):
    #     calibrated_magnitudes = {}
    #     calibrated_magnitudes_with_res = {}
    #
    #     for cal_res, cal_port in sorted(cal_resistors.items()):
    #         self.mux.select(cal_port)
    #         real = []
    #         imag = []
    #         for i in range(0, 100):
    #             self.ad5933.start_output()
    #             self.ad5933.start_sweep()
    #
    #             sleep(0.1)
    #             while not self.ad5933.data_ready():
    #                 sleep(0.1)
    #
    #             real.append(self.ad5933.real_data.read_signed())
    #             imag.append(self.ad5933.imag_data.read_signed())
    #             self.ad5933.repeat_freq()
    #
    #         real = sum(real) / len(real)
    #         imag = sum(imag) / len(imag)
    #         phase = atan(imag / real) * 360 / (2 * pi)
    #         magnitude = sqrt((real ** 2) + (imag ** 2))
    #         gain_factor = (5 if self.ad5933.get_pga_multiplier() else 1) / (cal_res * magnitude)
    #
    #         calibrated_magnitudes[magnitude] = gain_factor
    #         calibrated_magnitudes_with_res[magnitude] = {cal_res, gain_factor}
    #         print(gain_factor)
    #         print(phase)
    #
    #     return calibrated_magnitudes, calibrated_magnitudes_with_res

    # def _calibrate(self, cal_resistors):
    #     calibrated_magnitudes = {}
    #     calibrated_magnitudes_with_res = {}
    #
    #     self.ad5933.set_start_increment_steps(start=4960, increment=198, steps=500)
    #     self.ad5933.start_output()
    #     self.ad5933.start_sweep()
    #
    #     for cal_res, cal_port in sorted(cal_resistors.items()):
    #         self.mux.select(cal_port)
    #         magnitudes = []
    #         phases = []
    #
    #         for i in range(0, 10):
    #             (magnitude, phase) = self.get_measurement()
    #             magnitudes.append(magnitude)
    #             phases.append(phase)
    #
    #         magnitude = sum(magnitudes) / len(magnitudes)
    #         phase = sum(phases) / len(phases)
    #
    #         gain_factor = (5 if self.ad5933.get_pga_multiplier() else 1) / (cal_res * magnitude)
    #
    #         calibrated_magnitudes[magnitude] = gain_factor
    #         calibrated_magnitudes_with_res[magnitude] = {cal_res, gain_factor}
    #         print(cal_res)
    #         print(gain_factor)
    #         print(phase)
    #
    #     return calibrated_magnitudes  # , calibrated_magnitudes_with_res

    def _calibrate_sweep(self, cal_resistors):
        calibrated = {}

        for cal_res, cal_port in sorted(cal_resistors.items()):
            self.mux.select(cal_port)

            sweep = self.sweep_raw(start=1000, increment=198, steps=500, repeats=100)

            if len(calibrated) == 0:
                for freq in sweep.keys():
                    calibrated[freq] = {}

            for (freq, (magnitude, phase)) in sweep.items():
                calibrated[freq][magnitude] = 1 / (cal_res * magnitude)

            if cal_res == sorted(cal_resistors.keys())[len(cal_resistors) // 2]:
                for (freq, (magnitude, phase)) in sweep.items():
                    calibrated[freq][0.0] = phase

        return calibrated

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

        sleep_time = (32 * 1024 / self.ad5933.clock()) + (self.ad5933.get_settle_cycles() / self.ad5933.output_freq())

        timeouts = 0
        while len(real) < repeats:
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

        try:
            phase = atan(imag / real)
        except ZeroDivisionError:
            phase = atan(imag * float('Inf'))

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
        assert(1000 <= start <= 100000 and increment >= 0 and 0 <= steps <= 511)
        self.ad5933.set_pga_multiplier(False)
        results_1x = self.sweep_raw(start, increment, steps, repeats)
        self.ad5933.set_pga_multiplier(True)
        results_5x = self.sweep_raw(start, increment, steps, repeats)

        results = {}
        for (frequency, pair_1x), (_, pair_5x) in zip(sorted(results_1x.items()), sorted(results_5x.items())):
            results[frequency] = (pair_1x, pair_5x)

        return self.adjust(results)

    def sweep_raw(self, start, increment, steps, repeats):
        assert(1000 <= start <= 100000 and increment >= 0 and 0 <= steps <= 511)
        ext_limit = 11999
        int_start = start
        int_steps = steps
        results = {}
        if start <= ext_limit:
            self.ad5933.set_external_oscillator(True)
            ext_steps = min(steps, (ext_limit - start) // increment)
            self.ad5933.set_start_increment_steps(start, increment, ext_steps)
            self.ad5933.start_output()
            self.ad5933.start_sweep()
            results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            while not self.ad5933.sweep_complete():
                self.ad5933.increment_freq()
                results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            self.ad5933.reset()
            int_start += (ext_steps + 1) * increment
            int_steps -= ext_steps + 1

        if (start + (increment * steps)) > ext_limit:
            self.ad5933.set_external_oscillator(False)
            self.ad5933.set_start_increment_steps(int_start, increment, int_steps)
            self.ad5933.start_output()
            self.ad5933.start_sweep()
            results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            while not self.ad5933.sweep_complete() and self.ad5933.output_freq() <= (100000 - increment):
                self.ad5933.increment_freq()
                results[self.ad5933.output_freq()] = self.get_measurement(repeats=repeats)
            self.ad5933.reset()

        return results
    
    def adjust(self, results):
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

        print((self.interp_1x.fs, self.interp_1x.ms))

        gfs_1x = griddata((self.interp_1x.fs, self.interp_1x.ms), self.interp_1x.gfs, (frequencies, magnitudes_1x))
        gfs_nearest = griddata((self.interp_1x.fs, self.interp_1x.ms), self.interp_1x.gfs, (frequencies, magnitudes_1x),
                               method='nearest')
        for i in range(len(gfs_1x)):
            if isnan(gfs_1x[i]):
                gfs_1x[i] = gfs_nearest[i]
        phase_offsets_1x = griddata(self.interp_1x.po_fs, self.interp_1x.pos, frequencies)
                
        gfs_5x = griddata((self.interp_5x.fs, self.interp_5x.ms), self.interp_5x.gfs, (frequencies, magnitudes_5x))
        gfs_nearest = griddata((self.interp_5x.fs, self.interp_5x.ms), self.interp_5x.gfs, (frequencies, magnitudes_5x),
                               method='nearest')
        for i in range(len(gfs_5x)):
            if isnan(gfs_5x[i]):
                gfs_5x[i] = gfs_nearest[i]
        phase_offsets_5x = griddata(self.interp_5x.po_fs, self.interp_5x.pos, frequencies)
                
        results = {}
        for f, m_1x, gf_1x, p_1x, po_1x, m_5x, gf_5x, p_5x, po_5x in zip(frequencies, magnitudes_1x, gfs_1x, phases_1x,
                                                                         phase_offsets_1x, magnitudes_5x, gfs_5x,
                                                                         phases_5x, phase_offsets_5x):
            impedance = 1 / (m_1x * gf_1x)
            phase = p_1x - po_1x
            if impedance > 500:
                impedance = 1 / (m_5x * gf_5x)
                phase = p_5x - po_5x

            results[f] = (impedance, phase)

        return results
