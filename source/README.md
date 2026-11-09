# Sable Creek Hydro for Half-Life 2

The GoldSrc control room (see `../goldsrc`), rebuilt for Half-Life 2 with the same unit (250 kW Francis
turbine, 72-pole alternator, 480 V, 60 Hz, on a run-of-river intake), the same panels, controls and
names, and real numbers instead of counters.

## Playing it

Copy `out/sablecreek.bsp` to `Steam/steamapps/common/Half-Life 2/hl2/maps/` and type `map sablecreek` in
the console. The textures and sounds are packed inside the BSP, and no launch options are needed.

## Entities and speed

The map has 1,263 entities, and only 76 of them use network slots: the needles, switches, dials,
pushbuttons, lamps, annunciator windows and sounds. The plant logic (1,182 entities: `math_counter`,
`math_remap`, `logic_relay`, `logic_timer`, `logic_auto`) is server-only and uses none. Half-Life 2 allows
2048 of each kind. The room's detail is world geometry (`func_detail`), which costs nothing while playing.

What limits the logic is speed, not entity count. Each output the engine fires finds its target by
name, and that lookup compares the name against every named entity in the map. So the cost is events
times entities. The plant therefore runs as four loops, started on different server ticks so no two land on the same one:

| Loop | Every | Runs |
|---|---|---|
| fast | 0.03 s | gate travel, runner and water column, rotor speed and swing, phase, 52G closing, the speed, gate, kW, power factor, net head, frequency and synchroscope needles |
| medium | 0.12 s | gate commands (dials, governor, headwater control), excitation and voltage regulator, protection and trips, brakes, the volts, field and firing-angle needles, sound pitch and loudness |
| slow | 0.24 s | river and spillway, pumps and compressor, bearings, their meters |
| annunciator | 0.24 s (half a period after slow) | the 20 windows' alarm sequence, horn, ACK / RESET / TEST |

In all they handle about 18,000 events a second, at most about 640 in one server tick. Sine and cosine are short formulas instead of tables, sibling `math_remap`s
fed by the same value share one name (one event reaches them all), and node names are one to three
characters that usually differ in the first, which keeps each name comparison as short as possible.

## The physics

The plant is a per-unit machine model, the kind used in hydro studies:

- **Runner:** a vertical Francis runner in an open flume, 40 ft (12.2 m) of head. Its torque falls with
  speed (stall torque 1.8 pu at full gate, runaway 160 %). The head is the river's: 40 ft at the normal
  7.0 m depth, rising and falling with it, and the power goes with it.
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
- **Sound:** the turbine's pitch follows its speed and its loudness the water through it; the water noise
  follows the flow; the generator hums louder with volts and load. They update 8 times a second.
- **Light:** the ceiling troffers light the room (texture lights), with finer lightmaps on the panels.

## Controls

The cabinets and the spillway panel are laid out as in the GoldSrc map. These things are different:

| Control | Now |
|---|---|
| Meters | 250-degree switchboard meters; needle speed matched to its loop's update rate. |
| ACK / RESET / TEST | Pushbuttons under GOV MODE and AVR MODE. |
| WICKET GATE LOWER / RAISE | Spring-return. Held: 0.25 %/s for 1 s, 2.5 %/s for 2 s, then 10 %/s. |
| FIRING ANGLE knob | Position = firing angle, 90 deg (left stop) to 0 deg (right stop, 140 % field). Each new grab reverses direction (Source wheel). Tracks the AVR in AUTO for a bumpless transfer. |
| SYNCHROSCOPE | Real phase angle; 216 deg/s per 1 % slip, max 1 rev/s. Sync lamps dark at 12 o'clock. |
| Hit areas | Each control has an invisible player-clip disc over its plate, and a clip layer in front of each panel has a hole over each control. E takes the control under the crosshair; between controls it does nothing. |

## Nameplates

IEEE C37.2 device numbers for relays and breakers (12, 25, 32, 38, 39, 40, 41, 52G, 59, 86U). Cabinets
CP-1 (generator control), CP-2 (annunciator), CP-3 (auxiliaries), SP-1 (spillway gate). HPU = governor
hydraulic power unit, CW = cooling water, HW = headwater, SNL = speed-no-load, OOP = out of phase,
LOF = loss of field, OV = overvoltage. Field current reads 0-60 A (50 A at rated no-load field).

## Starting the unit

1. LUBE OIL PUMP ON, CW PUMP ON, HPU PUMP AUTO, AIR COMP AUTO. HPU PRESS to 300 psi in about 15 s (gate
   blocked below 230 psi).
2. BRAKES RELEASE.
3. GOV MODE AUTO: 90 % speed in about 20 s, settles slightly fast. GOV MODE MAN: RAISE to 25 % gate,
   LOWER to about 15 % past 80 % speed.
4. AVR MODE AUTO, 41 CLOSE (permissive at 90 % speed). Field flashes, 480 V in a few seconds.
5. 25 SYNC ON. 52G CLOSE with 25 PERM lit: within 10 deg, 0.33 % slip (0.2 Hz), 5 % volts. In MAN, trim
   with short taps; each tap takes 15-20 s to show in the speed.
6. Load: GOV AUTO opens the gate to pass the river and holds HW at 7.0 m (17 % gate minimum). In MAN,
   hold RAISE; the kW dips as the gate starts moving fast.

## Protection

A trip operates 86U: wicket gate shut, 52G and 41 open, GOV and AVR to MAN, 86U handle to TRIP. Turning
the handle to TRIP trips the unit. RESET it to reset; it trips again if the cause remains.

| Trip | Cause |
|---|---|
| 12 OVERSPEED | 140 % speed |
| 52G OOP CLOSE | 52G closed with 25 SYNC off and out of phase (with 25 on, the close is refused) |
| 32 REV PWR | on line, gate under SNL for 8 s |
| 40 LOF | on line, field under 60 %, or pole slip |
| 59 OV | off line, 115 % volts |
| 38 BRG TEMP HH | 90 C (no lube oil: seconds; no CW: about a minute) |
| (86U only) | HPU under 210 psi with the gate open; HW under 4.75 m with the unit turning |

Annunciator: 20 windows, ISA-18.1 manual reset. New alarm: window flashes, horn, relay click. ACK: steady,
horn off. RESET: clears windows whose condition has cleared (trip targets stay until 86U is reset).
TEST: all windows on. BRAKES APPLIED, SPILL GATE OPEN, GOV IN MAN and AVR IN MAN are status windows (no
flash, no horn). Alarms standing at map load start acknowledged.

## The room

The GoldSrc map's room: the three cabinets, the spillway panel, door, extinguisher, clock, desk and chair.

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
packs the materials and sounds into `out/sablecreek.bsp`. The room, cabinets and panel art come from
`../goldsrc/build.py`.

Brush rules for Source compilers, learned the hard way: every brush must be at least 1 cubic unit (the
BSP drops smaller pieces), no edge may be 0.2 units or shorter (the face is dropped), and thin slabs
must not be crossed by other brushes' planes. That's why the meters sit in rectangular cases and the
needles are 1 unit deep.

After compiling, `build.py` drops gbsp's per-face triangle lists ("primitives"), so the game draws every
face as a fan of its own outline. The game reserves (corners - 2) x 3 indices for each face, and gbsp
leaves zero-area triangles out of a face with a repeated corner. One short list shifts every index after
it, and the whole map then draws with the wrong triangles and textures.
