# Sable Creek Hydro for Half-Life 2

The GoldSrc control room (see `../goldsrc`), rebuilt for Half-Life 2 with the same unit (250 kW Francis
turbine in an open flume, 72-pole alternator, 480 V, 60 Hz, run-of-river), the same panels, controls and
names, and real numbers instead of counters.

## Playing it

Copy `out/sablecreek.bsp` to `Steam/steamapps/common/Half-Life 2/hl2/maps/` and type `map sablecreek` in
the console. The textures and sounds are packed inside the BSP, and no launch options are needed.

## Entities and speed

The map has 1,695 entities, and only 162 of them use network slots: the needles, switches, dials,
pushbuttons, lamps, annunciator windows and sounds (107), and the 55 models that move with them. The 67 fixed
models are static props, which cost nothing. The plant logic (1,461 entities: `math_counter`,
`math_remap`, `logic_relay`, `logic_timer`, `logic_auto`, `logic_branch`) is server-only and uses none. Half-Life 2 allows
2048 of each kind. The room's detail is world geometry (`func_detail`), which costs nothing while playing.

What limits the logic is speed, not entity count. Each output the engine fires finds its target by
name, and that lookup compares the name against every named entity in the map. So the cost is events
times entities. The plant therefore runs as five loops, started on different server ticks so no two land on the same one:

| Loop | Every | Runs |
|---|---|---|
| fast | 0.03 s | gate travel, runner and water column, rotor speed and swing, phase, 52G closing, the speed, gate, kW, power factor, net head, frequency and synchroscope needles |
| medium | 0.12 s | gate commands (dials, governor, forebay level control), excitation and voltage regulator, protection and trips, brakes, the volts, field and firing-angle needles, sound pitch and loudness |
| slow | 0.24 s | river and spillway, pumps and compressor, bearings, stator winding, grid volts, their meters |
| annunciator, two halves | 0.24 s each (half a period after slow, two ticks apart) | twelve windows each: the alarm sequence, horn, ACK / RESET / TEST |

In all they handle about 22,000 events a second, at most about 540 in one server tick. Sine and cosine are short formulas instead of tables, sibling `math_remap`s
fed by the same value share one name (one event reaches them all), and node names are one to three
characters that usually differ in the first, which keeps each name comparison as short as possible.

## The physics

The plant is a per-unit machine model, the kind used in hydro studies:

- **Runner:** a vertical Francis runner in an open flume, 40 ft (12.2 m) of head. Its torque falls with
  speed (stall torque 1.8 pu at full gate, runaway 160 %). The head is the river's: 40 ft at the normal
  forebay level (23.0 ft), rising and falling with it, and the power goes with it.
- **Run-of-river:** no storage. The forebay is the river behind the diversion weir; its flow wanders between
  65 and 85 % of the unit's full-gate discharge (90 cfs). What the unit doesn't take goes through the
  spillway gate. On line in AUTO the governor is in forebay level control: it opens the wicket gates as the
  level rises, so the unit passes the river's flow.
- **Open flume:** the runner sits in an open concrete flume off the headrace, with no penstock and no
  scroll case. The water in the flume and draft tube still has a little momentum (a nonlinear inelastic
  water column as in the IEEE hydro turbine models, starting time 0.4 s; the turbine passes
  q = G sqrt(h)), so a fast gate opening makes the power dip slightly before it rises. A fast closure only
  piles the water up in the flume, a surge of about 2.4 ft, not water hammer. The NET HEAD meter on the
  auxiliaries panel shows the head at the runner (0-60 ft).
- **Rotor:** mechanical starting time 6 s, friction and windage, air brakes. Off line the speed settles
  where the gate's torque meets the losses (speed-no-load at 15 % gate). Coasting down with the gate shut
  takes minutes, so the brakes matter.
- **On line:** the rotor is tied to the grid through the generator's reactance. The load angle sets the
  kilowatts and the field sets the vars. Closing 52G makes the rotor swing into step (the kW meter rocks
  for a second or two), and losing too much field makes it slip poles.
- **Generator volts:** off line they follow the open-circuit curve (saturating above rated field) times
  speed. On line the grid holds them, raised slightly by the vars through the step-up transformer.
- **Exciter:** static and fed from the generator's own terminals, so its ceiling is 1.4 times the volts.
  With no volts it can't build the field: closing 41 flashes the field from the station battery until
  the volts pass 40 %. The field current follows the exciter through the winding (1.5 s).
