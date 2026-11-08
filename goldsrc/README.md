# Sable Creek Hydro for Half-Life (GoldSrc)

The same plant as the web simulator, as a map for plain Half-Life: no mod, no DLL,
no scripting. The physics is faked with stock `hl.dll` entities used as variables.
There is no pond: the plant takes its water straight out of the river, which is about 7 m deep at the
intake, so it has to pass whatever the river brings, and the river's flow rises and falls by itself.
The unit is run by hand from 17 controls, with round gauges, pistol-grip control switches and
spring-return dials.

## Controls

The left cabinet runs the unit, the middle one is the annunciator with the generator and station
frequency meters and the PLC and AVR breakers, and the right one holds the auxiliary pumps and their
gauges. On every cabinet the gauges are at the top and the breakers and dials in a band across the
middle. The spillway gate has its own panel on the left wall, beside the fire extinguisher.

| Cabinet | Control | What it does |
|---|---|---|
| Left | WICKET GATE TRIP (red, yellow plate) | The emergency stop: closes the gate fast and opens 41 and 52G. Protection turns it to TRIP by itself; turning it back to NORMAL resets (it trips again if the cause is still there). |
| Left | SYNCHROSCOPE | Shows the phase between the generator and the grid, and puts the sync check (25) in service. The phase is there whether the switch is on or not, while the field is on and the unit is within 5 % of 60 Hz; the switch only shows it (pointer and sync lamps). The phase turns at the slip: anticlockwise (SLOW) when the unit is slower than the grid, clockwise (FAST) when faster, quicker the further off. At exactly 100 % speed it stands still wherever it is. The sync lamps are dark at 12 o'clock and brightest at 6. The green SYNC OK lamp lights while a close would be allowed: phase in the green sector, speed at 100 % and volts within 5 % (456–504 V). |
| Left | 52G SYNC BREAKER | Closes the generator onto the grid, on the real phase. In phase (what SYNC OK shows) it closes, switch on or off. Out of phase with the synchroscope on, the sync check refuses and the handle springs back; with the synchroscope off nothing stops it and the unit trips as out of phase. Once closed the unit is locked to the grid and the phase stops. |
| Left | 41 FIELD BREAKER | Connects the thyristor exciter. Opening it lets the field decay. |
| Left | FIRING ANGLE dial | Sets the field (manual excitation). Off line it sets the voltage; on line it sets the reactive power, shown on the POWER FACTOR meter. The FIRING ANGLE gauge above shows the thyristor angle: field goes as cos α, so 90° is no field, about 34° is rated field and 0° is full field. |
| Left | WICKET GATE LOWER and RAISE dials | Hold USE on RAISE to open the gate, on LOWER to close it: 1 % every 0.1 s while held. They are spring-return: let go and the dial springs back to 12 o'clock and the gate stops. |
| Left | BRAKES dial | APPLY / RELEASE. Apply them below 30 % speed when stopping. |
| Middle | PLC | ON: the PLC runs the gate: it brings the unit up to speed once the brakes are released, and on line it holds the river at 7.0 m deep at the intake, so the unit follows the river's flow. |
| Middle | AVR | AUTO: the AVR runs the field: 480 V off line, slightly lagging on line. |
| Right | LUBE OIL PUMP | Bearing lube oil. Turning the unit without it wipes the bearings in seconds (trip). |
| Right | COOLING WATER PUMP | Bearing and generator cooling. Without it the bearings heat up in about a minute (trip). |
| Right | SERVO OIL PUMP | Charges the gate servo accumulator. Every gate movement uses oil; below 220 psi the gate trips. |
| Right | AIR COMPRESSOR | Brake air. The brakes are spring-applied and need 50 psi to stay released. |
| Spillway | CONTROL (AUTO / MANUAL) | AUTO: the spillway gate opens when the river is deeper than 7.5 m and still rising, and closes below 7.25 m (with the PLC on, on line, it gives the water to the unit first). MANUAL: the gate only moves on the dials. |
| Spillway | GATE LOWER and RAISE dials | In MANUAL, hold to move the spillway gate 0.15 m a second (it opens 1.2 m). Spring-return, like the wicket gate dials. |

