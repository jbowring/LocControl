from Board import Board
import datetime
import cal

board = Board(0)

# for cal_fn in (board.calibrate_1x_sweep, board.calibrate_5x_sweep):
#     then = datetime.datetime.now()
#     cal = cal_fn(board.mux.port1)
#
#     po_freqs = []
#     pos = []
#     freqs = []
#     mags = []
#     gfs = []
#
#     for f, d in sorted(cal.items()):
#         for mag, gf in sorted(d.items()):
#             if mag == 0:
#                 po_freqs.append(f)
#                 pos.append(gf)
#             else:
#                 freqs.append(f)
#                 mags.append(mag)
#                 gfs.append(gf)
#
#     print(cal)
#     print()
#     print()
#     print('v = ', end='')
#     print(po_freqs, end=';\n')
#     print('w = ', end='')
#     print(pos, end=';\n')
#     print('x = ', end='')
#     print(freqs, end=';\n')
#     print('y = ', end='')
#     print(mags, end=';\n')
#     print('z = ', end='')
#     print(gfs, end=';\n')
#     print()
#     print()
#     print(datetime.datetime.now() - then)
#     print()
#     print()

board.load_calibration_constants(cal.calibrated_1x, cal.calibrated_5x)
board.mux.select(board.mux.port1.channel4.impedance)
while True:
    print(sorted(board.sweep(start=1000, increment=200, steps=495).items()))
