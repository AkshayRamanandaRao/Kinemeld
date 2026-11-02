"""Trusted sampled rotary PD peer over MBDyn's native loopback TCP streams."""
import json
import math
from pathlib import Path
import queue
import socket
import struct
import subprocess
import sys
import threading
import time


def servos(model):
    return [item for item in model.get('jointTorques', []) if item.get('type') == 'servo']


def reference(control, time_value):
    target = math.radians(control['targetAngleDeg'])
    phase = min(1., max(0., time_value / control['rampTime']))
    return (.5 * target * (1 - math.cos(math.pi * phase)),
            0. if phase == 1 else .5 * target * math.pi / control['rampTime'] * math.sin(math.pi * phase))


def command(control, time_value, angle, speed):
    desired, rate = reference(control, time_value)
    raw = control['kp'] * (desired - angle) + control['kd'] * (rate - speed)
    torque = max(-control['torqueLimit'], min(control['torqueLimit'], raw))
    return dict(desiredAngle=desired, desiredSpeed=rate, error=desired-angle,
                commandTorque=torque, commandSaturated=abs(raw) > control['torqueLimit'])


def _receive(connection, count):
    packet = bytearray()
    while len(packet) < count:
        part = connection.recv(count-len(packet))
        if not part:
            raise ValueError('Native solver feedback ended before the requested final time.')
        packet.extend(part)
    return packet


def peer(directory):
    model = json.loads((directory/'project.json').read_text(encoding='utf-8'))
    controls = servos(model)
    duration, step = (model['simulation'][key] for key in ('duration', 'step'))
    listeners, connections = [], []
    try:
        for _ in range(2):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listeners.append(listener)
            listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(10)
        print(json.dumps({'ports': [item.getsockname()[1] for item in listeners]}), flush=True)
        for listener in listeners:
            connection, _ = listener.accept(); connections.append(connection)
            connection.settimeout(10); connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            listener.close()
        commands, feedback = connections
        previous = [(0., False)] * len(controls)
        with (directory/'controller-trace.jsonl').open('w', encoding='utf-8', buffering=1) as trace:
            for index in range(math.ceil(duration/step)+2):
                values = struct.unpack(f'={1+2*len(controls)}d', _receive(feedback, 8*(1+2*len(controls))))
                t = values[0]
                if not all(math.isfinite(value) for value in values) or abs(t-index*step) > 1e-7*max(1., duration):
                    raise ValueError('Native controller feedback is nonfinite, out of order or off the fixed time grid.')
                states = []
                for i, control in enumerate(controls):
                    q, speed = values[1+2*i:3+2*i]
                    if abs(q) >= math.pi-1e-5 or abs(speed)*step > .1:
                        raise ValueError(f"Servo {control['id']} exceeded the resolved +/-pi angle or 0.1 rad/step bound.")
                    state = dict(id=control['id'], angle=q, speed=speed, **command(control, t, q, speed))
                    state.update(torque=previous[i][0], saturated=previous[i][1], power=previous[i][0]*speed)
                    states.append(state)
                # MBDyn may take one extra fixed step when accumulated time is just below final time.
                final = t >= duration
                trace.write(json.dumps(dict(time=t, sent=not final, servoStates=states), allow_nan=False)+'\n')
                if final:
                    return 0
                # The command based on converged state n is held during solver step n+1.
                commands.sendall(struct.pack(f'={len(controls)}d', *(state['commandTorque'] for state in states)))
                previous = [(state['commandTorque'], state['commandSaturated']) for state in states]
        raise ValueError('Native controller feedback exceeded the bounded step count.')
    finally:
        for item in connections+listeners:
            item.close()