The spillway panel also carries the RIVER DEPTH (at the intake, 0–10 m), RIVER FLOW and SPILL GATE gauges.
The river's flow wanders between 65 and 85 % of the turbine's full-gate discharge (58–77 cfs; full gate
is 90 cfs), a step of 5 % every 32 s, so a cycle takes about 6½ minutes. When the plant and the spillway
take more than the river brings, it gets shallower (below 4.75 m the intake draws air and the unit
trips); when they take less it gets deeper, up to 9.0 m, bank full. Its dials turn anticlockwise:
a momentary button on that wall can only roll that way.

The POWER FACTOR meter (left cabinet, where the kilovar meter was) reads cos φ with φ = atan(Q / P):
1 at the top, LEAD to the left, LAG to the right, down to 0.5 each way. Q follows the field
(5 kvar per 1 % above rated field), and P is taken from the load band (below 30 % gate, 30–54 %, 55 %
and up), so the same field gives a lower power factor at light load.

### Starting by hand

1. Right cabinet: start the lube oil pump, the cooling water pump, the servo oil pump and the air compressor.
   Wait for servo oil and brake air to come up (the SERVO OIL and BRAKE AIR windows go dark).
2. Left cabinet: BRAKES dial to RELEASE.
3. Hold RAISE to open the wicket gate to about 25 %. As speed passes 80 %, hold LOWER to bring it
   back to 15 % (speed-no-load): the unit settles at 100 rpm. Each 1 % of gate around there moves the speed about 5 %
   (14 % gives 94 rpm, 16 % gives 104). Leaving the gate open overspeeds it (trip at 140 %).
4. Close 41 and raise the field with the firing-angle dial until GEN VOLTS reads 480.
5. SYNCHROSCOPE on. While the speed is still settling the pointer spins (SLOW below 100 %, FAST
   above); at 100 % it stands still. To bring it round to 12 o'clock, nudge the speed: tap RAISE, and
   when the speed reaches 101 % and the pointer starts to turn clockwise, tap LOWER; the speed comes
   back to 100 % and the pointer stops, about 25° further on (LOWER first turns it back the other way).
   Wait longer at 101 % to move it further. Close 52G while the green SYNC OK lamp is lit (pointer in
   the green, speed and volts matched). If it isn't, the close is refused and nothing trips.
6. Open the gate to load the unit (about 190 kW at 60 % gate). Keep it above 13 %, or the reverse-power
   relay opens 52G. Keep the field up, or loss of field trips 52G.

To stop: close the gate to 15 %, turn 52G to TRIP, open 41, close the gate, and apply the brakes below 30 %.
With the PLC ON and the AVR on AUTO (middle cabinet), steps 3 and 4 happen by themselves, and the PLC
holds the unit a hair fast, so the phase creeps clockwise (a turn in 11 s) and you only wait for 12 o'clock.

## How the "math" works

