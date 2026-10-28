"""Validate optional body-local reference frames retained in a spatial project."""
import math
import re

IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")
MAX_FRAMES = 64
MAX_LINKS = 64


def frame_axis(frame, axis):
    """Return a frame axis in parent coordinates using Euler123."""
    rx,ry,rz=(math.radians(frame['rotation'][key]) for key in ('rx','ry','rz'))
    cx,sx=math.cos(rx),math.sin(rx);cy,sy=math.cos(ry),math.sin(ry);cz,sz=math.cos(rz),math.sin(rz)
    matrix=((cy*cz,-cy*sz,sy),(cx*sz+sx*sy*cz,cx*cz-sx*sy*sz,-sx*cy),(sx*sz-cx*sy*cz,sx*cz+cx*sy*sz,cx*cy))
    col=('x','y','z').index(axis)
    values=[matrix[row][col] for row in range(3)];length=math.sqrt(sum(value*value for value in values))
    return dict(zip(('x','y','z'),(max(-1.,min(1.,value/length)) for value in values)))


def validate_links(model, *, check_values=True):
    """Reject invalid references and, normally, snapshots inconsistent with their links."""
    links=model.get('frameLinks',[]);issues=[]
    def issue(field,message):issues.append({'level':'error','field':field,'message':message})
    if not isinstance(links,list) or len(links)>MAX_LINKS:
        issue('frameLinks',f'Supply at most {MAX_LINKS} joint-frame links.');return issues
    frames=model.get('frames',[]);joints=model.get('joints',[])
    if not isinstance(frames,list) or not isinstance(joints,list):
        issue('frameLinks','Joint-frame links require valid frames and joints.');return issues
    frame_map={f['id']:f for f in frames if isinstance(f,dict) and isinstance(f.get('id'),str)}
    joint_map={j['id']:j for j in joints if isinstance(j,dict) and isinstance(j.get('id'),str)}
    seen=set()
    for i,link in enumerate(links):
        path=f'frameLinks.{i}'
        if not isinstance(link,dict) or set(link)!={'joint','side','frame','axis'}:
            issue(path,'Supply exactly joint, side, frame and axis.');continue
        joint_id,side,frame_id,axis=(link[key] for key in ('joint','side','frame','axis'))
        if not all(isinstance(x,str) for x in (joint_id,side,frame_id,axis)) or side not in ('a','b') or axis not in ('x','y','z'):
            issue(path,'Use a joint ID, side a or b, frame ID, and axis x, y or z.');continue
        if (joint_id,side) in seen:issue(path,'Each joint end can have only one live frame link.');continue
        seen.add((joint_id,side));joint=joint_map.get(joint_id);frame=frame_map.get(frame_id)
        if joint is None or frame is None:issue(path,'Reference an existing joint and frame.');continue
        if frame.get('body')!=joint.get(side):issue(path,'The linked frame must belong to this joint end’s body.');continue
        if validate_frames({'bodies':model.get('bodies',[]),'frames':[frame]}):issue(path,'The linked frame must be valid before it can be applied.');continue
        if not check_values:continue
        suffix=side.upper();anchor=joint.get('anchor'+suffix);axis_value=joint.get('axis'+suffix)
        def equal(actual,expected):
            return isinstance(actual,dict) and set(actual)=={'x','y','z'} and all(type(actual[k]) in (int,float) and abs(actual[k])<=1000 and math.isfinite(actual[k]) and abs(actual[k]-expected[k])<=1e-9 for k in ('x','y','z'))
        if not equal(anchor,frame['translation']):issue(path,'The linked joint anchor is out of sync with the frame; reapply or unlink it.')
        if axis_value is not None and not equal(axis_value,frame_axis(frame,axis)):issue(path,'The linked joint axis is out of sync with the frame; reapply or unlink it.')
    return issues


def sync_links(model):
    """Update linked joint snapshots in place after a valid frame edit."""
    issues=validate_links(model,check_values=False)
    if issues:raise ValueError(issues[0]['message'])
    if not model.get('frameLinks'):return
    frames={f['id']:f for f in model.get('frames',[]) if isinstance(f,dict) and isinstance(f.get('id'),str)};joints={j['id']:j for j in model.get('joints',[]) if isinstance(j,dict) and isinstance(j.get('id'),str)}
    for link in model.get('frameLinks',[]):
        frame,joint=frames[link['frame']],joints[link['joint']];suffix=link['side'].upper()
        joint['anchor'+suffix]=dict(frame['translation'])
        if 'axis'+suffix in joint:joint['axis'+suffix]=frame_axis(frame,link['axis'])


def validate_frames(model):
    """Return model validation issues; frames do not alter constraints by themselves."""
    frames = model.get('frames', [])
    issues = []
    def issue(field, message):
        issues.append({'level': 'error', 'field': field, 'message': message})
    if not isinstance(frames, list) or len(frames) > MAX_FRAMES:
        issue('frames', f'Supply at most {MAX_FRAMES} reference frames.')
        return issues
    bodies = model.get('bodies', [])
    names = {body.get('id') for body in bodies if isinstance(body, dict) and isinstance(body.get('id'), str)} if isinstance(bodies, list) else set()
    names.add('ground')
    seen = set()
    for i, frame in enumerate(frames):
        path = f'frames.{i}'
        if not isinstance(frame, dict) or set(frame) != {'id', 'name', 'body', 'translation', 'rotation'}:
            issue(path, 'Supply exactly id, name, body, translation and rotation.')
            continue
        identifier = frame['id']
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or identifier == 'ground':
            issue(path+'.id', 'Use a letter-leading identifier up to 32 characters; ground is reserved.')
        elif identifier in seen:
            issue(path+'.id', 'Reference-frame identifier is repeated.')
        else:
            seen.add(identifier)
        name = frame['name']
        if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
            issue(path+'.name', 'Use 1–120 printable characters.')
        if not isinstance(frame['body'], str) or frame['body'] not in names:
            issue(path+'.body', 'Select ground or a declared body.')
        for key, components, limit in (('translation', ('x','y','z'), 1000), ('rotation', ('rx','ry','rz'), 360)):
            vector = frame[key]
            if not isinstance(vector, dict) or set(vector) != set(components):
                issue(path+'.'+key, 'Supply exactly the three components.')
                continue
            for component in components:
                value = vector[component]
                if type(value) not in (int, float) or abs(value) > limit or not math.isfinite(value):
                    issue(path+'.'+key+'.'+component, f'Enter a finite value within ±{limit}.')
    return issues
