from Board import Board
# from traceback import print_exception

board = Board(0)
board.phase_offset = 0

# (calibrated_magnitudes_1x, calibrated_magnitudes_with_res_1x) = board.calibrate_1x(board.mux.port1)
# (calibrated_magnitudes_5x, calibrated_magnitudes_with_res_5x) = board.calibrate_5x(board.mux.port1)

board.cal_magnitudes_1x = {
    6842.249809273263: 6.643216298963706e-07,
    13163.97805158076: 7.596487901162353e-07,
    3162.3056502811364: 6.3371736879827e-07
}
board.cal_magnitudes_5x = {
    800.3892068862498: 6.246960799798232e-07,
    15340.903005527412: 6.531584272809784e-07,
    1170.8543930395444: 6.279979150423916e-07,
    2383.0687519456924: 6.357984904608593e-07,
    7731.829090305863: 6.466775120868852e-07
}

# print('1x')
# print(list(sorted(calibrated_magnitudes_with_res_1x.items())))
# print(calibrated_magnitudes_1x)
# print('5x')
# print(list(sorted(calibrated_magnitudes_with_res_5x.items())))
# print(calibrated_magnitudes_5x)

board.mux.select(board.mux.port1.channel5.reference)
board.sweep(10000, 200, 450)

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
