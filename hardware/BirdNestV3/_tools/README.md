# The tools of the BirdNest V3 board

The scripts in this directory work on the board of the V3:
`../BirdNestV3.kicad_pcb`.

**Every script that writes the board overwrites the whole file.**  There
is no undo.  So before a script that changes the board, the board is
saved:

    cp ../BirdNestV3.kicad_pcb /tmp/board_before.kicad_pcb

The best board so far is saved in `/tmp/BirdNestV3_ISET82.kicad_pcb`:
82 violations, 43 unconnected, every error in the copper is gone.

## The scripts that are in use

| script | what it does |
|---|---|
| `safe_board.py` | **the guard of the board**: it measures the board before and after a change, and it puts the board back when the change made it worse.  The scripts that were thrown out use it, so they can not destroy the work. |
| `restore.py` | puts the copy of the board back.  The `repair.py` takes that copy before it starts. |
| `layout_v3.py` | places the parts: the proven slots of the V2, the new parts from `packed.json`, the mounting holes. `apply` writes the board. |
| `pack.py` | finds the room for the parts that are new in the V3.  It writes `packed.json`.  It reads the tracks of the V2 as obstacles, and it gives the parts with fine pads a room around themselves. |
| `refill.py` | fills the zones again.  It has to run after every change of the copper. |
| `route_one.py` | routes one net at a time and measures the board after every net.  A route that makes the board worse is thrown away. |
| `hand_routes.py` | the routes that are drawn by hand.  A route is measured before it is drawn: a route that does not fit is not drawn at all.  The points of a route that stand on a pad are moved onto the middle of that pad, because a line that stops a hair before the middle of a pad does not reach it. |
| `find_way.py` | looks for a way between two points on one copper.  The last argument is the room to keep from the other copper; a bigger room gives a shorter way that is farther away from the parts. |
| `delitem.py` | removes the tracks and the vias of a net, in a process of its own. |
| `net_rules.py` | shows the rules of the nets: the class, the width, the clearance. |
| `pad_room.py` | shows the room between the pads of the parts that are close to each other. |
| `room.py` | shows the free room around the pads of the nets that are not connected. |
| `u11_room.py` | shows the pins of the U11 and the copper around the package. |
| `survey.py` | shows the parts, the tracks, the holes and the errors of the board. |
| `parts_on_v2_tracks.py` | shows where the pads of the new parts stand over the tracks of the V2. |
| `compare_layouts.py` | compares the placement of the V2 and of the V3. |
| `dangling.py` | shows the tracks that hang loose. |
| `hermes-verify-routes.py` | checks the hand drawn routes and the guard of the board: the width may change, the route may change to the other copper through a via, the line may not cross a track of another net, the zone of the ground is filled again after the route, the script takes more than one net, and every kind of error of the copper counts in the guard.  It puts the board back afterwards.  Run it from this directory. |
| `hermes-verify-silk.py` | checks the cleaner of the silk screen: the file is sound, the cleaner finds the references that are in the way, every reference has a place, no reference lies over a pad after the move, and the copper of the board has no error.  It puts the board back afterwards.  Run it from this directory. |
| `fix_silk.py` | moves the reference of a part that lies over the copper of a pad.  Only the references that the rules checker names are moved, and the guard of the board has the last word.  Run it again and again: every run moves a few more. |
| `check_u11.py`, `check_v2.py`, `inspect_board.py`, `nets.py`, `map_ref.py` | the older tools for looking at the board. |

## The scripts that were thrown out

These scripts write the board too, and they are **not** to be run: they
were the attempts that did not work, and they are here only as the
record of what was tried.  They all go through `safe_board.py`, so the
board is put back when they make it worse.

| script | why it was thrown out |
|---|---|
| `maze.py`, `maze2.py`, `maze3.py` | the first routers.  They drew tracks over the copper of the other nets: the board ended with 253 violations instead of the 82 that it has now. |
| `maze4.py` | the router that the `route_one.py` uses.  It is the only router that is kept, but it is used through `route_one.py`, which measures the board after every net and throws away the routes that make the board worse. |
| `repair.py` | the loop that routed the nets again and again.  It made the board worse: 248 violations became 394. |
| `route.py`, `fix_overlaps.py`, `merge_tracks.py`, `drop_slivers.py` | the scripts that moved the copper around.  The moves broke the nets. |
| `fix_u11_escapes.py` | the attempt to lead the pins of the U11 out.  It is read only now. |
| `freeroute.py`, `prep_dsn.py` | the bridge to the freerouting.  The freerouting does not stop, and it does not write a stable session file. |
| `delnets.py` | the removal of the nets.  It removes too much. |
| `fix_drc.py`, `fix_netclasses.py` | the repairs of the rules.  They are done, the rules are in the project file. |

## The order of the work

1.  `pack.py`  -> the new `packed.json`
2.  `layout_v3.py apply`  -> the parts are on the board
3.  `route_one.py`  -> the routes, one net at a time
4.  `hand_routes.py`  -> the routes that are drawn by hand
5.  `refill.py`  -> the zones are filled again
6.  `kicad-cli pcb drc`  -> the measurement

The measurement is the only truth.  A route that is not measured is
not a route.
