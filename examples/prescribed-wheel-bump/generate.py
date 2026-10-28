"""Create a guided wheel-end travel fixture using the source STEP assets."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
project = json.loads((root / 'open-wheel-end/wheel-end.mbdyn-studio').read_text(encoding='utf-8'))
model = project['model']
model['name'] = 'Open CAD wheel-end prescribed travel fixture'
fixture = model['joints'][0]
fixture.update(type='prismatic', axisA={'x':0.,'y':0.,'z':1.}, motion={'amplitude':.025,'frequencyHz':1.})
model['bodies'][1]['velocity']['wx'] = 0.
model.pop('jointTorques')
(Path(__file__).parent / 'wheel-bump.mbdyn-studio').write_text(json.dumps(project,indent=2),encoding='utf-8')