- **Voltage regulator:** PI control. Off line it holds 480 V; on line it holds 0.95 power factor lagging, as small hydro
  units on a distribution grid do. In MAN it tracks the knob, so switching to AUTO is bumpless. When 41
  opens, the manual setting goes back to the no-load field.
- **Governor:** digital PID speed control. The gate is limited to 25 % while starting, and the integrator waits
  at the speed-no-load gate until 90 % speed, so start-up overshoots only about 2 %. On a full load
  rejection the speed peaks around 118 % and comes back to speed-no-load without tripping. With the governor in MAN
  nothing catches it, and 12 overspeed trips at 140 %.
- **Auxiliaries:** in AUTO the governor oil pump runs on its pressure switch (on below 270 psi, off at 300)
  and the air compressor on its own (100 / 125 psi); you hear them start and stop. Bearings warm with speed and
  load over about a minute (52-60 C with cooling water); without it they head for 120 C, and without lube
  oil they wipe in seconds.
- **Wicket gate timing:** the servomotors stroke the gates fully in 10 s opening and 5 s closing. A trip
  closes them at that rate (the shutdown solenoid), not instantly, so a trip at load lets the unit overspeed
  to about 111 % before the water is off.
- **Shutdowns:** an electrical trip (or the 86U handle) is an immediate shutdown: 52G and 41 open at once.
  A mechanical trip is a quick shutdown: 52G stays closed while the gates close, so the grid holds the
  speed, and 52G and 41 open as the gate passes speed-no-load; no overspeed.
- **Closing 52G unsupervised:** with 25 SYNC off nothing checks the close. Within 45 deg the breaker holds
  and the rotor is wrenched into step (the kW swings by hundreds); further out, or with no field, the
  inrush trips 50.
- **Grid:** stiff at 60 Hz, but its volts wander between 476 and 486 V. Off line the AVR matches them for
  synchronizing; on line in MAN the vars and power factor drift as they move.
- **Stator winding:** heats with the square of the current (60 C rise at rated 316 A, four minutes' time
  constant): 93 C at rated load, alarm at 105 C, trip at 120 C.
- **Sound:** the turbine's pitch follows its speed and its loudness the water through it; the water noise
  follows the flow; the generator hums louder with volts and load. They update 8 times a second.
- **Light:** the ceiling troffers light the room (texture lights), with finer lightmaps on the panels.

## Controls

The three cabinets are 50 wide and 94 high (37 x 70 in), narrower and lower than the GoldSrc map's, so the
devices fill the doors down to the vents and the top meters are at eye height. Every panel uses the same
columns: four for meters and breaker switches, five for a row of switches and dials.

| Panel | Top to bottom |
|---|---|
| CP-1 generator control | eight meters; 25 SYNC, 52G, 41 and 86U with their lamps under them |
| CP-2 annunciator | the annunciator and its ACK / RESET / TEST buttons; GATE POS, GEN FREQ, BUS FREQ, FIELD AMPS; GOV MODE, WICKET GATE LOWER / RAISE, AVR MODE, FIRING ANGLE in one row |
| CP-3 auxiliaries | eight meters; LUBE OIL PUMP, CW PUMP, HPU PUMP, AIR COMP, BRAKES |

The devices in detail:

