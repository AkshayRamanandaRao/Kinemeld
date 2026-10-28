"""Verify and record occurrence identities for the authored example projects."""
import base64
import hashlib
import step_geometry


def identify_authored_step(asset, expected):
    """Require each authored part-to-occurrence mapping to match the CAD transfer."""
    witnesses = {}
    for index, source in enumerate(asset['files']):
        data = base64.b64decode(source['data'], validate=True)
        if len(data) != source['byteLength'] or hashlib.sha256(data).hexdigest() != source['sha256']:
            raise ValueError('Example STEP source does not match its recorded hash.')
        parts = step_geometry.convert_step(data, source['name'])['parts']
        selected = {key.split(':', 1)[1]: value for key, value in expected.items() if key.startswith(f'{index}:')}
        if len(parts) != len(selected) or {part['id'] for part in parts} != set(selected):
            raise ValueError('Example STEP occurrence count or mapping changed.')
        for part in parts:
            witness = part.get('occurrenceWitness')
            if not witness or (selected[part['id']] is not None and witness != selected[part['id']]):
                raise ValueError('Example STEP occurrence identity differs from its authored mapping.')
            witnesses[f"{index}:{part['id']}"] = witness
    if set(witnesses) != set(expected):
        raise ValueError('Example STEP occurrence mapping is incomplete.')
    asset['occurrenceWitnesses'] = witnesses
    asset['unverifiedBindings'] = {}
