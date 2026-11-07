# Sable Creek Hydro for Half-Life (GoldSrc)

The same plant as the web simulator, as a map for plain Half-Life: no mod, no DLL,
no scripting. The physics is faked with stock `hl.dll` entities used as variables.

## How the "math" works

| Idea | Entities |
|---|---|
| Integer variable | One `game_counter` per value of interest, all with the same name. A `trigger_relay` sends USE_ON (+1) or USE_OFF (−1); each counter fires `<var>_eq<v>` when the value lands on its number. |
| True/false flag | `env_global` state (and its opposite `n<flag>`), read by `multisource` masters. `env_global` "Set Initial State" seeds them at spawn. |
| Rule (if A and B then do X) | A chain of `game_counter_set` entities, each locked by a `multisource` master. Rules with the same leading conditions share links. |
| Clock | Two `multi_manager`s that trigger each other every 0.05 s; `game_counter`s with "reset on fire" divide it to 0.1, 0.2, 0.5, 1, 4 and 8 s. |
| Meter needle | `game_counter_set` sends USE_SET with a fraction to a `momentary_door`, which slides to that point on the scale. The same trick sets `ambient_generic` pitch. |
| Lamp, annunciator window | `func_wall` with `+0` / `+A` textures, switched explicitly on or off by `trigger_relay`. |
| Analog knob, handwheel | `momentary_rot_button`: while it turns it fires its target every frame. That sets a "moving" flag; a rule steps the variable once per 0.1 or 0.2 s while the flag is set, then clears it. A counter on the 0.05 s base tick notices 0.1 s without movement (when the button itself reverses) and flips the direction flag. |

### Analog controls

The load setpoint, wicket gate (governor in MAN), spill gate and the instructor's river inflow are
`momentary_rot_button`s rather than raise/lower buttons. Hold USE on one and it turns; the longer
you hold it, the further the value goes. Like every `momentary_rot_button`, it turns the other way
each time you let go and grab it again, so each control has an amber NEXT TURN lamp (RAISE / LOWER)
showing which way the next turn will go. Grabbing it again within a tenth of a second keeps the
same direction.

The river knob is absolute: its position is the flood inflow (0 to +140 cfs). It also drives the
FLOOD CFS meter next to it directly, and its direction lamp resets when it reaches the top stop.
The other three are relative: they nudge the value up or down and stop at its limits. The knob
spins freely past the limit, but the value stays put.

The plant state lives in eight variables (speed, gate, voltage, load setpoint, governor oil
pressure, headwater, spill gate, water hammer) plus four difference variables whose sign drives
the rules:

- **speed error** = T(gate) − speed, where T is the speed the runner would settle at for that gate
  (speed-no-load at 10 % gate, runaway near 175 %). Off line, speed steps toward T every tick, so a
  breaker trip at full load overspeeds the unit until the governor's closing catches up (about 130 %).
- **gate error** = (gate − 2) − setpoint, so on line the governor walks the gate to the load setpoint.
- **voltage error** = speed − voltage: excited, the voltage follows speed up to 100 %.
- **pond balance** = river − gate − 3 × spill gate: the headwater integrates it, the PLC trims the
  load setpoint to hold 513 ft, and the spillway opens only when the unit is full.

Gate movements draw oil from the pressure tank; the lead and lag pumps cut in at 270 and 250 psi.
Closing gates fast raises spiral-case pressure (water hammer). On line between 20 and 45 % gate the
draft-tube vortex rope shows on the vibration meter and annunciator.

`plant.py` is the whole model. `hlogic.py` compiles it into entities and contains a simulator that
reproduces how those entities behave in `hl.dll`; `test_plant.py` runs start, load rejection, normal
stop, E-stop and oil-pump failure through it.

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

The map has 1,150 entities, so it needs the 25th-anniversary engine (its limit is 1,200; the old
limit was 900).

Press USE (E) on buttons and selector switches; hold it on knobs and handwheels:

- **Panel 2:** START, STOP, EMERGENCY STOP, 86 RESET (only at standstill), 52G CLOSE/TRIP, GOVERNOR and
  SYNC MODE selectors, the WICKET GATE handwheel (works with the governor in MAN) and the LOAD SETPOINT
  knob (the black pointer on the kW meter).
- **Panel 3:** annunciator ACK/RESET, EXC ON/OFF, LEVEL CONTROL and SPILLWAY selectors, and the SPILL
  GATE handwheel (works with the spillway selector in MAN).
- **Panel 1:** PUMP TEST.
- **Instructor console on the desk:** utility trip (load rejection), the RIVER knob with its FLOOD CFS
  meter, and an oil pump failure switch.

## Status

Compiled with SDHLT 1.3.1 (CSG, BSP, full VIS, RAD -extra) with no warnings or errors. The compiled
.bsp was checked outside the game: entity and model counts, pointer travel from the compiled model bounds
(14 units on the panel meters, 10 on the flood meter), that the knob and handwheel origins come out where
they were placed, lightmap levels, and a render of the BSP with its lightmaps.

It has not been played in Half-Life yet. The entity logic was checked in `test_plant.py`'s simulator,
which follows the Half-Life SDK's entity code, not in the engine itself.
