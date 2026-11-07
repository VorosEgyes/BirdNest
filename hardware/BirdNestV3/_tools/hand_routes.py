#!/usr/bin/env python3
"""
The routes that are drawn by hand.

Some of the nets of the board can not be routed by the router: the
router draws a track that runs over the copper of another net, and the
board would have more errors than it had before.  These routes are
drawn here, one net at a time, and every one of them is measured by the
design rules checker afterwards.

The route replaces the whole copper of its net: the tracks that are
there are removed first and the route is drawn instead.  So a net that
belongs here is a net whose copper is made by hand and not copied from
the V2 layout.  The nets in KEEP are the exception: their route of the
V2 is good, and only a piece has to be added to it.

The script is idempotent: a route that is already there is not drawn
again.  The removals are done by delitem.py, in a process of its own,
because removing an item invalidates the wrapper of the board.

The table holds the routes that are drawn by hand.  A route is measured
before it is drawn: the line may not come closer to the copper of
another net than the clearance, and a route that does not fit is not
drawn at all.  The script says which copper is in the way.

The clearance of a pad is its own local clearance when it has one, and
the clearance of the class of its net otherwise.  The pins of the U11
have 0.15 millimetres, because they are half a millimetre apart, and
the class of the signal has 0.25 millimetres.  The rules live in the
project file, not in the board.

Run:  hand_routes.py [net name]
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew                    # noqa: E402  the board of KiCad

from maze4 import load_classes    # noqa: E402  the rules of the nets
import safe_board               # noqa: E402  the guard of the board

PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
JSON = "/tmp/hand_routes_drc.json"

# The routes: net -> list of (width, layer, [points])
# The points are in millimetres, (x, y).  The first and the last point
# of a route are the pads of the net.  A net with three pads has two
# routes that share their beginning.
#
# The width of a route may change along the way: the point may hold a
# third number, the width of the line from that point on.  A pin of the
# U11 is only 0.35 millimetres wide and half a millimetre from its
# neighbour, so the line that leaves it is narrow, and it grows to the
# width of the net further away.
#
#   (0.2, "F", [(179.675, 90.525), (179.675, 92.5, 0.8)])
#
# The width of the line is the width of the segment that starts at the
# point, so the last point of a route does not need a width.
#
# The line may also change to the other copper: the point may hold a
# fourth number, the layer of the line from that point on.  A via is
# drawn where the line changes, and it sits on the point.
#
#   (0.8, "F", [(179.442, 85.175), (179.442, 83.5, 0.8, "B"),
#               (186.155, 83.5, 0.8, "B"), (186.155, 91.525)])
#
# The via needs room of its own: it is 0.6 millimetres wide, so the
# point of the change has to be far enough from the copper of the
# other nets.
ROUTES = {
    # The set current of the charger: the pin 2 of the U11 and the
    # resistor R12.
    #
    # The pins of the U11 are 0.5 millimetres apart and only 0.35
    # millimetres wide, and the ground pad of the package is in the
    # middle of them.  There is no room for a line between the pins,
    # and not for a via on a pin either.  So the line leaves the pin to
    # the left, on the side of the package where the resistor R12 is.
    #
    # The line is 0.2 millimetres wide.  It leaves the pin at the height
    # of the pin, so that it does not run over the pin above it.
    "Net-(U11-ISET)": [(0.2, "F", [
        (179.675, 89.525),
        (179.000, 89.525),
        (179.000, 88.425),
        (176.155, 88.425),
    ])],

    # The temperature of the battery: the pin 1 of the U11, the
    # thermistor TH1 and the resistor R14.
    #
    # The pin 1 is the topmost pin of the left column, so the line can
    # go up over the package.  It goes over the package to the right,
    # down between the package and the resistor R14, and to the
    # thermistor on the left of the resistor.  The branch to the
    # resistor R14 is a second route of the same net, and it starts
    # where the first one turns, so the line over the package is drawn
    # only once.
    "Net-(U11-TEMP)": [
        # The pin 1 to the resistor R14: the line goes over the package
        # to the right, on the north side of the line of the charger,
        # and down to the pad of the resistor.  The line stands higher
        # than before, so that the lines of the charger may leave the
        # pins of the U11 to the east.
        (0.2, "F", [
            (179.675, 89.025),
            (179.675, 86.600),
            (186.155, 86.600),
            (186.155, 88.425),
        ]),
        # The thermistor TH1: the line leaves the line over the package
        # on the west of the resistor, goes to the back copper, where it
        # may pass the lines of the charger, and comes to the thermistor
        # on the front copper again.
        (0.2, "F", [
            (184.700, 86.600),
            (184.700, 88.850, 0.2, "B"),
            (185.155, 93.200, 0.2, "B"),
        ]),
        # The thermistor is now a pin header of 1.00 mm, so its two
        # pads are 1 mm apart: the pad of the signal is on the east of
        # the pad of the ground, and the line comes to it from the
        # north west.
        (0.2, "B", [
            (185.155, 93.200, 0.2, "F"),
            (186.155, 95.975),
        ]),
    ],

    # The reading of the voltage of the battery: the resistor R29, the
    # capacitor C22, the resistor R30 and the pin IO12 of the U4.
    #
    # The three parts are in the corner of the board in the V3, and the
    # line of the V2 that came from the U4 ends in the middle of the
    # board, where the parts of the V2 used to be.  The line is led
    # from there to the capacitor, and the three parts are joined to
    # each other.
    "/BAT_MON": [
        (0.2, "F", [
            (123.000, 83.950),
            (108.175, 61.568),
        ]),
        (0.2, "F", [
            (105.155, 58.425),
            (108.175, 61.568),
        ]),
        (0.2, "F", [
            (108.175, 61.568),
            (111.155, 61.525),
        ]),
    ],

    # The input of the charger: the pin 4 of the U11, the capacitor
    # C24, the capacitor C25, the resistor R13, the resistor R14, the
    # diode D10 and the test point TP2.
    #
    # The pin 4 of the U11 is the lowest pin of the left column, and
    # the ground pin is right above it.  The line that leaves the pin
    # is 0.2 millimetres wide, and it goes down to the resistor R13
    # below the package.
    #
    # The line from the R13 to the C24 is 0.8 millimetres wide.
    #
    # The line from the C24 to the C25 and from there to the R14 goes
    # to the back copper: the line of the set current runs over the
    # place where the line would go on the front, and a line may not
    # cross another line.  The via is on the pad of the C24.  On the
    # back copper the line goes between the two capacitors and then
    # under the R14, which is why the LED D7 is not in the way: it is
    # on the front.
    #
    # The diode D10 and the test point TP2 are not joined yet: they
    # stand far away from the package.
    "/VIN_PROT": [
        (0.2, "F", [
            (179.675, 90.525),
            (179.675, 93.000),
            (176.155, 93.000),
            (176.155, 93.925),
        ]),
        (0.8, "F", [
            (176.155, 93.925),
            (179.442, 94.675),
        ]),
        # the line from the C24 down to the C25 on the back copper:
        # the via is on the pad of the C24 and the other one is on the
        # pad of the C25.  The line goes straight down between the two
        # pads: on the back copper the package of the U11 is not in the
        # way.
        (0.8, "F", [
            (179.442, 94.675, 0.8, "B"),
            (179.442, 85.175, 0.8, "F"),
        ]),
        # the line from the C25 to the R14 on the back copper, with a
        # via on the pad of the R14
        (0.8, "B", [
            (179.442, 85.175),
            (186.155, 85.175, 0.8, "B"),
            (186.155, 91.525, 0.8, "F"),
        ]),
        # the line from the R14 to the diode D10, over the top of the
        # board: the resistor R14 and the LED D7 stand next to each
        # other, so the line cannot go straight down
        (0.8, "F", [
            (186.155, 91.525),
            (189.500, 91.525),
            (189.500, 81.275),
            (192.070, 81.275),
        ]),
    ],

    # The five volts of the board: the test point TP4 and the
    # capacitor C12.
    #
    # The line of the V2 reaches the C12, and the test point TP4 stands
    # in the other corner of the board, 40 millimetres away.  There is
    # no room for a line of one millimetre on the front copper, so the
    # line goes to the back copper, where there is nothing, and comes
    # back on the pads of the two parts.
    #
    # The pad of the C12 has a hole in it, so it is copper on both
    # layers: the line of the back copper ends on the pad itself and
    # needs no via there.  The pad of the TP4 is on the front only, so
    # the via sits on it.
    "/+5V": [
        (1.0, "F", [
            (113.525, 50.525, 1.0, "B"),
            (120.000, 50.525, 1.0, "B"),
            (120.000, 90.000, 1.0, "B"),
            (148.182, 90.000, 1.0, "B"),
            (148.182, 97.000),
        ]),
    ],

    # The output of the charge pump of the U10: the switch Q3 and the
    # pin 3 of the U10.
    #
    # The pin 3 of the U10 is the lowest pin of the left column, and
    # the switch Q3 stands above it.  The line of the Q3 goes straight
    # down, but then it runs over the pins 1 and 2 of the U10, so it
    # goes around the package on the left and comes back under it.
    "Net-(U10-OC)": [
        (0.25, "F", [
            (140.260, 105.265),
            (137.500, 105.265),
            (137.500, 111.000),
            (139.438, 111.000),
            (139.438, 110.350),
        ]),
    ],

    # The output of the diode of the U10: the switch Q3 and the pin 1
    # of the U10.  The two parts stand next to each other, so the line
    # goes straight from one to the other.
    "Net-(U10-OD)": [
        (0.25, "F", [
            (146.020, 105.265),
            (139.438, 108.450),
        ]),
    ],

    # The gate of the switch Q9: the switch itself, the resistor R27
    # and the resistor R28.  The three parts stand in the corner of
    # the board, and the line goes around the switch on the left.
    "Net-(Q9-G)": [
        (0.25, "F", [
            (107.549, 113.900),
            (107.549, 107.000),
            (109.925, 107.000),
            (109.925, 108.155),
        ]),
        # the branch to the resistor R28
        (0.25, "F", [
            (109.925, 108.155),
            (109.925, 109.500),
            (117.525, 109.500),
            (117.525, 111.155),
        ]),
    ],

    # The supply of the U10: the resistor R11, the pin 5 of the U10 and
    # the capacitor C19.
    #
    # The three parts stand far from each other, and the inductor L1
    # and the capacitor C15 stand in the way on the front copper.  The
    # line to the capacitor goes around the U10 on the right and then
    # under the C15.
    #
    # The branch to the resistor R11 starts where the line to the
    # capacitor turns, so the short piece next to the U10 is drawn only
    # once.
    "Net-(U10-VCC)": [
        (0.25, "F", [
            (141.713, 109.400),
            (142.800, 109.400),
            (142.800, 113.600),
            (129.675, 113.600),
            (129.675, 111.567),
        ]),
        # the branch to the resistor R11: under the inductor L1
        (0.25, "F", [
            (142.800, 109.400),
            (142.800, 115.000),
            (160.155, 115.000),
            (160.155, 114.025),
        ]),
    ],

    # The line between the two LEDs of the charger: the LED D8, the LED
    # D7 and the resistor R13.
    #
    # The two LEDs stand on the two sides of the charger, and the line
    # of the five volts and the line of the input of the charger cross
    # the way on the front copper.  So the line goes to the back copper
    # for the whole way.
    "Net-(D7-A)": [
        # The two LEDs and the resistor R13: the line leaves the pads of
        # the LEDs to the north, and goes to the back copper, where it
        # runs to the west of the board and down to the resistor.
        (0.2, "F", [
            (185.900, 80.975),
            (185.900, 79.800),
            (189.400, 79.800, 0.2, "B"),
            (175.000, 79.800, 0.2, "B"),
            (175.000, 97.025, 0.2, "B"),
            (176.155, 97.025, 0.2, "F"),
        ]),
        # The LED D7 to the line of the two LEDs: the line ends on the
        # line of the D8, so there is only one via on the two LEDs.
        (0.2, "F", [
            (188.100, 80.975),
            (188.100, 79.800),
        ]),
    ],

    # The line between the two diodes: the diode D9, the diode D10 and
    # the solar panel connector J4.
    #
    # The two diodes stand next to each other in the corner of the
    # board, and the ground pad of the D9 stands between them and the
    # connector.  So the line goes around the D9 on the right.
    "Net-(D10-A)": [
        # the diode D10 to the diode D9
        (0.25, "F", [
            (196.070, 81.275),
            (198.000, 81.275),
            (198.000, 86.570),
            (195.775, 86.570),
        ]),
        # the diode D10 to the connector J4: the line starts where the
        # line to the D9 starts, so there is only one via on the pad of
        # the D10
        (0.25, "F", [
            (198.000, 81.275),
            (198.000, 110.545),
            (189.673, 110.545),
        ]),
    ],

    # The ground pin of the U11.  The zone of the ground does not reach
    # the pin: the pin is only 0.35 millimetres wide and the zone keeps
    # away from it.  So a short line joins the pin to the zone on the
    # left of the package.
    "GND": [
        (0.2, "F", [
            (179.675, 90.025),
            (178.200, 90.025),
        ]),
        # The two ground pins of the Q3: the zone keeps away from them
        # too, because they stand close by.  A thin line joins them,
        # and it goes to the left, where the zone is.
        (0.2, "F", [
            (140.260, 103.965),
            (140.260, 104.615),
        ]),
        (0.2, "F", [
            (140.260, 104.615),
            (137.000, 104.615),
        ]),
    ],

    # The positive pole of the battery: the connector BT3, the switch
    # Q9, the capacitor C23 and the resistor R11.
    #
    # The connector and the capacitor stand next to each other, so the
    # line goes straight from one to the other.  The switch stands
    # between them, and the line to the switch goes around it on the
    # right.
    #
    # The resistor R11 stands far away, and the inductor L1 is in the
    # way on the front copper.  So the line to the resistor goes to the
    # back copper.
    "/BAT_CELL+": [
        # the connector BT3 to the capacitor C23
        (0.8, "F", [
            (109.730, 126.000),
            (126.675, 113.067),
        ]),
        # the capacitor C23 to the switch Q9: the pad of the switch is
        # only one millimetre wide and the neighbour of it stands close
        # by, so the line is thin and it goes above the pad
        (0.4, "F", [
            (126.675, 113.067),
            (126.675, 112.500),
            (108.499, 112.500),
            (108.499, 111.700),
        ]),
        # the capacitor C23 to the resistor R11, on the back copper
        (0.8, "F", [
            (126.675, 113.067, 0.8, "B"),
            (160.155, 113.067, 0.8, "B"),
            (160.155, 110.925, 0.8, "F"),
        ]),
    ],

    # The negative pole of the battery: the connector BT3, the switch
    # Q3, the pin 6 of the U10, the resistor R27 and the capacitor C19.
    #
    # The switch Q3 is a small package with the pads close by, and the
    # pad of the diode is in the way.  So the line to the switch is
    # thin and it goes around the package on the right.
    #
    # The capacitor C19 and the resistor R27 stand on the two sides of
    # the chip U7, and the line cannot go over it.  So it goes to the
    # back copper.
    "/BAT_CELL-": [
        # the pin 6 of the U10 to the switch Q3
        (0.3, "F", [
            (141.713, 108.450),
            (147.500, 108.450),
            (147.500, 103.965),
            (146.020, 103.965),
        ]),
        # the switch Q3 to the pin 6 of the Q3: the two pads stand next
        # to each other, so a thin line joins them
        (0.3, "F", [
            (146.020, 103.965),
            (146.020, 104.615),
        ]),
        # the capacitor C19 to the resistor R27, on the back copper
        (0.8, "F", [
            (129.675, 108.442, 0.8, "B"),
            (129.675, 110.000, 0.8, "B"),
            (113.025, 110.000, 0.8, "B"),
            (113.025, 108.155, 0.8, "F"),
        ]),
        # the capacitor C19 to the pin 6 of the U10: the chip U7 and the
        # capacitor C15 stand in the way on the front copper, so the
        # line goes to the back copper and comes back at the U10
        (0.8, "F", [
            (129.675, 108.442),
            (131.000, 108.442, 0.8, "B"),
            (131.000, 105.000, 0.8, "B"),
            (141.713, 105.000, 0.8, "B"),
            (141.713, 108.450, 0.8, "F"),
        ]),
        # The negative pole of the battery at the connector BT3: the
        # connector stands in the corner of the board, far from the
        # rest.  The line goes to the back copper and comes back at the
        # pin 6 of the U10, where there is a via already.
        (0.4, "F", [
            (189.070, 126.000, 0.4, "B"),
            (176.750, 126.000, 0.4, "B"),
            (160.750, 110.000, 0.4, "B"),
            (160.500, 110.000, 0.4, "B"),
            (160.250, 109.750, 0.4, "B"),
            (143.000, 109.750, 0.4, "B"),
            (141.713, 108.450, 0.4, "B"),
        ]),
    ],

    # The whole line of the protected pole is written down here, and
    # not only the pieces that are new.  The net is drawn again from
    # scratch, so that no piece of it is left over from the layout of
    # the V2, and the line is the same every time the script runs.
    #
    # The line of the V2 reaches the resistor R25, and the parts of the
    # V3 stand elsewhere, so the line has to be built again:
    #
    #   - the resistor R29 stands in the corner of the board, far from
    #     the line of the V2.  The line to it goes along the left edge
    #     of the board, where there is nothing else;
    #   - the resistor R18 stands on the other side of the board, so
    #     the piece of the line that joins the R15 to the R18 is new;
    #   - the U7 stands in the way of the line that runs to the R25,
    #     so the line has to go around it;
    #   - the two capacitors C15 and C16 stand next to each other, and
    #     they hold the line of the charger;
    #   - the resistor R28 stands near the Q9, and the line to the pin
    #     2 of the Q9 goes to the back copper, where there is room for
    #     it;
    #   - the pins 5 and 8 of the U11 hold the line of the charger.
    #     The pins of the U11 are 0.5 millimetres apart and only 0.35
    #     millimetres wide: a via does not fit between them.  So the
    #     line leaves the pins to the right, on the side of the
    #     package, where the gap is.
    "/BAT_PROT+": [
        # the R29 to the R22, along the left edge of the board
        (0.8, "F", [
            (105.155, 61.525),
            (106.000, 61.525),
            (106.000, 89.450),
            (114.000, 89.450),
        ]),
        # the R22 to the C7, the R15 and the R18
        (0.8, "F", [
            (114.000, 89.450),
            (117.000, 89.438),
            (119.987, 89.438),
            (120.000, 89.450),
            (123.000, 89.450),
        ]),
        # The R18 to the Q6: the pins of the Q6 stand close by, and
        # there is no room between them.  So the line goes over them
        # and comes down on the pin 3.
        (0.8, "F", [
            (123.000, 89.450),
            (137.580, 89.450),
            (137.580, 94.000),
        ]),
        # The R22 to the R25, around the left of the board.  The line
        # goes from the pad of the R22 to the pad of the R25 without a
        # break: two lines that only meet at their ends are not joined,
        # the rules checker says so.  So the line has to go on from the
        # place where the other line comes.
        #
        # The line ends on the pin 8 of the U7 and not on the R25,
        # because the line of the R25 to the U7 already ends there.
        # Three lines that meet in one place without a pad and without
        # a hole in the board are not joined either.
        (0.8, "F", [
            (114.000, 89.450),
            (108.500, 94.950),
            (108.500, 102.000),
            (112.000, 105.500),
            (122.725, 105.500),
            (124.540, 107.315),
        ]),
        # The R25 to the U7: the line starts on the pad of the R25, so
        # the two lines are joined there, and it ends on the pad of the
        # U7.
        (0.8, "F", [
            (130.900, 105.500),
            (126.355, 105.500),
            (124.540, 107.315),
        ]),
        # The C15 to the C16
        (0.8, "F", [
            (135.675, 111.567),
            (132.675, 111.567),
        ]),
        # The C15 to the U7: the capacitors stand next to the charger,
        # and the line has to go around the parts that stand in the
        # way.  It goes to the left and up, and comes to the U7 from
        # the right.  The line is thinner than the rest of the line of
        # the net, because only the current of the filter goes
        # through this piece.
        #
        # The C16 hangs on the C15, so both are joined to the line of
        # the charger this way.
        (0.4, "F", [
            (135.675, 111.567),
            (135.750, 111.750),
            (132.250, 111.750),
            (130.750, 110.250),
            (129.250, 110.250),
            (127.750, 108.750),
            (126.000, 108.750),
            (124.750, 107.500),
            (124.540, 107.315),
        ]),
        # The R28 to the line of the R22: on the back copper, where
        # there is room for it.  The line goes up along the left of the
        # R27, where nothing stands.
        (0.8, "F", [
            (114.425, 111.155, 0.8, "B"),
            (114.500, 111.250, 0.8, "B"),
            (112.750, 111.250, 0.8, "B"),
            (112.000, 110.500, 0.8, "B"),
            (112.000, 110.250, 0.8, "B"),
            (111.750, 110.000, 0.8, "B"),
            (111.750, 105.750, 0.8, "B"),
            (112.000, 105.500, 0.8, "F"),
        ]),
        # The R28 to the pin 2 of the Q9: on the back copper, where
        # there is room for it.  The line starts on the pad of the R28
        # and comes back to the front copper at the pin 2 of the Q9.
        (0.8, "F", [
            (114.425, 111.155),
            (112.000, 111.155, 0.8, "B"),
            (112.000, 112.500, 0.8, "B"),
            (109.449, 112.500, 0.8, "B"),
            (109.449, 113.900, 0.8, "F"),
        ]),
        # the pin 5 of the U11 to the Q6: on the back copper
        (0.2, "F", [
            (182.375, 90.525),
            (183.100, 90.525),
            (183.100, 91.500, 0.2, "B"),
            (183.600, 91.500, 0.2, "B"),
            (183.600, 99.000, 0.2, "B"),
            (137.580, 99.000, 0.2, "B"),
            (137.580, 94.000),
        ]),
        # The pin 8 of the U11 to the line of the charger: the line
        # goes up over the package and to the back copper, where the
        # line of the charger runs down.  It does not go around the
        # pins any more, because the pins 6 and 7 of the U11 have to
        # leave the package to the east.
        (0.2, "F", [
            (182.375, 89.025),
            (182.375, 88.400),
            (183.100, 88.400, 0.2, "B"),
            (183.100, 91.500, 0.2, "B"),
        ]),
    ],

    # The supply of the board: the test point TP3 stands in the corner
    # of the board, far from the rest.  The line to it goes on the back
    # copper, along the left edge of the board, where there is nothing
    # else.
    #
    # The line of the Q6 to the L1 goes on the front copper, around the
    # parts that stand in the way.
    #
    # The line of the L1 to the C6, the C8 and the C10 is the line of
    # the V2, and it is written down again here, so that the whole line
    # of the net is the same every time the script runs.
    "/SYS_PWR": [
        (0.25, "F", [
            (111.025, 46.025, 0.25, "B"),
            (111.250, 46.250, 0.25, "B"),
            (111.250, 83.250, 0.25, "B"),
            (119.500, 91.500, 0.25, "B"),
            (121.500, 91.500, 0.25, "B"),
            (126.500, 96.500, 0.25, "B"),
            (131.000, 96.500, 0.25, "B"),
            # The corner of the line is 0.2 mm lower than it was: the
            # via of the /REF2V5 sits in the pad of the R17 and the
            # line of the /SYS_PWR went too close to it.
            (133.750, 99.450, 0.25, "B"),
            (134.250, 99.450, 0.25, "B"),
            (134.750, 98.950, 0.25, "B"),
            (134.750, 94.500, 0.25, "B"),
            (135.250, 94.000, 0.25, "B"),
            # the pin 2 of the Q6 has a hole in it: the line comes to
            # it on the back copper and no via is needed
            (135.040, 94.000),
        ]),
        (0.25, "F", [
            (135.040, 94.000),
            (135.250, 94.000),
            (135.250, 94.250),
            (136.500, 95.500),
            (139.500, 95.500),
            (141.500, 93.500),
            (150.500, 93.500),
            (151.000, 93.000),
            (153.250, 93.000),
            (153.500, 93.250),
            (153.500, 94.750),
            (153.250, 95.000),
            (148.000, 95.000),
            (147.000, 96.000),
            (147.000, 102.750),
            (148.000, 103.750),
            (148.000, 107.250),
            (153.000, 112.250),
            (153.000, 112.150),
        ]),
        (0.8, "F", [
            (153.000, 112.150),
            (153.175, 112.325),
            (163.238, 112.325),
            (163.380, 112.182),
            (167.500, 112.182),
            (167.755, 112.438),
            (174.000, 112.438),
            (174.062, 112.500),
            (177.000, 112.500),
        ]),
    ],

    # The input of the charger: the test point TP2 stands in the
    # corner of the board, far from the rest.  The line to it goes on
    # the back copper, over the top of the board, where there is
    # nothing else.
    #
    # The rest of the line is the line of the V2, and it stays.
    "/VIN_PROT": [
        (0.25, "F", [
            (109.025, 51.025, 0.25, "B"),
            (109.250, 51.250, 0.25, "B"),
            (109.250, 46.750, 0.25, "B"),
            (110.750, 45.250, 0.25, "B"),
            (120.000, 45.250, 0.25, "B"),
            (160.500, 85.750, 0.25, "B"),
            (162.750, 85.750, 0.25, "B"),
            (174.750, 97.750, 0.25, "B"),
            (176.500, 97.750, 0.25, "B"),
            (179.500, 94.750, 0.25, "B"),
            (179.442, 94.675),
        ]),
    ],

    # The green LED of the charger: the pad of the LED D7 to the pin 6
    # of the U11.  The line goes under the resistor R14 and up on the
    # east of it, to the pad of the LED.
    "/DONE_STAT": [
        (0.2, "F", [
            (182.375, 90.025),
            (188.100, 90.025),
            (188.100, 83.025),
        ]),
    ],

    # The other LED of the charger: the pad of the LED D8 to the pin 7
    # of the U11.  The line goes under the resistor R14 as well, and
    # comes to the LED from the east, below the pad of the LED D7.
    "/CHG_STAT": [
        (0.2, "F", [
            (182.375, 89.525),
            (187.600, 89.525),
            (187.600, 84.500),
            (185.900, 84.500),
            (185.900, 83.025),
        ]),
    ],

    # The reference voltage of the U8: the test point TP5 stands in
    # the corner of the board, far from the U8.  The line to it goes on
    # the back copper, along the left edge of the board, where there
    # is nothing else.
    #
    # The line of the U8 itself is on the front copper: the parts stand
    # close by, and the line goes around them.
    "/REF2V5": [
        (0.25, "F", [
            (113.525, 55.025, 0.25, "B"),
            (113.750, 55.250, 0.25, "B"),
            (113.750, 85.000, 0.25, "B"),
            (119.750, 91.000, 0.25, "B"),
            (123.500, 91.000, 0.25, "B"),
            (126.500, 94.000, 0.25, "B"),
            (129.750, 94.000, 0.25, "B"),
            (134.250, 98.500, 0.25, "B"),
            (134.050, 98.500, 0.25, "F"),
        ]),
        (0.25, "F", [
            (134.050, 98.500),
            (134.250, 98.500),
            (134.250, 102.250),
            (133.500, 103.000),
            (133.500, 102.975),
        ]),
        (0.25, "F", [
            (133.500, 102.975),
            (133.500, 101.075),
        ]),
        (0.25, "F", [
            (134.050, 98.500),
            (134.250, 98.500),
            (134.250, 105.250),
            (134.000, 105.500),
        ]),
    ],
}

# The nets whose copper is kept.  The route of the V2 is good, and only
# a piece is added to it: the parts of the V3 stand elsewhere than the
# parts of the V2, and the line of the V2 ends in the middle of the
# board.
#
# The battery reading: the line of the V2 comes from the U4 and ends
# in the middle of the board, where the parts of the V2 used to be.
#
# The five volts: the line of the V2 reaches the C12, and the test point
# TP4 stands in the other corner of the board.  The line to the TP4 is
# added to the line of the V2, and the line of the V2 stays.
#
# The ground: the zone stays, and the piece of the ground that is on
# the copper stays too.
#
# The nets whose copper is kept: the line of the V2 holds the parts of
# the V2 together, and only a piece is added to it, for the parts of
# the V3 that stand elsewhere.
#
# The protected pole of the battery and the supply of the board are not
# among them: the whole line of them is written down in the table of
# the routes, so it is drawn again from scratch every time and it is
# the same every time.
#
# The input of the charger is among them: only the test point TP2 is
# new, and the line of the V2 that joins the C24, the C25, the R13,
# the R14 and the D10 is good.
KEEP = {"/BAT_MON", "/+5V", "GND", "/VIN_PROT"}


def mm(v):
    return v / 1000000.0


def iu(v):
    """Millimetres as the integer that pcbnew wants."""
    return int(round(v * 1000000.0))


def point_seg(p, a, b):
    """The distance of the point p from the segment a-b."""
    (px, py) = p
    (ax, ay) = a
    (bx, by) = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def crosses_line(a, b, c, d):
    """Do the segments a-b and c-d cross each other?

    The answer is True when they do.  Two lines that only touch each
    other do not cross: the touching end points are the corners of a
    line, and the copper of the two nets meets there.
    """
    (ax, ay), (bx, by) = a, b
    (cx, cy), (dx, dy) = c, d

    def side(p, q, r):
        """Is the point r on the left of the line p-q?"""
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1 = side(c, d, a)
    d2 = side(c, d, b)
    d3 = side(a, b, c)
    d4 = side(a, b, d)
    # a point that lies on the line has a side of zero: the lines only
    # touch each other then, and that is not a crossing
    if d1 == 0 or d2 == 0 or d3 == 0 or d4 == 0:
        return False
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def layer_of(name):
    """The layer of a route of the table."""
    return pcbnew.F_Cu if name == "F" else pcbnew.B_Cu


def layer_name(layer):
    """The name of a layer: "F" for the front, "B" for the back."""
    return "F" if layer == pcbnew.F_Cu else "B"


def self_class(board, net):
    """The class of the net."""
    bnet = board.FindNet(net)
    if bnet is None:
        return "Default"
    return (bnet.GetNetClassName() or "").split(",")[0].strip()


def rule_of(board, net):
    """The rules of the net: the clearance, the width and the via."""
    return load_classes().get(self_class(board, net)) or {}


def segments_of(points, width, layer="F"):
    """The segments of a route, with the width and the layer of every one.

    The answer is a list of ((x0, y0), (x1, y1), width, layer).  A point
    may hold a third number, the width of the line from that point on,
    and a fourth one, the layer of the line from that point on.
    """
    out = []
    w = width
    lay = layer
    for i in range(len(points) - 1):
        p = points[i]
        if len(p) > 2:
            w = p[2]
        if len(p) > 3:
            lay = p[3]
        out.append(((p[0], p[1]), (points[i + 1][0], points[i + 1][1]), w,
                    lay))
    return out


def snap_to_pads(board, net, routes):
    """The routes, with their points on the pads of the net.

    The points of the routes are written down with three decimals of
    a millimetre, but the middle of a pad is not on such a place: it
    is a whole number of nanometres away.  A line that stops a hair
    before the middle of a pad does not reach it, and the rules
    checker says that it hangs loose.

    So every point of a route that stands on a pad is moved onto the
    middle of that pad.
    """
    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            q = p.GetPosition()
            pads.append((q.x, q.y))
    # The vias of the net as well: a line that ends on a via has to
    # reach the via, and not the pad beside it.
    for t in board.GetTracks():
        if t.GetNetname() != net or t.GetClass() != "PCB_VIA":
            continue
        q = t.GetPosition()
        pads.append((q.x, q.y))
    out = []
    for (width, layer, points) in routes:
        new = []
        for p in points:
            x = iu(p[0])
            y = iu(p[1])
            best = None
            for (px, py) in pads:
                d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
                if d < 20000 and (best is None or d < best[0]):
                    best = (d, px, py)
            if best is not None:
                new.append((px_of(best), py_of(best)) + tuple(p[2:]))
            else:
                new.append(p)
        out.append((width, layer, new))
    return out


def px_of(best):
    """The x of a pad, in millimetres."""
    return best[1] / 1e6


def py_of(best):
    """The y of a pad, in millimetres."""
    return best[2] / 1e6


def route_is_there(board, net, routes):
    """Is the route of the net already on the board?

    Every track of the route is looked for: not only the first point
    of it.  Two routes of the same net may start at the same point, and
    then the start alone does not tell them apart.  One route counts
    once, however many tracks of it are on the board.

    The answer is True when every route of the table is on the board.
    """
    for (width, layer, points) in routes:
        segs = segments_of(points, width, layer)
        if not track_is_one_of(board, net, segs):
            return False
    return True


def route_is_exactly_there(board, net, routes):
    """Is the copper of the net exactly the copper of the routes?

    Not only every route has to be on the board, but the board may not
    hold any other track of the net.  A piece of an older route would
    otherwise stay on the board for ever, and it would join the line
    in a place where two lines meet only at their ends: the rules
    checker does not join such lines, and it says that they hang
    loose.

    The answer is True when the copper of the net is the copper of the
    routes and nothing else.
    """
    wanted = []
    for (width, layer, points) in routes:
        for seg in segments_of(points, width, layer):
            wanted.append(seg)
    have = []
    for t in board.GetTracks():
        if t.GetNetname() != net or t.GetClass() == "PCB_VIA":
            continue
        a = t.GetStart()
        e = t.GetEnd()
        have.append(((mm(a.x), mm(a.y)), (mm(e.x), mm(e.y)),
                     mm(t.GetWidth()),
                     "F" if t.GetLayer() == pcbnew.F_Cu else "B"))
    if len(have) != len(wanted):
        return False

    def same(one, other):
        (a0, a1, w0, l0) = one
        (b0, b1, w1, l1) = other
        return (l0 == l1 and abs(w0 - w1) < 0.01
                and ((abs(a0[0] - b0[0]) < 0.02 and abs(a0[1] - b0[1]) < 0.02
                      and abs(a1[0] - b1[0]) < 0.02
                      and abs(a1[1] - b1[1]) < 0.02)
                     or (abs(a0[0] - b1[0]) < 0.02
                         and abs(a0[1] - b1[1]) < 0.02
                         and abs(a1[0] - b0[0]) < 0.02
                         and abs(a1[1] - b0[1]) < 0.02)))

    left = list(have)
    for w in wanted:
        for i, h in enumerate(left):
            if same(w, h):
                left.pop(i)
                break
        else:
            return False
    return not left


def track_is_one_of(board, net, segs):
    """Is there a track of the net that is one of the segments?

    The track has to have the same width and the same layer as the
    segment, and to lie on it.
    """
    for t in board.GetTracks():
        if t.GetNetname() != net or t.GetClass() == "PCB_VIA":
            continue
        a = t.GetStart()
        e = t.GetEnd()
        for s in segs:
            if s[3] != layer_name(t.GetLayer()):
                continue
            if abs(mm(t.GetWidth()) - s[2]) > 0.01:
                continue
            if (abs(mm(a.x) - s[0][0]) < 0.02
                    and abs(mm(a.y) - s[0][1]) < 0.02
                    and abs(mm(e.x) - s[1][0]) < 0.02
                    and abs(mm(e.y) - s[1][1]) < 0.02):
                return True
    return False


def vias_of(points, layer="F"):
    """The places where the line changes to the other copper.

    The answer is a list of (x, y).  A via is drawn at every one of
    them, and it sits on the point of the change.
    """
    out = []
    lay = layer
    for p in points:
        if len(p) > 3:
            if p[3] != lay:
                out.append((p[0], p[1]))
                lay = p[3]
    return out


def point_rect(p, rect):
    """The distance of a point and a rectangle.

    The rectangle is (x0, y0, x1, y1).  The answer is 0 when the point
    lies in the rectangle.
    """
    (x0, y0, x1, y1) = rect
    cx = min(max(p[0], x0), x1)
    cy = min(max(p[1], y0), y1)
    return ((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5


def seg_rect_distance(s0, s1, rect):
    """The distance of a segment and a rectangle.

    The answer is 0 when the segment goes through the rectangle.  The
    distance is the smallest of the distances of the ends of the
    segment to the rectangle and the distances of the corners of the
    rectangle to the segment.
    """
    (x0, y0, x1, y1) = rect
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i in range(4):
        if crosses_line(s0, s1, corners[i], corners[(i + 1) % 4]):
            return 0.0
    d = min(point_rect(s0, rect), point_rect(s1, rect))
    for c in corners:
        d = min(d, point_seg(c, s0, s1))
    return d


def free_of_copper(board, net, points, width, layer):
    """Is there room for the line between the points?

    The line may not come closer to the copper of another net than the
    clearance of the net, and it may not touch it at all.  The pads of
    the net itself are free: the line has to arrive at them.

    The answer is None when there is room, and the description of the
    copper that is in the way when there is not.
    """

    # The clearance of the net.  The rules live in the project file, not
    # in the board: the board holds only the name of the class.
    clearance = rule_of(board, net).get("clearance", 0.2)

    # the segments of the line, with the width and the layer of every one
    segs = segments_of(points, width, layer_name(layer))

    def crosses(rect, gap, lay):
        """Does the line come within the gap of the rectangle?

        The rectangle is (x0, y0, x1, y1).  Every piece of the line is
        thickened by the gap and by half of its own width, so the
        question is whether the line comes nearer to the rectangle than
        that.

        The distance is measured exactly, not in steps: the distance of
        the ends of the line to the rectangle and the distances of the
        corners of the rectangle to the line.  A line that goes over
        the corner of the rectangle comes close to it, but it does not
        touch it, and the rules checker says so too.

        Only the pieces of the line on the layer of the rectangle are
        of interest: the copper of the other layer is under it.
        """
        for (a, c, w, seg_layer) in segs:
            if seg_layer != lay:
                continue
            need = gap + w / 2
            if seg_rect_distance(a, c, rect) < need:
                return True
        return False

    # The pads of the other nets.  The clearance of a pad is its own
    # local clearance when it has one, and the clearance of the class
    # of its net otherwise.  The local clearance of a pad overrules the
    # clearance of the class, and the U11 has 0.15 millimetres on its
    # pins, because the pins are only half a millimetre apart.
    #
    # A pad is copper on every layer it is on, so a pad that is on both
    # copper layers is in the way of a line on either of them.
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net or not p.GetNetname():
                continue
            local = p.GetLocalClearance()
            gap = pcbnew.ToMM(local) if local else clearance
            # The box of the pad is taken from the board and not from
            # the size of the pad: a pad may lie at an angle, and the
            # size of it says nothing about where its corners are.
            bb = p.GetBoundingBox()
            rect = (mm(bb.GetLeft()), mm(bb.GetTop()),
                    mm(bb.GetRight()), mm(bb.GetBottom()))
            for pad_layer in ("F", "B"):
                if not p.IsOnLayer(pcbnew.F_Cu if pad_layer == "F"
                                  else pcbnew.B_Cu):
                    continue
                if crosses(rect, gap, pad_layer):
                    return (f"the pad {fp.GetReference()}.{p.GetNumber()}"
                            f" of the {p.GetNetname()} net is in the way")

    # the tracks of the other nets
    for t in board.GetTracks():
        if t.GetNetname() == net or t.GetNetname() == "GND":
            continue
        if t.GetClass() == "PCB_VIA":
            continue
        a, c = t.GetStart(), t.GetEnd()
        w = mm(t.GetWidth()) / 2
        ax, ay = mm(a.x), mm(a.y)
        ex, ey = mm(c.x), mm(c.y)
        track_layer = "F" if t.GetLayer() == pcbnew.F_Cu else "B"
        # the distance of the two segments: the line and the track.
        # Every piece of the line has its own width and its own layer,
        # and only the pieces on the layer of the track are of interest.
        for (s0, s1, sw, seg_layer) in segs:
            if seg_layer != track_layer:
                continue
            # the line may not cross the track of the other net
            if crosses_line(s0, s1, (ax, ay), (ex, ey)):
                return (f"the line crosses the track of the"
                        f" {t.GetNetname()} net")
            gap = sw / 2 + w + clearance
            d = min(point_seg((ax, ay), s0, s1),
                    point_seg((ex, ey), s0, s1),
                    point_seg(s0, (ax, ay), (ex, ey)),
                    point_seg(s1, (ax, ay), (ex, ey)))
            if d < gap:
                return (f"the track of the {t.GetNetname()} net is in"
                        f" the way")

    # The vias of the route.  A via goes through both copper layers, so
    # it has to keep away from the copper of the other nets on both.
    vias = vias_of(points, layer_name(layer))
    if vias:
        rule = rule_of(board, net)
        vdia = rule.get("via_diameter", 0.6)
        for (vx, vy) in vias:
            for fp in board.GetFootprints():
                for p in fp.Pads():
                    if p.GetNetname() == net or not p.GetNetname():
                        continue
                    if not p.IsOnLayer(pcbnew.F_Cu):
                        continue
                    local = p.GetLocalClearance()
                    gap = pcbnew.ToMM(local) if local else clearance
                    pos = p.GetPosition()
                    sz = p.GetSize()
                    hx, hy = mm(sz.x) / 2, mm(sz.y) / 2
                    px, py = mm(pos.x), mm(pos.y)
                    # the distance of the point and the rectangle
                    cx = min(max(vx, px - hx), px + hx)
                    cy = min(max(vy, py - hy), py + hy)
                    d = ((vx - cx) ** 2 + (vy - cy) ** 2) ** 0.5
                    if d < vdia / 2 + gap:
                        return (f"the via is in the way of the pad"
                                f" {fp.GetReference()}.{p.GetNumber()}"
                                f" of the {p.GetNetname()} net")
    return None


def drc():
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    with open(JSON) as f:
        return json.load(f)


def drc_of(net, d=None):
    """The errors of the board that belong to the net."""
    d = d if d is not None else drc()
    out = []
    for v in d.get("violations", []):
        for i in v.get("items", []):
            if f"[{net}]" in i.get("description", ""):
                out.append((v["type"], i.get("description", "")[:60]))
                break
    return out


def unconnected_of(net, d=None):
    """The pads of the net that are not connected."""
    d = d if d is not None else drc()
    out = set()
    for u in d.get("unconnected_items", []):
        for i in u.get("items", []):
            desc = i.get("description", "")
            if f"[{net}]" in desc:
                out.add(desc[:70])
    return out


def main():
    nets = list(ROUTES)
    if len(sys.argv) > 1:
        # every name on the command line, and the nets that are not on
        # it are left alone
        wanted = set(sys.argv[1:])
        unknown = wanted - set(ROUTES)
        if unknown:
            print(f"no route for the net {sorted(unknown)[0]!r}")
            return 1
        nets = [n for n in nets if n in wanted]
    if not nets:
        print("no route for that net")
        return 1

    b = pcbnew.LoadBoard(PCB)
    for net in nets:
        routes = snap_to_pads(b, net, ROUTES[net])
        bnet = b.FindNet(net)
        if bnet is None:
            print(f"the net {net} is not on the board")
            continue

        # is the route already there?
        # The nets in KEEP keep the copper of the V2, so only the
        # routes of the table have to be there.  The other nets are
        # drawn again from scratch, so the copper of the net has to be
        # exactly the copper of the table: a piece of an older route
        # would stay on the board for ever.
        if net in KEEP:
            if route_is_there(b, net, routes):
                print(f"the route of the {net} is already there")
                continue
        elif route_is_exactly_there(b, net, routes):
            print(f"the route of the {net} is already there")
            continue

        # The copper of the net has to be removed first: the route may
        # be a different one than the one that is there now.  The
        # removal is done by delall.py, in a process of its own,
        # because removing an item invalidates the wrapper of the board.
        # The whole copper of the net goes away at once: when it goes
        # away piece by piece, KiCad gives the copper that is left over
        # another name, and the new route then does not fit.
        # The nets in KEEP keep their copper: their route of the V2 is
        # good, and only a piece is added to it.
        #
        # The board of before is kept aside: when the route has no
        # room, the copper of the net is put back.  Otherwise the net
        # would stay without any line.
        backup = PCB + ".before"
        if net not in KEEP:
            shutil.copy(PCB, backup)
            env = {**os.environ,
                   "PYTHONPATH": os.environ.get("PYTHONPATH", "") + ":" + HERE}
            subprocess.run(
                [sys.executable, os.path.join(HERE, "delall.py"), net],
                capture_output=True, text=True, env=env, cwd=HERE)
        b = pcbnew.LoadBoard(PCB)
        bnet = b.FindNet(net)

        # Every route of the net is measured before it is drawn: the
        # line has to be free of the copper of the other nets.  The
        # check is done with the distance of the line to every pad and
        # to every track, so that a route that can not be drawn is not
        # drawn at all.
        blocked = None
        for (width, layer, points) in routes:
            blocked = free_of_copper(b, net, points, width, layer_of(layer))
            if blocked:
                break
        if blocked:
            print(f"    {blocked}")
            print(f"the route of the {net} has no room")
            if os.path.exists(backup):
                shutil.copy(backup, PCB)
                os.remove(backup)
                print("the copper of the net is put back")
            return 0

        segments = 0
        vias = 0
        for (width, layer, points) in routes:
            segs = segments_of(points, width, layer)
            for ((x0, y0), (x1, y1), w, seg_layer) in segs:
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pcbnew.VECTOR2I(iu(x0), iu(y0)))
                t.SetEnd(pcbnew.VECTOR2I(iu(x1), iu(y1)))
                t.SetWidth(iu(w))
                t.SetLayer(layer_of(seg_layer))
                t.SetNet(bnet)
                b.Add(t)
                segments += 1
            # the places where the line changes to the other copper
            rule = rule_of(b, net)
            vdia = rule.get("via_diameter", 0.6)
            vdrill = rule.get("via_drill", 0.3)
            for (vx, vy) in vias_of(points, layer):
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(pcbnew.VECTOR2I(iu(vx), iu(vy)))
                v.SetWidth(iu(vdia))
                v.SetDrill(iu(vdrill))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(bnet)
                b.Add(v)
                vias += 1
        # The zone of the ground has to be filled again: it still holds
        # the copper of the board of before, and the copper of the
        # route runs into it.  Without the new fill the guard sees the
        # errors of the stale zone and throws a good route away.
        filler = pcbnew.ZONE_FILLER(b)
        filler.Fill(list(b.Zones()))
        # the guard puts the board back when the route made it worse
        kept = safe_board.save(b, f"the route of the {net}")
        if os.path.exists(backup):
            os.remove(backup)
        if kept:
            print(f"the route of the {net} is drawn: {segments} segments,"
                  f" {vias} vias")
        else:
            print(f"the route of the {net} was thrown away by the guard")
    # the measurement.  It runs even when nothing was drawn: the state
    # of the board is what the caller wants to know.
    d = drc()
    for net in nets:
        err = drc_of(net, d)
        unc = unconnected_of(net, d)
        print()
        print(f"the net {net}")
        print(f"  {len(err)} errors")
        for (t, desc) in err[:6]:
            print(f"    [{t}] {desc}")
        print(f"  {len(unc)} items are not connected")
        for desc in sorted(unc)[:4]:
            print(f"    {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