| Control | Now |
|---|---|
| Meters | 250-degree switchboard meters: square flange, round bezel, pointer with a counterweight; each needle's speed is set a little above the fastest its quantity normally moves, so it sweeps instead of ticking along in steps; slow needles start where they read. |
| CP-1 meters | TURBINE RPM, GEN VOLTS, GEN AMPS, KW; EXC FIRING ANGLE, POWER FACTOR, GRID VOLTS, SYNCHROSCOPE (sync lamps above it; 25 PERM under the 25 SYNC switch). GRID VOLTS is the 480 V bus the utility feeds; it wanders between 476 and 486 V. BUS FREQ is the grid's 60 Hz. GEN AMPS is apparent power over volts, \|S\| by alpha-max-plus-beta-min (within 4 %). |
| Control switches | All breaker-type (SB style), spring return: the L handle hangs at normal. One press of E anywhere on the switch works it: an invisible button over the plate and handle asks a `logic_branch` that holds the switch's state, and the handle turns the way that changes it (right when off, left when on: 0.15 s over, 0.25 s held, 0.15 s back). So E on 52G closes it when it is open and trips it when it is closed. The state latches in the logic and shows in the target window (a model skin the logic sets): red closed / running / ON / AUTO / locked out, green otherwise. A protective trip changes the targets, not the handles. |
| 52G, 41 | TRIP / CLOSE. A close is refused without the sync check (52G) or below 90 % speed (41). |
| 25 SYNC | OFF / ON. |
| 86U | RESET / TRIP, red handle. |
| GOV MODE, AVR MODE | MAN / AUTO. A trip drops both to MAN; AUTO is blocked until 86U is reset. |
| LUBE OIL PUMP, CW PUMP | STOP / START. |
| HPU PUMP, AIR COMP | OFF / AUTO (they run on their pressure switches). |
| BRAKES (CP-3) | RELEASE / APPLY; the target is red with APPLY selected (as at the start). The brakes go on only below 30 % speed and with air. |
| GATE MODE (SP-1) | MAN / AUTO for the spill gate; it starts in AUTO. |
| CP-2 meters | GATE POS by GOV MODE, GEN FREQ, BUS FREQ, FIELD AMPS by AVR MODE. |
| CP-3 meters | LUBE OIL PRESS, CW FLOW, THRUST BRG TEMP, SHAFT VIB; HPU PRESS, BRAKE AIR PRESS, NET HEAD, STATOR TEMP. |
| SP-1 meters | FOREBAY LEVEL 0-35 ft (23.0 normal, alarms at 24.6 HI and 20.5 LO, bank full 29.5), INFLOW in cfs, spill GATE POS 0-4 ft. In AUTO the spill gate opens above 24.6 ft and closes below 23.8 ft. |
| ACK / RESET / TEST | Pushbuttons under GOV MODE and AVR MODE. |
| WICKET GATE LOWER / RAISE | Spring-return. Held: 0.25 %/s for 1 s, 2.5 %/s for 2 s, then 10 %/s. |
| FIRING ANGLE knob | Position = firing angle, 90 deg (left stop) to 0 deg (right stop, 140 % field). Each new grab reverses direction (Source wheel). Tracks the AVR in AUTO for a bumpless transfer. |
| SYNCHROSCOPE | Real phase angle; 216 deg/s per 1 % slip, max 1 rev/s. Sync lamps dark at 12 o'clock. |
| Hit areas | Each control has an invisible player-clip box over its plate (a switch's reaches down over its handle), and a clip layer in front of each panel has a hole over each control. E takes the control under the crosshair; between controls it does nothing. |
| Sizes | Meters 8.6 units square (6.5 in); switch and dial plates 6.7 (5 in); lamps and pushbuttons 3.6 (2.7 in); annunciator windows 5.9 x 4.1. |

## Nameplates and terms

IEEE C37.2 device numbers for relays and breakers (12, 25, 32, 38, 39, 40, 41, 52G, 59, 86U). Cabinets
CP-1 (generator control), CP-2 (annunciator), CP-3 (auxiliaries), SP-1 (spillway gate). HPU = governor
hydraulic power unit, CW = cooling water, SNL = speed-no-load, OOP = out of phase, LOF = loss of field,
OV = overvoltage. Field current reads 0-60 A (50 A at rated no-load field). Units are US practice: ft, cfs,
psi, mils peak to peak; bearing temperatures in deg C.

The wording follows the Bureau of Reclamation's FIST manuals (2-3 governors, 3-14 excitation, 4-7
commissioning) and the ESHA small hydro guide:

| Term | Meaning |
|---|---|
| Run-of-river | No storage: the unit generates as the river provides and stops below its minimum flow. |
| Open flume | The runner sits in an open flume instead of a penstock and scroll case; a low-head setting. |
| Forebay, tailwater | The water levels above and below the unit; net head is their difference less the losses. |
| Trashracks, headgate, draft tube, tailrace | The water passage, intake to river. |
| Wicket gates | The adjustable gates round the runner (guide vanes in European texts), moved by servomotors through the shift ring; shear pins protect the linkage. |
| Speed-no-load (SNL) | The gate opening that holds rated speed off line (15 % here). |
| Speed adjustment, gate limit, speed droop | A governor's operator settings: the speed (or load) setpoint, the stop on gate travel, and the speed change per gate travel. |
| Forebay level control | Governor mode that sets the gate to hold the forebay level (GOV MODE AUTO on line). |
| HPU | Governor hydraulic power unit: sump, pumps and accumulator. |
| AVR, manual | Voltage regulator modes: automatic (terminal volts) and manual (here an open-loop firing angle). |
| Field flashing | Building the field from the station battery until a bus-fed static exciter can supply itself. |
| Lockout (86) | The relay a trip operates; hand reset. |
| Rough zone | The part-gate range where the draft tube vortex shakes a Francis unit (25-50 % gate here). |

## Starting the unit