def supervise(directory, solver_command):
    """Both children inherit the existing run's Windows job/POSIX process group."""
    import spatial_assembly
    model = json.loads((directory/'project.json').read_text(encoding='utf-8'))
    check = spatial_assembly.validate(model)
    if not check['valid'] or not servos(model):
        raise ValueError('The managed rotary controller requires a validated servo model.')
    controller = solver = None
    try:
        with (directory/'controller.log').open('wb') as log:
            controller = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--peer', str(directory)],
                                          stdout=subprocess.PIPE, stderr=log)
            ready = queue.Queue()
            threading.Thread(target=lambda: ready.put(controller.stdout.readline()), daemon=True).start()
            try:
                data = json.loads(ready.get(timeout=10))
            except (queue.Empty, ValueError) as exc:
                raise ValueError('The local controller did not open its bounded loopback channels.') from exc
            ports = data.get('ports')
            if not isinstance(ports, list) or len(ports) != 2 or any(type(port) is not int or not 0 < port < 65536 for port in ports):
                raise ValueError('The local controller returned invalid loopback ports.')
            (directory/'model.mbd').write_text(spatial_assembly.deck(model, control_ports=ports), encoding='utf-8')
            solver = subprocess.Popen(solver_command, cwd=directory)
            (directory/'controller-processes.json').write_text(json.dumps({'controller':controller.pid,'solver':solver.pid}),encoding='utf-8')
            controller_finished = None
            while solver.poll() is None:
                code = controller.poll()
                if code is not None and code != 0:
                    raise ValueError('The local controller failed; the native solver was stopped. Inspect controller.log.')
                if code == 0:
                    controller_finished = controller_finished or time.monotonic()
                    if time.monotonic()-controller_finished > 2:
                        raise ValueError('The controller finished before the native solver terminated; the solver was stopped.')
                time.sleep(.01)
            if solver.returncode != 0:
                raise ValueError(f'Native controlled solve failed with exit {solver.returncode}.')
            try:
                code = controller.wait(timeout=2)
            except subprocess.TimeoutExpired as exc:
                raise ValueError('The native solver ended without a completed controller exchange.') from exc
            if code != 0:
                raise ValueError('The local controller failed; inspect controller.log.')
            return 0
    finally:
        for child in (solver, controller):
            if child is not None and child.poll() is None:
                child.kill(); child.wait()