| Idea | Entities |
|---|---|
| Integer variable | One `game_counter` per value something listens for, all with the same name. A `trigger_relay` sends USE_ON (+1) or USE_OFF (−1); each counter fires `<var>_eq<v>` when the value lands on its number. |
| True/false flag | `env_global` state (and its opposite `n<flag>`), read by `multisource` masters. `env_global` "Set Initial State" seeds them at spawn. |
| Rule (if A and B then do X) | A chain of `game_counter_set` entities, each locked by a `multisource` master. Rules with the same leading conditions share links. |
| Clock | Two `multi_manager`s that trigger each other every 0.05 s; `game_counter`s with "reset on fire" divide it to 0.1, 0.2, 0.5, 1, 4 and 8 s. |
| Gauge needle | `game_counter_set` sends USE_SET with a fraction to an invisible `momentary_door` (the slider) hidden in the gauge bezel. The needle is an `env_beam` from the dial centre to the slider, so it swings as the slider moves. The same USE_SET trick sets `ambient_generic` pitch. |
| Phase, synchroscope | The phase is a `func_tracktrain` on a ring of 12 `path_track`s behind the synchroscope's bezel; a beam from the centre to it is the pointer, switched on and off with the SYNCHROSCOPE switch. Its speed is the slip: the logic stops it (USE_OFF) and gives it a number of quarter notches (USE_SET, `game_counter_set`), negative to run the ring backwards, none at 100 %. The tracks at 11 and 1 o'clock are the in-phase window's edges (entering or leaving depends on which way it turns), so the breaker closes on exactly what you see. Every track sets the sync lamps' brightness with an `env_render`; a `func_wall_toggle` covers them while the switch is off. |
| Control switch | `func_rot_button` with a pistol-grip handle, maintained in two positions ("toggle", with `wait` 0.5: `wait -1` would make it stay pushed for good). Each turn toggles a flag. The logic can turn the handle itself, so the 52G, 41 and gate-trip handles always agree with the plant. |
| Lamp, annunciator window | `func_wall` with `+0` / `+A` textures, switched explicitly on or off by `trigger_relay`. |
| Spring-return dial | `momentary_rot_button` with Auto Return: held, it turns to its stop and fires its target every frame; let go, it springs back and fires once every 0.1 s on the way. A `game_counter` reset every 0.05 s only counts it as turning on two fires within one tick, so the fires on the way back are ignored. While it turns, a rule steps the variable every tick. |
| Knob | `momentary_rot_button`: while it turns it fires its target every frame. That sets a "moving" flag; a rule steps the variable every 0.2 s while the flag is set. A counter on the 0.05 s tick notices 0.1 s without movement (when the button itself reverses), flips the direction flag and drops any step still pending. |

### Round gauges

Stock Half-Life has no entity that turns to an angle it is told, so each needle is a beam. Its start
is the `env_beam` itself (it counts as a point when the beam is set up), and its end is an invisible
`momentary_door` that slides along a line 5 units above the dial centre, inside the bezel. Only the
part of the beam inside the round window can be seen, so the visible needle has a fixed length and
swings ±50° as the slider moves. `build.py` bends the fractions the logic sends (`warp()`), so the
needle angle is linear in the value and the scales are printed evenly. The slider carries a small
invisible tab in front of the bezel. Without it the slider would sit entirely inside solid brushes,
the server would never send it to the client, and the needle would not be drawn.

Beams are additive (they glow), so the dials are black with cream scales and an orange needle. The
kilowatt, wicket gate and exciter field gauges have a second scale inside the first (amperes,
discharge in cfs, field volts). On the spillway panel the frame is turned 90 degrees: its sliders
run along Y.

## The model

`plant.py` is the whole model; `hlogic.py` compiles it into entities and contains a simulator that
reproduces how those entities behave in `hl.dll`; `test_plant.py` runs it by hand through the simulator:
a manual start on the gate dials (and that the spring-back of a dial adds no step), the phase turning
SLOW and FAST as the speed settles and standing still at 100 % (and its in-phase window agreeing with
where the pointer is), nudging it into the window and synchronizing, closes with the synchroscope off
both in and out of phase, the power factor at three loads and two field settings, the emergency stop, an
out-of-phase close, a start with the PLC and AVR, the PLC following the river for 400 s, the lube oil pump stopping
on line, a brake air failure and the spillway in MANUAL and back in AUTO. The simulated
`func_tracktrain` follows the SDK's `CPathTrack::LookAhead()`, so it reverses the way the game does.

