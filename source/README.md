# Sable Creek Hydro for Half-Life 2

The GoldSrc control room (see `../goldsrc`), rebuilt for Half-Life 2 with the same unit (250 kW Francis
turbine, 72-pole alternator, 480 V, 60 Hz, on a run-of-river intake), the same panels, controls and
names, and real numbers instead of counters.

## Playing it

Copy `out/sablecreek.bsp` to `Steam/steamapps/common/Half-Life 2/hl2/maps/` and type `map sablecreek` in
the console. The textures and sounds are packed inside the BSP, and no launch options are needed.

## Entities

The map has about 1,030 entities, and only 72 of them use network slots: the needles, switches, dials,
lamps, annunciator windows and sounds. All the plant logic (955 entities: `math_counter`, `math_remap`,
`logic_relay`, `logic_timer`, `logic_auto`) is server-only and uses no network slots. Half-Life 2 allows
2048 networked entities and 2048 server-only ones, so there's room to spare.

## The physics

The plant is a per-unit machine model, the kind used in hydro studies:

- **Runner:** Francis turbine torque falls with speed (stall torque 1.8 pu at full gate, runaway 160 %).
  The head is the river's: it rises and falls with the depth at the intake (12.2 m at 7.0 m), and power
  goes with it.
- **Water column:** the flow takes about a second to follow the gate (water starting time 1 s). Open the
  gate fast and the power dips before it rises; close it fast and it kicks up.
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
- **AVR:** PI control. Off line it holds 480 V; on line it holds 0.95 power factor lagging, as small hydro
  units on a distribution grid do. In MAN it tracks the knob, so switching to AUTO is bumpless. When 41
  opens, the manual setting goes back to the no-load field.
- **PLC governor:** PID speed control. The gate is limited to 25 % while starting, and the integrator waits
  at the speed-no-load gate until 90 % speed, so start-up overshoots only about 2 %. On a full load
  rejection the speed peaks around 126 % and comes back to speed-no-load without tripping. With the PLC off
  nothing catches it, and 12 overspeed trips at 140 %.
- **Auxiliaries:** the hydraulic pump runs on its pressure switch (on below 270 psi, off at 300) and the
  air compressor on its own (100 / 125 psi); you hear them start and stop. Bearings warm with speed and
  load over about a minute (52-60 C with cooling water); without it they head for 120 C, and without lube
  oil they wipe in seconds.
- **Sound:** the turbine's pitch follows its speed and its loudness the water through it; the water noise
  follows the flow; the generator hums louder with volts and load.
- **Light:** the ceiling troffers light the room (texture lights), with finer lightmaps on the panels.

## Controls

The cabinets and the spillway panel are laid out as in the GoldSrc map. These things are different:

| Control | Now |
|---|---|
| Meters | Switchboard meters with a 250-degree scale. The needles move smoothly to any value. |
| WICKET GATE LOWER / RAISE | Spring-return dials. Held, they move the gate 0.25 %/s for the first second, 2.5 %/s for the next two, then 10 %/s. Short taps trim the speed finely for synchronizing. |
| FIRING ANGLE | The knob's position is the firing angle: left stop 90 degrees (no field), right stop 0 degrees (the exciter's ceiling, 140 % field). Like every Source wheel, each new grab turns the other way. With the AVR on AUTO the knob follows the AVR, so switching back to MAN doesn't bump the field. |
| SYNCHROSCOPE | The pointer is the real phase angle. It turns at the slip (216 degrees a second per 1 % of speed off 100 %, at most one turn a second): clockwise when fast, anticlockwise when slow. The sync lamps are dark at 12 o'clock. |
| Spillway GATE dials | Turn clockwise, like the others. |

## Starting the unit

1. OIL PUMP, WATER PUMP, HYDRAULIC PUMP and AIR COMPRESSOR to RUN. Wait about 15 s for HYDRAULIC
   PRESS to reach 300 psi (the gate won't open below 230 psi).
2. BRAKES to RELEASE.
3. Either turn the PLC ON (it brings the unit to speed in about 20 s and settles it a hair fast about
   15 s later), or by hand: hold RAISE to about 25 % gate, and once speed passes 80 % hold LOWER back to
   about 15 %.
4. AVR to AUTO, then 41 FIELD BREAKER to CLOSE (it closes from 90 % speed). The field flashes and the
   volts come up to 480 V in a few seconds.
5. SYNCHRONIZING ON. Close 52G while the SYNC CHECK lamp is lit: phase within 10 degrees of 12 o'clock,
   speed within 0.33 % (0.2 Hz slip) and volts within 5 %. By hand, trim the speed with short taps on
   RAISE / LOWER until the pointer creeps. Each tap takes 15-20 s to show fully in the speed, so tap,
   wait, and tap again.
6. Load: with the PLC on, it opens the gate to pass the river and holds the depth at 7.0 m (never below
   17 % gate). By hand, hold RAISE. Watch the kW needle dip as the gate starts moving fast.

## Protection

Any trip shuts the wicket gate at once, opens 52G and 41, turns the PLC OFF and the AVR to MAN, and
turns the WICKET GATE TRIP handle to TRIP. Turn it back to RESET to reset; it trips again if the cause
is still there.

| Trip | Cause |
|---|---|
| 12 OVERSPEED | 140 % speed |
| 52G CLOSED OUT OF PHASE | 52G closed with the synchronizing switch off and not in phase (with it on, the sync check refuses the close and the handle springs back) |
| 32 REVERSE POWER | on line and motoring (the gate under speed-no-load) for 8 s |
| 40 LOSS OF FIELD | on line with the field under 60 %, or the rotor slipping poles |
| 59 GEN OVERVOLTAGE | off line at 115 % volts |
| 38 BRG TEMP HIGH-HIGH | bearing at 90 C (no lube oil wipes it in seconds, no cooling water cooks it in about a minute) |
| (lockout only) | hydraulic oil under 210 psi with the gate open; river under 4.75 m with the unit turning |

The annunciator has the GoldSrc map's 20 windows. Trips stay lit until the reset, alarms and status
follow their condition, and the horn sounds for 6 s on each new trip or alarm.

## How the logic works

`hydro.py` writes the plant as equations; `srclogic.py` compiles them into logic entities. Every state
variable is a `math_counter`. A `logic_timer` fires every 0.06 s (4 server ticks); its relay asks every
variable for its value (`GetValue`), and the values flow through `math_remap` nodes (one value: scale,
offset, clamp) and `math_counter` nodes (two values: add, subtract, multiply, divide) into the new
values, the needles (`SetPosition`), the sync lamps (`Alpha`) and the turbine pitch. A two-value node
takes its first value with `SetValueNoFire` and computes when the second arrives, so the compiler times
every node by its distance from the timer (Source runs one tick's outputs first-in first-out). Lamps,
windows, sounds and the handles the logic turns hang off 0/1 counters (`OnHitMax`, `OnHitMin`).

`srcsim.py` simulates those entities as the Source SDK code does: the event queue, the reverse order
of an output's actions, the relays, timers rounded to ticks, the buttons and wheels, 32-bit floats.
`python3 test_hydro.py` runs start-up by hand and by PLC, synchronizing (and the swing after it),
loading (and the water-hammer dip), the power factor on line, a trip and reset, a load rejection with the
PLC on, the out-of-phase close, the refused close and overspeed, and checks that every two-value node got
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