def read_trace(directory, model, samples):
    controls = servos(model)
    if not controls:
        return
    path = directory/'controller-trace.jsonl'
    if path.stat().st_size > 64*1024*1024:
        raise ValueError('The controller trace exceeds its bounded read size.')
    import spatial_assembly as sp
    lookup = {body['id']: body for body in model['bodies']}
    joints = {joint['id']: joint for joint in model['joints']}
    frames = {}
    for control in controls:
        joint = joints[control['joint']]
        ra, rb = (sp.body_rotation(lookup.get(joint[key])) for key in ('a', 'b'))
        axis = sp.mul(ra, sp.xyz(joint['axisA'])); first, second, _ = sp.basis(axis)
        world = [[first[i], second[i], axis[i]] for i in range(3)]
        frames[control['id']] = (sp.matmul(sp.transpose(ra), world), sp.matmul(sp.transpose(rb), world))
    previous = [(0., False)]*len(controls)
    with path.open(encoding='utf-8') as stream:
        for index, sample in enumerate(samples):
            line = stream.readline(65537)
            if not line or len(line) > 65536:
                raise ValueError('The controller trace is missing, truncated or oversized.')
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != {'time', 'sent', 'servoStates'} or type(row['sent']) is not bool:
                raise ValueError('The controller trace has an invalid record schema.')
            if type(row['time']) not in (int,float) or not math.isfinite(row['time']) or row['sent'] != (index != len(samples)-1):
                raise ValueError('The controller trace has invalid time or final-handshake evidence.')
            states = row.get('servoStates', [])
            keys = {'id','angle','speed','desiredAngle','desiredSpeed','error','torque','saturated','power','commandTorque','commandSaturated'}
            if not isinstance(states, list) or any(not isinstance(state,dict) or set(state) != keys for state in states):
                raise ValueError('The controller trace has an invalid actuator schema.')
            if abs(row.get('time', -1)-sample['time']) > 1e-7*max(1., sample['time']) or [state.get('id') for state in states] != [control['id'] for control in controls]:
                raise ValueError('Native output and controller feedback do not share the same time grid and actuators.')
            if any((type(value) is not bool if key in ('saturated','commandSaturated') else type(value) not in (int,float)) or not math.isfinite(value) for state in states for key, value in state.items() if key != 'id'):
                raise ValueError('The controller trace contains invalid numeric evidence.')
            observed = {body['id']:dict(pose=node,velocity=node) for body,node in zip(model['bodies'],sample['nodes'])}
            for i, (control, state) in enumerate(zip(controls, states)):
                expected = command(control, sample['time'], state['angle'], state['speed'])
                if any(abs(state[key]-value)>1e-10*max(1.,abs(value)) for key,value in expected.items()) or (state['torque'],state['saturated']) != previous[i]:
                    raise ValueError('The recorded controller law or held command is inconsistent.')
                a,b = (observed.get(joints[control['joint']][side]) for side in ('a','b'))
                ra,rb = sp.body_rotation(a),sp.body_rotation(b);fa,fb = frames[control['id']]
                relative = sp.matmul(sp.transpose(sp.matmul(ra,fa)),sp.matmul(rb,fb))
                angle = math.atan2(relative[1][0],relative[0][0])
                axis = sp.mul(ra,sp.xyz(joints[control['joint']]['axisA']))
                speed = sum(x*y for x,y in zip(axis,sp.sub(sp.angular(b),sp.angular(a))))
                if abs(state['angle']-angle)>1e-8 or abs(state['speed']-speed)>1e-8*max(1.,abs(speed)):
                    raise ValueError('Recorded controller feedback does not match native body motion.')
                if type(state['saturated']) is not bool or type(state['commandSaturated']) is not bool or abs(state['torque'])>control['torqueLimit']+1e-12:
                    raise ValueError('The recorded controller saturation is invalid.')
                if abs(state['power']-state['torque']*state['speed'])>1e-10*max(1.,abs(state['power'])):
                    raise ValueError('The recorded actuator power is inconsistent.')
                previous[i] = (state['commandTorque'],state['commandSaturated'])
            sample['servoStates'] = states
        if stream.read(1):
            raise ValueError('The controller trace contains unmatched native samples.')
    if row.get('sent') is not False:
        raise ValueError('The controller did not observe the native final state.')
    # Independently check the peer's held commands against MBDyn's actual couple output.
    labels, label = {}, 1
    for drive in model.get('jointTorques', []):
        joint = joints[drive['joint']]
        if drive.get('type') == 'servo':
            labels[label] = drive
        label += 1+int(joint['a'] != 'ground')
    counts = {label: 0 for label in labels}
    with (directory/'result.frc').open(encoding='utf-8') as stream:
        for line in stream:
            parts = line.split()
            if not parts or int(parts[0]) not in labels:
                continue
            label = int(parts[0]); drive = labels[label]; index = counts[label]
            if len(parts) != 5 or index >= len(samples):
                raise ValueError('Native servo couple output has an unexpected shape or sample count.')
            vector = list(map(float, parts[2:]))
            sample = samples[index]; joint = joints[drive['joint']]
            body = next(node for node, body in zip(sample['nodes'], model['bodies']) if body['id'] == joint['b'])
            axis = sp.mul(sp.rotation(body['rx'], body['ry'], body['rz']), sp.xyz(joint['axisB']))
            torque = sum(a*b for a, b in zip(axis, vector))
            state = next(item for item in sample['servoStates'] if item['id'] == drive['id'])
            if not math.isfinite(torque) or abs(torque-state['torque']) > 1e-8*max(1., abs(torque)):
                raise ValueError('Native applied servo torque does not match the recorded held controller command.')
            counts[label] += 1
    if any(count != len(samples) for count in counts.values()):
        raise ValueError('Native applied servo torque is incomplete.')


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--peer':
            sys.exit(peer(Path(sys.argv[2]).resolve()))
        if len(sys.argv) > 4 and sys.argv[1] == '--run' and sys.argv[3] == '--':
            sys.exit(supervise(Path(sys.argv[2]).resolve(), sys.argv[4:]))
        raise ValueError('Use the managed application Run action for controlled actuators.')
    except (OSError, ValueError, ArithmeticError) as error:
        print(str(error), file=sys.stderr, flush=True)
        sys.exit(1)
