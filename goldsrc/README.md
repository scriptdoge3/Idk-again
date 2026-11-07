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
| Gauge needle | `game_counter_set` sends USE_SET with a fraction to an invisible `momentary_door` (the slider) hidden in the gauge bezel. The needle is an `env_beam` from the dial centre to the slider, so it swings as the slider moves. The same USE_SET trick sets `ambient_generic` pitch. |
| Breaker control switch | `func_rot_button` with a pistol-grip handle, maintained in two positions. Each turn toggles a flag and runs the command. The logic also turns the handle itself, so it always agrees with the plant. |
| Lamp, annunciator window | `func_wall` with `+0` / `+A` textures, switched explicitly on or off by `trigger_relay`. |
| Analog knob, handwheel | `momentary_rot_button`: while it turns it fires its target every frame. That sets a "moving" flag; a rule steps the variable once per 0.1 or 0.2 s while the flag is set, then clears it. A counter on the 0.05 s base tick notices 0.1 s without movement (when the button itself reverses) and flips the direction flag. |

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
kilowatt meter has a second, blue needle for the load setpoint. The kW, wicket gate and exciter field
gauges have a second scale inside the first (amperes, discharge in cfs, field volts).

### Breaker control switches

The 52G breaker, unit START/STOP and 41 field breaker are pistol-grip control switches. Use one and it
turns to the other side: right is CLOSE / START / ON, left is TRIP / STOP / OFF. If the plant does
something by itself (the auto-synchronizer closes the breaker, a trip opens it, a close is refused),
the logic turns the handle to match within half a second. A refused close looks like a spring
return. PUMP TEST, annunciator ACK and RESET, 86 RESET and the instructor's UTILITY TRIP are
spring-return twist switches: they turn 45°, act, and spring back. EMERGENCY STOP stays a red
mushroom push button, as it would be in a real plant.

### Analog controls

The load setpoint, wicket gate (governor in MAN), spill gate and the instructor's river inflow are
`momentary_rot_button`s rather than raise/lower buttons. Hold USE on one and it turns; the longer
you hold it, the further the value goes. Like every `momentary_rot_button`, it turns the other way
each time you let go and grab it again, so each control has an amber NEXT TURN lamp (RAISE / LOWER)
showing which way the next turn will go. Grabbing it again within a tenth of a second keeps the
same direction.

The river knob is absolute: its position is the flood inflow (0 to +140 cfs). It also drives the
FLOOD INFLOW gauge behind it directly (that gauge's scale is printed where the needle really points), and its direction lamp resets when it reaches the top stop.
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

The map has 1,175 entities, so it needs the 25th-anniversary engine (its limit is 1,200; the old
limit was 900).

Press USE (E) on switches; hold it on knobs and handwheels:

- **Panel 2:** UNIT START/STOP and 52G BREAKER control switches, EMERGENCY STOP, 86 RESET (only at
  standstill), GOVERNOR and SYNC MODE selectors, the WICKET GATE handwheel (works with the governor in
  MAN) and the LOAD SETPOINT knob (the blue needle on the kW gauge).
- **Panel 3:** annunciator ACK and RESET, the 41 FIELD BREAKER control switch, LEVEL CONTROL and SPILLWAY
  selectors, and the SPILL GATE handwheel (works with the spillway selector in MAN).
- **Panel 1:** OIL PUMP TEST.
- **Instructor console on the desk:** UTILITY TRIP (load rejection), the RIVER knob with its FLOOD INFLOW
  gauge, and an oil pump failure switch.

## Status

Compiled with SDHLT 1.3.1 (CSG, BSP, full VIS, RAD -extra) with no warnings or errors. The compiled
.bsp was checked outside the game. The checks covered:

- entity and model counts;
- for every needle, that the beam finds its own slider;
- slider travel from the compiled model bounds (12 units, allowing for the engine's 1-unit bounds padding);
- that each slider's tab is in an open leaf the player can see from the start;
- that switch, knob and handwheel pivots come out on whole units;
- a render of the BSP with its lightmaps, with the needles drawn where the beams would be.

It has not been played in Half-Life yet. The entity logic was checked in `test_plant.py`'s simulator,
which follows the Half-Life SDK's entity code, not in the engine itself. The beam needles are the part
most worth checking in game: their width and glow come from the engine's beam renderer, which the
render above only imitates.
