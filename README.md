# Sable Creek Hydro · Unit 1

A 3D control-room simulator of a small hydro station: one **250 kW vertical Francis turbine**
direct-coupled to a **72-pole, 480 V, 60 Hz salient-pole generator** (120 × 60 / 72 = **100 rpm**).
The map is only the control room: three floor-standing cabinets, a desk, a door, a clock and the
single-line diagram on the wall. Everything is operated from the cabinet fronts.

Open `index.html` in a browser (WebGL needed). There is no build step. three.js r149 and the fonts
load from CDNs.

| File | What it is |
|---|---|
| `sim.js` | The plant: waterway, turbine, shaft, governor, generator, excitation, network, auxiliaries, PLC, protection, annunciator |
| `panels.js` | Cabinet layouts (millimetres on each door) and all instrument artwork: dials, nameplates, displays, the PLC rack, the relay face |
| `room.js` | The three.js scene: cabinets and hardware built from the layouts, the room, lighting, camera and picking |
| `ui.js` | Simulator menu, tooltips, procedural sound, main loop |

## Moving around

Drag to look, W A S D or scroll to walk, Q E to turn, double-click a panel to step up to it, 1 2 3 to
jump to a cabinet and 0 to step back. Click the left or right side of a switch to turn it that way;
hold raise/lower switches. Hover any device to read it. On a phone, drag to look, pinch to walk and tap
a device to identify it. The SIMULATOR button holds speed (pause to ×30), sound, starting conditions,
river and utility events, 20 malfunctions, operating notes and the event log.

## Cabinets

| | Cabinet | On it |
|---|---|---|
| +CP1 | Auxiliary systems | Station service and 125 VDC (with DC ground detector), governor oil pressure unit (two pumps, lead/lag, tank level, air admission), cooling water pump and strainer backwash, draft tube air admission, generator heaters, thrust bearing HP lift pump, brakes, station air, powerhouse sump, intake headgate, trash rack and rake, penstock pressure |
| +CP2 | Turbine–generator | Generator V/A (phase selectors), kW, kvar, Hz, PF, kWh/hours/starts registers, synchronizing (incoming/running volts, synchroscope, dark sync lamps, sync mode, 25 bypass key), 52G pistol-grip switch, speed, wicket gate with gate-limit pointer, spiral case and draft tube pressure, discharge, net head, vibration, digital governor, gate limit and speed/load switches, inlet valve and bypass, RTD scanner, unit control, E-stop, 86G/86M lockouts, multifunction generator protection relay |
| +CP3 | Excitation, PLC, annunciator, spillway | 40-window annunciator (ISA ringback) with horn, brushless exciter field meters, digital AVR (FCR/AVR/VAR/PF, OEL/UEL/V/Hz), excitation switch, PLC rack behind a window with live I/O LEDs, operator interface (status, permissives, pond level setpoint, load setpoint, spillway, events, machine data), headwater/tailwater, two radial spillway gates, level control |

## What is simulated

**Waterway.** An 80 m, 1.5 m steel penstock solved by the method of characteristics (16 reaches,
1000 m/s wave speed, Darcy friction), so water hammer travels and reflects. Intake through a fouling
trash rack and a headgate, a butterfly inlet valve with its own loss curve and a bypass that equalizes a
compliant spiral case. Pond mass balance with two radial gates (orifice/weir flow), overtopping,
fish flow and a tailwater rating curve.

**Francis runner from first principles.** Flow and torque come from Euler's turbine equation with
velocity triangles: guide-vane angle from gate opening, shock loss at the runner inlet off design,
runner friction, exit swirl and draft tube recovery, labyrinth leakage, disc friction and part-load
recirculation. The result is a real hill chart: about 92 % best efficiency near 70 % gate, 250 kW at
about 87 % gate, the low-specific-speed Francis drop in flow with overspeed, and runaway near 180 %.
Exit swirl drives a precessing draft tube vortex rope at 0.28 × runner frequency between roughly 40
and 85 % of best-efficiency flow (damped by air admission), and the low-load rough zone adds broadband
pulsation. Both feed back through the draft tube pressure into flow, torque and penstock pressure.

**Shaft.** 18 000 kg·m² rotor (H ≈ 3.3 s). Thrust bearing friction depends on load (rotor weight plus
hydraulic thrust) and oil film: boundary friction below about 12 % speed unless the HP lift is
running, with pad heating and wiping. Guide bearings, windage, core and field losses, air brakes with
stiction, and gate leakage creep.

**Generator and network.** Salient-pole subtransient model (field, d- and q-axis dampers, saturation)
with flux states scaled by speed, so it works from standstill. A two-node network: 480 V bus with
station service, 500 kVA step-up transformer, 12.47 kV feeder load and a utility source behind a
recloser. Out-of-phase closing, islanding, reclosing onto a live island and pole slipping come out of the
equations.

**Excitation.** Brushless exciter (rotating armature, diode bridge with commutation, saturation,
armature reaction), PMG-fed digital AVR with soft start, V/Hz limiter, reactive droop, inverse-time OEL,
UEL and FCR/AVR/VAR/PF modes.

**Governor and PLC.** Digital PID governor (isochronous off line, 4 % power droop on line) with
gate limiter, start opening, speed-probe supervision and servomotors whose speed depends on oil pressure.
Oil pressure unit with an air-over-oil tank (gas law, slow air loss, air admission) and lead/lag pumps.
The PLC runs the start and stop sequences, auto-synchronizer with breaker-time compensation, pond level
control with inflow feed-forward, automatic spillway control and auto-restart on level.

**Protection.** Relay functions 24, 27, 32, 40 (offset mho), 50, 51V, 59, 64G, 78, 81O/U, 87G and PLC
trips 12 (electronic and mechanical overspeed), 38, 39, 49, 63, 71 and E-stop, with 86G/86M hand-reset
lockouts. Thermal models for bearings, stator, generator air coolers and cooling water.

Starting states, river flow, floods, debris, utility trips and outages, sags, frequency dips and the
malfunctions are in the SIMULATOR menu.