1. LUBE OIL PUMP START, CW PUMP START, HPU PUMP AUTO, AIR COMP AUTO. HPU PRESS to 300 psi in about 15 s (gate
   blocked below 230 psi).
2. BRAKES RELEASE.
3. GOV MODE AUTO: 90 % speed in about 20 s, settles slightly fast. GOV MODE MAN: RAISE to 25 % gate,
   LOWER to about 15 % past 80 % speed.
4. AVR MODE AUTO, 41 CLOSE (permissive at 90 % speed). Field flashes, 480 V in a few seconds.
5. 25 SYNC ON. 52G CLOSE with 25 PERM lit: within 10 deg, 0.33 % slip (0.2 Hz), 5 % volts. In MAN, trim
   with short taps; each tap takes 15-20 s to show in the speed.
6. Load: GOV AUTO (forebay level control) opens the gate to pass the river and holds FOREBAY LEVEL at
   23.0 ft (17 % gate minimum). In MAN,
   hold RAISE; the kW dips as the gate starts moving fast.

## Protection

Every trip operates the 86U lockout (target red), closes the wicket gates at the servomotor rate and drops
GOV and AVR to MAN. RESET on 86U resets it; it trips again if the cause remains.

| Trip | Cause | Shutdown |
|---|---|---|
| 86U handle to TRIP | by hand | immediate |
| 50 GEN INST OVERCURRENT | 52G closed with 25 SYNC off, more than 45 deg out or with no field | immediate |
| 40 LOSS OF FIELD | on line, field under 60 %, or pole slip | immediate |
| 32 REVERSE POWER | on line, gate under SNL for 8 s | immediate |
| 59 GEN OVERVOLTAGE | off line, 115 % volts | immediate |
| 12 OVERSPEED | 140 % speed | immediate |
| 38 THR BRG TEMP HI-HI | 90 C (no lube oil: seconds; no CW: about a minute) | quick |
| 49 STATOR TEMP HI-HI | 120 C | quick |
| 63Q HPU PRESS LO-LO | under 210 psi with the gate open | quick |
| 71 FOREBAY LEVEL LO-LO | under 15.6 ft with the unit turning | quick |

Immediate: 52G and 41 open at once. Quick: they open as the gate passes speed-no-load.

Annunciator: 24 backlit windows (4.4 x 3.1 in each) in four rows of six (electrical trips, mechanical trips, alarms, levels and
status), red for trips, amber for alarms, white for status, legends with their IEEE C37.2 device numbers
(63Q oil pressure, 63A air pressure, 71 level, 80 flow). ISA-18.1 manual reset: a new alarm flashes its
window and sounds the horn; ACK makes it steady and silences the horn; RESET clears windows whose condition
has cleared (trip targets stay until 86U is reset); TEST lights every window. SPILL GATE OPEN, BRAKES
APPLIED, GOV IN MANUAL and AVR IN MANUAL are status windows (no flash, no horn). Alarms standing at map load
start acknowledged.

## The room

The GoldSrc map's room: the three cabinets, the spillway panel, door, extinguisher, clock, desk and chair.
Its surfaces are drawn at 24-32 texels a unit: painted concrete block in running bond with tooled joints, a
darker dado five courses high under a stripe, 12 in vinyl tile, and 2 x 4 ft acoustic tile in a white grid.
The door is a 36 x 84 in hollow metal door with a wire-glass lite and a kick plate in a steel frame. The
extinguisher, clock, desk, chair, door lever and hinges are studio models (`srcroom.py`), with player-clip
boxes round them. Floor, walls and ceiling have their own surface properties (footsteps).

The cabinets are built, not painted: a frame flush with each door and a 0.3 gap round it with a dark
gasket, black joints between sections, two barrel hinges and a latch per door, stamped vents with real
slats, a top cap and a plinth. Control switches have black engraved escutcheons, their nameplates above them; the
dials have black plates too, engraved with a rest mark, stop and arrow (LOWER / RAISE) or the 90-0 deg
scale (FIRING ANGLE); the annunciator has a raised frame and a grid between its
windows; nameplates are raised laminate plates. Door art is 16 texels per unit.

The panel hardware is studio models (`srcparts.py`): meter cases, pointers, breaker control switches
(escutcheon, target flag, L handle), instrument knobs (aluminium skirt and cap, fluted black body) and
their engraved plates, pushbutton caps and bezels, lamp bezels, hinges and
latches. Fixed parts are `prop_static`. A moving part is a `prop_dynamic` parented to the brush entity
that moves; that entity is still there for the player to use, but it isn't drawn (`rendermode 10`). On
the spillway panel, which faces into the room from the wall, each model's angles are its parent's turned
90 degrees.