Speed, gate, voltage, field, servo oil, brake air, bearing temperature, river depth and spill gate are
integer variables, and so is the river's flow. Speed, voltage, field and gate move in 1 % steps; the fast ones update every 0.1 s. Four difference variables carry only their sign:

- **speed error** = T(gate) − speed, where T is the speed the runner would settle at for that gate
  (speed-no-load at 15 % gate, runaway near 175 %). Off line, speed moves toward T at 5 %/s while it
  is more than 20 % away, 2.5 %/s within 20 % and 1 %/s for the last 5 %, so it eases in instead of
  charging into the overspeed trip. Coasting with the gate shut it drops 2.5 %/s; the brakes take 5 %/s.
- **volts per hertz** = speed − voltage and **field** = field − voltage: off line the voltage follows the
  field but can't exceed what the speed allows. On line the grid holds the voltage and the field sets
  the reactive power (the POWER FACTOR meter).
- **river balance** = river flow − gate − 15 × spill gate: the river depth at the intake (RIVER DEPTH
  gauge, spillway panel) integrates it.

Gate movements draw servo oil; on line
between 20 and 45 % gate the draft-tube vortex rope shows on the vibration gauge and annunciator.

## Building

A compiled map is already included: `out/sablecreek.bsp`, and `sablecreek_valve_addon.zip` with the
map and sounds in the right folders. To rebuild it:

```
python3 build.py        # writes out/sablecreek.map, .wad, .rad and out/sound/sablecreek/*.wav
```

Then compile with SDHLT or VHLT: `compile.bat` (Windows) or `compile.sh` (Linux). Set `TOOLS`
to the folder that holds the compile tools first. The textures are embedded in the .bsp
(`-wadinclude`), so the WAD isn't needed to play. RAD picks up `sablecreek.rad` (the ceiling
texture lights) on its own. Light levels can be changed with
`SC_LIGHTS="texlight front back panel" python3 build.py` (default `200 130 90 60`).

## Installing and playing

1. Unzip `sablecreek_valve_addon.zip` into `Steam/steamapps/common/Half-Life/`, so the map lands in
   `valve_addon/maps/` and the sounds in `valve_addon/sound/sablecreek/`.
2. In Half-Life, turn on Options → Content → *Allow custom addon content*.
3. Open the console and type `map sablecreek`.

Press USE (E) on switches and the brake and spillway CONTROL dials; hold it on the LOWER / RAISE dials and
the firing-angle dial.

**Launch option needed:** the map has more entities than Half-Life allows by default, so add
`-num_edicts 2048` to Half-Life's launch options (Steam → Half-Life → Properties → Launch Options).
Without it the map won't load ("ED_Alloc: no free edicts"). 2048 is the most the engine can handle.

The map has 1,984 entities (1,977 once the lights are compiled in): the 1 % steps need a counter and a
gauge setter for most values. The default limit is 1,200 (900 before the 25th-anniversary update), hence
the launch option. The variables only get counters for values something listens for, and needles step
2-4 % where they are not read closely.

## Status

Compiled with SDHLT 1.3.1 (CSG, BSP, full VIS, RAD -extra) with no warnings or errors. The compiled
.bsp was checked outside the game. The checks covered:

- entity and model counts;
- for every needle, that the beam finds its own slider, including the two on the turned spillway panel;
- slider travel from the compiled model bounds (12 units, allowing for the engine's 1-unit bounds padding);
- that every slider tab is in an open leaf the player can see from the start, and the synchroscope
  train's tab at every one of its 12 path_tracks; that the tracks form one closed ring round the dial;
- that switch, knob and dial pivots come out on whole units;
- a render of the BSP with its lightmaps, with the needles drawn where the beams would be.

It has not been played in Half-Life yet. The entity logic was checked in `test_plant.py`'s simulator,
which follows the Half-Life SDK's entity code, not in the engine itself. The beam needles, the
synchroscope's track train and the spring-return dials are the parts most worth checking in game.
