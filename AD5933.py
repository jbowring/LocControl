class AD5933:
    def __init__(self, bus):
        self.__settle_cycles = None
        self.__clock = None
        self.__start_freq = None
        self.__cur_freq = None
        self.__inc_freq = None
        
        self.Register.bus = bus
        self.Register.device_address = 0x0d

        self.control_1.write(0b00000010)  # set 200 mVpp range
        self.enter_standby()
        self.set_pga_multiplier(False)
        self.set_external_oscillator(False)
        self.set_settle_cycles(0)
        self.settle_cycles.write(0)  # TODO: Also decide what to do with this

    class Register:
        bus = None
        device_address = None

        def __init__(self, address, size):
            self.address = address
            self.size = size

        def write(self, data):
            for i in range(0, self.size):
                self.bus.write_byte_data(self.device_address, self.address + i,
                                         (data >> (self.size - (i + 1)) * 8) & 0xff)

        def read_signed(self):
            result = 0
            for i in range(0, self.size):
                result |= (self.bus.read_byte_data(self.device_address, self.address + i) << (
                            (self.size - (i + 1)) * 8))

            if result & (2 ** ((8 * self.size) - 1)):  # if sign bit is set
                result -= 2 ** (8 * self.size)  # compute negative value
            return result

        def read(self):
            result = 0
            for i in range(0, self.size):
                result |= self.bus.read_byte_data(self.device_address, self.address + i) << ((self.size - (i + 1)) * 8)
            return result

        def set(self, mask, data):
            self.write((self.read() & ~mask) | data)

        def set_bit(self, bit, value):
            self.write((self.read() & ~(1 << bit)) | (value << bit))

        def get_bit(self, bit):
            return (self.read() >> bit) & 0b1

    control = Register(0x80, 2)
    control_1 = Register(0x80, 1)
    control_2 = Register(0x81, 1)
    start_freq = Register(0x82, 3)
    inc_freq = Register(0x85, 3)
    num_steps = Register(0x88, 2)
    settle_cycles = Register(0x8a, 2)
    status = Register(0x8f, 1)
    temp_data = Register(0x92, 2)
    real_data = Register(0x94, 2)
    imag_data = Register(0x96, 2)

    def output_freq(self):
        return self.__cur_freq

    def freq_code(self, freq):
        return int(freq * pow(2, 27) / (self.__clock / 4))

    def set_start_end_steps(self, start, end, steps):
        self.start_freq.write(self.freq_code(start))
        self.__start_freq = int(start)
        self.num_steps.write(int(steps))
        self.inc_freq.write(self.freq_code((end - start) / steps))
        self.__inc_freq = int((end - start) / steps)

    def set_start_end_increment(self, start, end, increment):
        self.start_freq.write(self.freq_code(start))
        self.__start_freq = int(start)
        print(str(int((end - start) / increment)) + ' steps')
        self.num_steps.write(int((end - start) / increment))
        self.inc_freq.write(self.freq_code(increment))
        self.__inc_freq = int(increment)

    def set_start_increment_steps(self, start, increment, steps):
        self.start_freq.write(self.freq_code(start))
        self.__start_freq = int(start)
        self.num_steps.write(int(steps))
        self.inc_freq.write(self.freq_code(increment))
        self.__inc_freq = int(increment)

    def set_settle_cycles(self, cycles):
        # self.settle_cycles.write(cycles)  # TODO: Decide what to do about this
        self.__settle_cycles = cycles

    def get_settle_cycles(self):
        return self.__settle_cycles

    def data_ready(self):
        return self.status.get_bit(1)

    def sweep_complete(self):
        return self.status.get_bit(2)

    def set_external_oscillator(self, enable):
        self.control_2.set_bit(3, 1 if enable else 0)
        self.__clock = 2000000 if enable else 16776000

    def clock(self) -> int:
        return self.__clock

    def set_pga_multiplier(self, enable):
        self.control_1.set_bit(0, 0 if enable else 1)

    def get_pga_multiplier(self):
        return self.control_1.get_bit(0) == 0

    def reset(self):
        self.control_2.set_bit(4, 1)
        self.control_2.set_bit(4, 0)
        self.__cur_freq = None

    def start_output(self):
        self.control_1.set(0b11110000, 0b00010000)
        self.__cur_freq = self.__start_freq

    def start_sweep(self):
        # self.set_external_oscillator(self.__cur_freq < 5000)
        self.control_1.set(0b11110000, 0b00100000)

    def increment_freq(self):
        # self.set_external_oscillator(self.__cur_freq < 5000)
        self.control_1.set(0b11110000, 0b00110000)
        self.__cur_freq += self.__inc_freq

    def repeat_freq(self):
        self.control_1.set(0b11110000, 0b01000000)

    def measure_temperature(self):
        self.control_1.set(0b11110000, 0b10010000)

    def power_down(self):
        self.control_1.set(0b11110000, 0b10100000)
        self.__cur_freq = None

    def enter_standby(self):
        self.control_1.set(0b11110000, 0b10110000)
