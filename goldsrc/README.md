# Sable Creek Hydro for Half-Life (GoldSrc)

The same plant as the web simulator, as a map for plain Half-Life: no mod, no DLL,
no scripting. The physics is faked with stock `hl.dll` entities used as variables.
The unit is run by hand from 13 controls, with round gauges and pistol-grip control switches.

## Controls

| Panel | Control | What it does |
|---|---|---|
| 1 | LUBE OIL PUMP | Bearing lube oil. Turning the unit without it wipes the bearings in seconds (trip). |
| 1 | COOLING WATER PUMP | Bearing and generator cooling. Without it the bearings heat up in about a minute (trip). |
| 1 | SERVO OIL PUMP | Charges the gate servo accumulator. Every gate movement uses oil; below 220 psi the gate trips. |
| 1 | AIR COMPRESSOR | Brake air. The brakes are spring-applied and need 50 psi to stay released. |
| 2 | WICKET GATE handwheel | Opens or closes the gate (hold USE; each grab turns the other way, see the NEXT TURN lamps). |
| 2 | BRAKES | APPLY / RELEASE. Apply them below 30 % speed when stopping. |
| 2 | WICKET GATE TRIP (red) | The emergency stop: closes the gate fast and opens 41 and 52G. Protection turns it to TRIP by itself; turning it back to NORMAL resets (it trips again if the cause is still there). |
| 2 | SYNCHROSCOPE | Switches the synchroscope and the sync check on. |
| 2 | 52G SYNC BREAKER | Closes the generator onto the grid. Close it while the synchroscope pointer is in the green sector (the sync lamps go dark there). |
| 3 | 41 FIELD BREAKER | Connects the thyristor exciter. Opening it lets the field decay. |
| 3 | FIRING ANGLE knob | Sets the field (manual excitation). Off line it sets the voltage; on line it sets the kilovars. |
| 3 | PLC GATE CONTROL | ON: the PLC runs the gate: it brings the unit up to speed once the brakes are released, and on line it holds the pond at 513.0 ft. |
| 3 | AVR | AUTO: the AVR runs the field: 480 V off line, slightly lagging on line. |

The spillway gate runs by itself (it opens above 513.5 ft).

### Starting by hand

1. Panel 1: start the lube oil pump, the cooling water pump, the servo oil pump and the air compressor.
   Wait for servo oil and brake air to come up (the SERVO OIL and BRAKE AIR windows go dark).
2. Panel 2: BRAKES to RELEASE.
3. Open the wicket gate to about 30 %. As speed passes 80 %, bring the gate back to 10 %
   (speed-no-load): the unit settles at 100 rpm. More gate overspeeds it (trip at 140 %).
4. Panel 3: close 41 and raise the field with the firing-angle knob until GEN VOLTS reads 480.
5. Panel 2: SYNCHROSCOPE on. The pointer turns once every 6 s. Close 52G while it is in the green
   sector. Anywhere else, off speed or at the wrong voltage, it's an out-of-phase close and the unit trips.
6. Open the gate to load the unit (about 200 kW at 60 % gate). Keep it above 10 %, or the reverse-power
   relay opens 52G. Keep the field up, or loss of field trips 52G.

To stop: close the gate to 10 %, turn 52G to TRIP, open 41, close the gate, and apply the brakes below 30 %.
With PLC ON and AVR AUTO, steps 3 and 4 happen by themselves.

## How the "math" works

| Idea | Entities |
|---|---|
| Integer variable | One `game_counter` per value something listens for, all with the same name. A `trigger_relay` sends USE_ON (+1) or USE_OFF (−1); each counter fires `<var>_eq<v>` when the value lands on its number. |
| True/false flag | `env_global` state (and its opposite `n<flag>`), read by `multisource` masters. `env_global` "Set Initial State" seeds them at spawn. |
| Rule (if A and B then do X) | A chain of `game_counter_set` entities, each locked by a `multisource` master. Rules with the same leading conditions share links. |
| Clock | Two `multi_manager`s that trigger each other every 0.05 s; `game_counter`s with "reset on fire" divide it to 0.1, 0.2, 0.5, 1, 4 and 8 s. |
| Gauge needle | `game_counter_set` sends USE_SET with a fraction to an invisible `momentary_door` (the slider) hidden in the gauge bezel. The needle is an `env_beam` from the dial centre to the slider, so it swings as the slider moves. The same USE_SET trick sets `ambient_generic` pitch. |
| Synchroscope | A `func_train` circling a hexagon of `path_corner`s behind the bezel, with a beam from the centre as the pointer. The corners at 11 and 1 o'clock fire the in-phase window, so the sync check uses exactly what you see. |
| Control switch | `func_rot_button` with a pistol-grip handle, maintained in two positions. Each turn toggles a flag. The logic can turn the handle itself, so the 52G, 41 and gate-trip handles always agree with the plant. |
| Lamp, annunciator window | `func_wall` with `+0` / `+A` textures, switched explicitly on or off by `trigger_relay`. |
| Knob, handwheel | `momentary_rot_button`: while it turns it fires its target every frame. That sets a "moving" flag; a rule steps the variable every 0.2 s while the flag is set. A counter on the 0.05 s tick notices 0.1 s without movement (when the button itself reverses), flips the direction flag and drops any step still pending. |

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
discharge in cfs, field volts).

## The model

`plant.py` is the whole model; `hlogic.py` compiles it into entities and contains a simulator that
reproduces how those entities behave in `hl.dll`; `test_plant.py` runs it by hand through the simulator:
a manual start and synchronization, loading, the emergency stop, an out-of-phase close, a start with the
PLC and AVR, the PLC holding the pond, the lube oil pump stopping on line and a brake air failure.

Speed, gate, voltage, field, servo oil, brake air, bearing temperature, headwater, spill gate and water
hammer are integer variables. Four difference variables carry only their sign:

- **speed error** = T(gate) − speed, where T is the speed the runner would settle at for that gate
  (speed-no-load at 10 % gate, runaway near 175 %). Off line, speed steps toward T every tick.
- **volts per hertz** = speed − voltage and **field** = field − voltage: off line the voltage follows the
  field but can't exceed what the speed allows. On line the grid holds the voltage and the field sets
  the kilovars.
- **pond balance** = river − gate − 3 × spill gate: the headwater integrates it.

Gate movements draw servo oil; closing the gate fast raises spiral-case pressure (water hammer); on line
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

Press USE (E) on switches; hold it on the handwheel and the firing-angle knob.

The map has 1,112 entities (1,105 once the lights are compiled in), so it needs the 25th-anniversary
engine: its limit is 1,200, the old limit was 900. The variables only get counters for values something
listens for, and needles step coarsely away from their normal readings, to stay under it.

## Status

Compiled with SDHLT 1.3.1 (CSG, BSP, full VIS, RAD -extra) with no warnings or errors. The compiled
.bsp was checked outside the game. The checks covered:

- entity and model counts;
- for every needle, that the beam finds its own slider;
- slider travel from the compiled model bounds (12 units, allowing for the engine's 1-unit bounds padding);
- that every slider tab, and the synchroscope train's, is in an open leaf the player can see from the start;
- that the train's bounds are centred on its origin, so it parks the pointer exactly on each corner;
- that switch, knob and handwheel pivots come out on whole units;
- a render of the BSP with its lightmaps, with the needles drawn where the beams would be.

It has not been played in Half-Life yet. The entity logic was checked in `test_plant.py`'s simulator,
which follows the Half-Life SDK's entity code, not in the engine itself. The beam needles and the
synchroscope train are the parts most worth checking in game.
