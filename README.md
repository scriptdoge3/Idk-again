# Mühlbach Hydro · Unit 1

A 2D control-room simulator of a small run-of-river hydro station as it would
have been built in 1988: a **250 kW vertical Kaplan turbine** directly coupled to a
**72-pole, 3-phase, 400 V / 50 Hz synchronous generator** (83.3 min⁻¹). You only
ever see the six floor-standing control cabinets. Everything is analog: moving-coil
meters, cam switches, incandescent lamps, electromechanical relays with flags, an
annunciator with horn, a 3-pen strip-chart recorder, a Ferraris kWh meter and a
dot-matrix event printer.

Open `index.html` in a browser. No build step and no dependencies (fonts come from Google Fonts and
fall back gracefully when offline).

`sim.js` is the plant model, `ui.js` the panel hardware, and `look.js` the surface realism: it bakes
powder-coat texture, grime, fingerprints, scratches, worn edges and the ceiling-light falloff into one
static canvas per door, so the look costs nothing per frame.

The control room is real 3D (WebGL via three.js r149 from jsDelivr). The cabinets are solid boxes
with roofs, sides and recessed plinths; meters, lamps, knobs, pushbuttons, the E-stop, breaker
control switches, lockout handles, relays, annunciator, recorder, counters and printer are 3D
objects on the doors, lit by fluorescent fittings with shadows and reflections. The room has a lino
floor, chequer-plate cable trench covers and a rubber safety mat. `view3d.js` builds the scene from
the (hidden) DOM cabinets: flat artwork is painted from the DOM into one texture per cabinet front,
live instruments use their canvases as textures, and clicks are ray-cast back onto the DOM controls,
so the simulator logic is untouched.

Drag to look around, scroll or W A S D to walk, right-drag to step sideways, double-click a panel to
step up to it. Without WebGL (or with `#flat` in the address) the 2D panel view is used instead.

Simulator controls (sound, sim time, instructor station, manual, walking to a cabinet) are behind
the SIMULATOR button in the top-right corner, so the room itself has no toolbar.

## Cabinets

| | Cabinet | What's on it |
|---|---|---|
| +A1 | Unit control | Auto start/stop sequencer, AUTO/MAN key, emergency stop, auxiliaries (cooling water, HP oil lift, brakes, trash-rack cleaner), intake gate, 110 V DC battery, station clock, hours/starts counters |
| +A2 | Turbine governor | Speed, gate, blade angle, discharge, gate limiter, speed/load setpoints, oil pressure unit (lead/lag pumps), net head, shaft vibration, seal water |
| +A3 | Generator & excitation | V/A with phase selectors, Hz, kW, kvar, cos φ, field current/voltage, 8-point Pt100 scanner, AVR (MAN / AUTO U / cos φ), cooler air, stator earth-fault U0, space heaters |
| +A4 | Synchronizing & network | Double voltmeter, synchroscope, dark-lamp sync lamps, vibrating-reed double frequency meter, auto-synchronizer, sync-check key, single-line mimic with 52L / 52G discrepancy switches, kWh and kvarh metering |
| +A5 | Protection | 16 relays (12, 12M, 50/51 induction disc, 59, 27, 81, 32, 40, 78, 64S, 87G, 49, 26, 63, 71, 33) and hand-reset lockouts 86E / 86M |
| +A6 | Alarms & recording | 30-window annunciator (ISA ringback sequence), 3-pen recorder, headwater/tailwater/trash-rack edgewise meters, event printer |

## What is simulated

- Water column with inertia (non-minimum-phase water hammer), Kaplan double regulation with
  an on-cam efficiency hill and off-cam penalty, runaway characteristic, pond level, weir spill,
  tailwater rise with flow, trash-rack fouling.
- Shaft swing equation with damper torque; one-axis generator model (E′ behind X′d, field
  dynamics, saturation) on an infinite bus, or islanded with station/feeder load.
- Self-fed static excitation with field flashing, V/Hz, over- and under-excitation limiters,
  manual follow-up channel, cos φ regulation.
- Electro-hydraulic PID governor with droop, gate limiter, start opening, load rejection logic,
  level control, and servomotors that depend on accumulator pressure.
- Auto start/stop sequence, auto-synchronizer with breaker closing-time compensation,
  sync-check relay, out-of-phase closing (torque shock or shaft damage), pole slipping, loss of field,
  loss of mains, bearing and stator thermal models, DC battery discharge.
- An instructor station (top bar) for initial conditions, time acceleration, network and river
  events, 12 malfunctions and random faults.

`MANUAL` in the top bar opens the plant's operating instruction sheet.
