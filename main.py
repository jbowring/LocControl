from Board import Board
# from traceback import print_exception
import datetime
import cal
from scipy.interpolate import interp2d, griddata
import numpy
from time import sleep

board = Board(0)
board.phase_offset = 0

# then = datetime.datetime.now()
#
# board.calibrate_1x_sweep(board.mux.port1)
# print('1x')
# print(board.cal_magnitudes_1x)
# print()
# print()
# freqs = []
# mags = []
# gfs = []
#
# for f, d in sorted(board.cal_magnitudes_1x.items()):
#     for mag, gf in sorted(d.items()):
#         freqs.append(f)
#         mags.append(mag)
#         gfs.append(gf)
#
# print('x = ', end='')
# print(freqs, end=';\n')
# print('y = ', end='')
# print(mags, end=';\n')
# print('z = ', end='')
# print(gfs, end=';\n')
#
# print()
# print()
# print(datetime.datetime.now() - then)
# print()
# print()
#
#
# then = datetime.datetime.now()
#
# board.calibrate_5x_sweep(board.mux.port1)
# print('5x')
# print(board.cal_magnitudes_5x)
# print()
# print()
#
# freqs = []
# mags = []
# gfs = []
#
# for f, d in sorted(board.cal_magnitudes_5x.items()):
#     for mag, gf in sorted(d.items()):
#         freqs.append(f)
#         mags.append(mag)
#         gfs.append(gf)
#
# print('x = ', end='')
# print(freqs, end=';\n')
# print('y = ', end='')
# print(mags, end=';\n')
# print('z = ', end='')
# print(gfs, end=';\n')
#
# print()
# print()
# print(datetime.datetime.now() - then)
# print()
# print()

# freqs = []
# mags = []
# gfs = []
# for f, d in sorted(cal.magnitudes_1x.items()):
#     for mag, gf in sorted(d.items()):
#         freqs.append(f)
#         mags.append(mag)
#         gfs.append(gf)
# # board.interp_1x['freqs'] = numpy.asarray(freqs)
# # board.interp_1x['mags'] = numpy.asarray(mags)
# # board.interp_1x['gfs'] = numpy.asarray(gfs)
# board.interp_1x_fn = interp2d(freqs, mags, gfs, kind='linear')
#
# freqs = []
# mags = []
# gfs = []
# for f, d in sorted(cal.magnitudes_5x.items()):
#     for mag, gf in sorted(d.items()):
#         freqs.append(f)
#         mags.append(mag)
#         gfs.append(gf)
# # board.interp_5x['freqs'] = numpy.asarray(freqs)
# # board.interp_5x['mags'] = numpy.asarray(mags)
# # board.interp_5x['gfs'] = numpy.asarray(gfs)
# board.interp_5x_fn = interp2d(freqs, mags, gfs, kind='linear')

# board.cal_magnitudes_1x = cal.magnitudes_1x
# board.cal_magnitudes_5x = cal.magnitudes_5x

board.load_calibration_constants(cal.magnitudes_1x, cal.magnitudes_5x)

board.mux.select(board.mux.port1.channel4.impedance)
freqs = []
mags = []
gfs = []
for _ in range(1):
    print('NEXT')
    # sleep(5)
    print('RUNNING')
    board.raw = {}
    board.sweep(start=1000, increment=200, steps=495)

    for f, pair in sorted(board.raw.items()):
        for mag, gf in sorted(pair.items()):
            freqs.append(f)
            mags.append(mag)
            gfs.append(gf)

    then = datetime.datetime.now()
    griddata((board.interp_5x['freqs'], board.interp_5x['mags']), board.interp_5x['gfs'],
             (freqs, mags))
    print(datetime.datetime.now() - then)


print(freqs)
print(mags)
print(gfs)

# while True:
#     board.sweep(start=1000, increment=200, steps=495)
#
# board.ad5933.start_output()
# board.ad5933.start_sweep()
# while True:
#     try:
#         r = board.get_measurement(calibrated_magnitudes_1x, calibrated_magnitudes_5x, phase_offset)
#         # print(('x5' if board.ad5933.get_pga_multiplier() else 'x1') + ': {0:.3f} kΩ\t{1:.2f}˚'.format(int(r[0])/1000, r[1]))
#         print(str(board.ad5933.output_freq()) + ' Hz: {0:.3f} kΩ\t{1:.2f}˚'.format(int(r[0]) / 1000, r[1]))
#     except TimeoutError as err:
#         print_exception(None, err, err)
#
#     input()
#
#     if board.ad5933.sweep_complete() or board.ad5933.output_freq() > 5000:
#         break
#     else:
#         board.ad5933.increment_freq()