## How the logic works

`hydro.py` writes the plant as equations; `srclogic.py` compiles them into logic entities. Every state
variable is a `math_counter`. Each loop's `logic_timer` fires its relay, which asks every variable of that
loop for its value (`GetValue`), and the values flow through `math_remap` nodes (one value: scale,
offset, clamp) and `math_counter` nodes (two values: add, subtract, multiply, divide) into the new
values, the needles (`SetPosition`), the sync lamps (`Alpha`) and the turbine pitch. A two-value node
takes its first value with `SetValueNoFire` and computes when the second arrives, so the compiler times
every node by its distance from the timer (Source runs one tick's outputs first-in first-out). Lamps,
windows, sounds and the handles the logic turns hang off 0/1 counters (`OnHitMax`, `OnHitMin`). A loop
reads another loop's variables through mirrors: the original's `OutValue` sets the copy with
`SetValueNoFire`, because `GetValue` answers every reader of a variable at once.

`srcsim.py` simulates those entities as the Source SDK code does: the event queue, the reverse order
of an output's actions, the relays, timers rounded to ticks, the buttons and wheels, 32-bit floats.
`python3 test_hydro.py` runs start-up by hand and by the governor, synchronizing (and the swing after it),
loading (and the water-hammer dip), the power factor on line, a trip and reset, a load rejection with the
governor in AUTO, the out-of-phase close, the refused close and overspeed, and checks that every two-value node got
its values in order on every tick.

## Building

`python3 build.py` writes `out/sablecreek.vmf`. With `GBSP` set to a folder holding gbsp, gvis and grad
(github.com/drwxor/gbsp, an open-source Source compiler: `cargo build -r`), it also compiles the map and
packs the materials, models and sounds into `out/sablecreek.bsp`. The room, cabinets and panel art come
from `../goldsrc/build.py`.

There is no model compiler here, so `srcmdl.py` writes the model files itself: `.mdl` (version 48),
`.vvd` and `.dx90/.dx80/.sw.vtx`. They are rigid props, laid out the way studiomdl lays out a
`$staticprop`: one bone, a hitbox set, a one-frame idle sequence, one body part, one mesh per material,
triangle lists wound clockwise. `read_model()` walks them back the way the engine does; srctools and
gbsp's own reader load them too.

Brush rules for Source compilers, learned the hard way:

- Every brush piece must be at least 1 cubic unit; the BSP drops smaller pieces.
- No edge may be 0.2 units or shorter; the face is dropped. So no two parallel edges on a door may be
  closer than that. Raised plates snap to a 0.25 grid.
- Thin slabs must not be crossed by other brushes' planes. That's why the meters sit in rectangular cases
  and the needles are 1 unit deep.
- In a brush entity, the compiler fills empty cells under 1 cubic unit. A small polygon with axial sides
  then comes out as its bounding box, so round knobs and lenses are 12-gons with no axial side, one brush
  each (the knob's pointer is texture art). They run deep into the cabinet, where they're hidden, and the
  hit areas are squares.
- A world brush with slanted sides must not touch a door's face: it cuts the face into pieces along its
  sides, and a hairline piece next to a nameplate's edge gets dropped, leaving a crack. The lamps' dark
  lenses therefore stand 0.1 off the door, inside their bezels.
- Two raised parts' edges must not run parallel a hair apart on a door (a meter's case and its nameplate):
  the strip of door between them is a sliver the compiler drops. A meter's nameplate is either exactly as
  wide as its case or half a unit inside it on each side. `holes2`-style scanning of the compiled doors
  (every sample point covered by a front-facing triangle) catches both kinds.

After compiling, `build.py` replaces gbsp's per-face triangle lists ("primitives"). The game reserves
(corners - 2) x 3 indices for each face, and gbsp leaves zero-area triangles out of a face with a repeated
corner. One short list shifts every index after it, and the whole map then draws with the wrong
triangles and textures. Convex faces get no list (the game draws a fan); the few non-convex faces gbsp
merges get an ear-clipped list of exactly corners - 2 triangles.

Before that, it fixes T-junctions as vbsp does. Where a corner of one world face lies part way along an
edge of a neighbour on the same plane, the corner is added to the neighbour's outline; otherwise the two
triangle edges don't meet exactly and the game shows a hairline crack of sparkles. Faces get new edges
and a rebuilt surfedge list, and the per-corner normal indices are rebuilt to match.
