"""Create the worked oleo fixture using the original licensed wheel-end STEP."""
import copy,json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
project=copy.deepcopy(json.loads((root/'examples/prescribed-wheel-bump/wheel-bump.mbdyn-studio').read_text(encoding='utf8')))
model=project['model'];model['name']='Open CAD wheel-end oleo fixture';model['simulation']={'duration':1.,'step':.0005}
model['forces']=[{'id':'oleo','type':'oleo-strut','a':'ground','b':'knuckle','anchorA':{'x':-.04,'y':-.0875,'z':.5},'anchorB':{'x':0.,'y':0.,'z':0.},
 'restLength':.5,'pressure':1e6,'gasArea':.001,'gasVolume':.001,'gamma':1.4,'minLength':.46,'maxLength':.5,'stopStiffness':60000.,'stopDamping':100.,
 'fluidArea':.001,'fluidDensity':850.,'dischargeCoefficient':.8,'compressionMeteringArea':.00015,'reboundMeteringArea':.0001}]
(Path(__file__).parent/'wheel-oleo.mbdyn-studio').write_text(json.dumps(project,indent=2)+'\n',encoding='utf8')
