"""Real STEP geometry round trips for authored primitive bodies."""
import copy
import hashlib
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

import primitive_step
import step_geometry


class PrimitiveValidationTests(unittest.TestCase):
    def test_spatial_pose_rejects_nonfinite_partial_and_extra_fields(self):
        model={"shape":"brick","dimensions":{"x":.2,"y":.3,"z":.4},"pose":{"x":1.,"y":2.,"z":3.,"rx":20.,"ry":30.,"rz":40.}}
        primitive_step.validate(model)
        for key,value in (("rx",float("nan")),("ry",361),("z",1001),("y",True)):
            invalid=copy.deepcopy(model);invalid["pose"][key]=value
            with self.subTest(key=key),self.assertRaises(primitive_step.PrimitiveError):primitive_step.validate(invalid)
        for change in (lambda p:p.pop("rx"),lambda p:p.update(angleDeg=0)):
            invalid=copy.deepcopy(model);change(invalid["pose"])
            with self.assertRaises(primitive_step.PrimitiveError):primitive_step.validate(invalid)

    def test_reject_invalid_shapes_pose_dimensions_and_unknown_fields(self):
        base={'shape':'brick','dimensions':{'x':1.,'y':.2,'z':.1},'pose':{'x':0.,'z':0.,'angleDeg':0.}}
        cases=[]
        for value in (None,True,-1,0,float('nan'),float('inf'),10**400,1001,'1'):
            model=copy.deepcopy(base);model['dimensions']['x']=value;cases.append(model)
        for key,value in [('angleDeg',361),('x',1001),('z',float('nan')),('x',True)]:
            model=copy.deepcopy(base);model['pose'][key]=value;cases.append(model)
        model=copy.deepcopy(base);model['dimensions']['radius']=1;cases.append(model)
        model=copy.deepcopy(base);model['shape']='cone';cases.append(model)
        model=copy.deepcopy(base);model['pose']['y']=1;cases.append(model)
        model=copy.deepcopy(base);model['other']='include';cases.append(model)
        for item in cases:
            with self.subTest(item=item):
                with self.assertRaises(primitive_step.PrimitiveError):primitive_step.generate_step(item)

    def test_regular_extrusion_rejects_invalid_side_counts(self):
        base={'shape':'regular-extrusion','dimensions':{'radius':.1,'length':1.,'sides':6},'pose':{'x':0.,'z':0.,'angleDeg':0.}}
        primitive_step.validate(base)
        for value in (2,65,3.5,True,'6',6.0):
            model=copy.deepcopy(base);model['dimensions']['sides']=value
            with self.subTest(value=value),self.assertRaises(primitive_step.PrimitiveError):primitive_step.validate(model)

    def test_custom_profile_rejects_crossing_overlaps_and_bad_points(self):
        base={'shape':'polygon-extrusion','dimensions':{'length':.4,'vertices':[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1}]},'pose':{'x':0.,'y':0.,'z':0.,'rx':0.,'ry':0.,'rz':0.}}
        for coords in ([(0,0),(1,1),(0,1),(1,0)],[(0,0),(1,0),(.5,0),(.5,1),(0,1)],[(0,0),(1,0),(1,0)],[(0,0),(1,0),(True,1)]):
            model=copy.deepcopy(base);model['dimensions']['vertices']=[{'x':x,'y':y} for x,y in coords]
            with self.subTest(coords=coords),self.assertRaises(primitive_step.PrimitiveError):primitive_step.validate(model)

    def test_revolution_rejects_negative_radius_and_separate_axis_touches(self):
        base={'shape':'revolution','dimensions':{'vertices':[]},'pose':{'x':0.,'y':0.,'z':0.,'rx':0.,'ry':0.,'rz':0.}}
        for coords in ([(-.1,0),(.2,0),(.2,1)],[(0,0),(.2,0),(.2,.2),(0,.3),(.2,.4),(.2,.6),(0,.6)]):
            model=copy.deepcopy(base);model['dimensions']['vertices']=[{'x':x,'y':y} for x,y in coords]
            with self.subTest(coords=coords),self.assertRaises(primitive_step.PrimitiveError):primitive_step.validate(model)


@unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP runtime is required')
class PrimitiveCadTests(unittest.TestCase):
    def test_conical_revolution_matches_analytic_centroidal_inertia(self):
        import step_mass
        vertices=[{'x':0.,'y':0.},{'x':.2,'y':0.},{'x':0.,'y':1.}]
        data=primitive_step.generate_step({'shape':'revolution','dimensions':{'vertices':vertices},'pose':{'x':0.,'y':0.,'z':0.,'rx':0.,'ry':0.,'rz':0.}})
        result=step_mass.calculate(data,1000.,'part-1');mass=1000*math.pi*.2**2/3
        self.assertAlmostEqual(result['mass'],mass,places=7);self.assertAlmostEqual(result['centerOfMass']['z'],0.,places=7)
        self.assertAlmostEqual(result['inertia'][2][2],3*mass*.2**2/10,places=7);self.assertAlmostEqual(result['inertia'][0][0],3*mass*.2**2/20+3*mass/80,places=7)

    def test_axis_touching_revolution_matches_solid_cylinder(self):
        import step_mass
        vertices=[{'x':0.,'y':0.},{'x':.2,'y':0.},{'x':.2,'y':1.},{'x':0.,'y':1.}]
        result=step_mass.calculate(primitive_step.generate_step({'shape':'revolution','dimensions':{'vertices':vertices},'pose':{'x':0.,'y':0.,'z':0.,'rx':0.,'ry':0.,'rz':0.}}),1000.,'part-1')
        mass=40*math.pi;self.assertAlmostEqual(result['mass'],mass,places=7);self.assertAlmostEqual(result['inertia'][2][2],mass*.2**2/2,places=7)

    def test_stepped_revolution_with_rotated_pose_matches_two_tubes(self):
        import step_mass
        from OCP.gp import gp_Quaternion,gp_Vec
        coords=[(.05,0),(.2,0),(.2,.3),(.1,.3),(.1,.6),(.05,.6)]
        pose={'x':.3,'y':-.2,'z':.4,'rx':20.,'ry':35.,'rz':-40.}
        data=primitive_step.generate_step({'shape':'revolution','dimensions':{'vertices':[{'x':x,'y':y} for x,y in coords]},'pose':pose})
        result=step_mass.calculate(data,1000.,'part-1');m1=1000*math.pi*(.2**2-.05**2)*.3;m2=1000*math.pi*(.1**2-.05**2)*.3;mass=m1+m2;zbar=(m1*.15+m2*.45)/mass
        iz=(m1*(.2**2+.05**2)+m2*(.1**2+.05**2))/2
        ix=m1*(3*(.2**2+.05**2)+.3**2)/12+m2*(3*(.1**2+.05**2)+.3**2)/12+m1*(.15-zbar)**2+m2*(.45-zbar)**2
        self.assertAlmostEqual(result['mass'],mass,places=7)
        for k in ('x','y','z'):self.assertAlmostEqual(result['centerOfMass'][k],pose[k],places=7)
        qs=[]
        for axis,key in (((1,0,0),'rx'),((0,1,0),'ry'),((0,0,1),'rz')):
            q=gp_Quaternion();q.SetVectorAndAngle(gp_Vec(*axis),math.radians(pose[key]));qs.append(q)
        r=(qs[0]*qs[1]*qs[2]).GetMatrix()
        for i in range(3):
            for j in range(3):self.assertAlmostEqual(result['inertia'][i][j],sum(r.Value(i+1,k+1)*v*r.Value(j+1,k+1) for k,v in enumerate((ix,ix,iz))),delta=1e-8)

    def test_hollow_revolution_step_matches_analytic_cylinder(self):
        import step_mass
        coords=[(.1,0),(.2,0),(.2,1),(.1,1)]
        for points in (coords,list(reversed(coords))):
            spec={'shape':'revolution','dimensions':{'vertices':[{'x':x,'y':y} for x,y in points]},'pose':{'x':.3,'y':-.2,'z':.4,'rx':0.,'ry':0.,'rz':0.}}
            result=step_mass.calculate(primitive_step.generate_step(spec),1000.,'part-1');mass=30*math.pi
            self.assertAlmostEqual(result['mass'],mass,places=7)
            for k in ('x','y','z'):self.assertAlmostEqual(result['centerOfMass'][k],spec['pose'][k],places=7)
            self.assertAlmostEqual(result['inertia'][2][2],mass*(.1**2+.2**2)/2,places=7)
            self.assertAlmostEqual(result['inertia'][0][0],mass*(3*(.1**2+.2**2)+1)/12,places=7)

    def test_concave_profile_step_preserves_centroid_and_full_inertia(self):
        import step_mass
        points=[(0,0),(.3,0),(.3,.1),(.1,.1),(.1,.3),(0,.3)]
        for vertices in (points,list(reversed(points))):
            spec={'shape':'polygon-extrusion','dimensions':{'length':.4,'vertices':[{'x':x,'y':y} for x,y in vertices]},'pose':{'x':.3,'y':-.2,'z':.4,'rx':0.,'ry':0.,'rz':0.}}
            data=primitive_step.generate_step(spec);result=step_mass.calculate(data,1000.,'part-1')
            self.assertAlmostEqual(result['mass'],20.,places=7)
            for key in ('x','y','z'):self.assertAlmostEqual(result['centerOfMass'][key],spec['pose'][key],places=7)
            for i,value in enumerate((.4113333333333333,.4113333333333333,.2893333333333333)):self.assertAlmostEqual(result['inertia'][i][i],value,places=7)
            self.assertAlmostEqual(result['inertia'][0][1],.072,places=7)

    def test_translated_concave_profile_rotates_world_inertia(self):
        import step_mass
        from OCP.gp import gp_Quaternion,gp_Vec
        vertices=[{'x':x+20,'y':y-30} for x,y in [(0,0),(.3,0),(.3,.1),(.1,.1),(.1,.3),(0,.3)]]
        pose={'x':.3,'y':-.2,'z':.4,'rx':20.,'ry':35.,'rz':-40.}
        result=step_mass.calculate(primitive_step.generate_step({'shape':'polygon-extrusion','dimensions':{'length':.4,'vertices':vertices},'pose':pose}),1000.,'part-1')
        self.assertAlmostEqual(result['mass'],20.,places=7)
        for key in ('x','y','z'):self.assertAlmostEqual(result['centerOfMass'][key],pose[key],places=7)
        qs=[]
        for axis,key in (((1,0,0),'rx'),((0,1,0),'ry'),((0,0,1),'rz')):
            q=gp_Quaternion();q.SetVectorAndAngle(gp_Vec(*axis),math.radians(pose[key]));qs.append(q)
        r=(qs[0]*qs[1]*qs[2]).GetMatrix();tensor=[[.4113333333333333,.072,0],[.072,.4113333333333333,0],[0,0,.2893333333333333]]
        for i in range(3):
            for j in range(3):
                expected=sum(r.Value(i+1,k+1)*tensor[k][l]*r.Value(j+1,l+1) for k in range(3) for l in range(3))
                self.assertAlmostEqual(result['inertia'][i][j],expected,delta=1e-8)

    def test_triangular_extrusion_step_mass_matches_analytic_centroid_and_inertia(self):
        import step_mass
        pose={'x':.3,'y':-.2,'z':.4,'rx':0.,'ry':0.,'rz':0.}
        data=primitive_step.generate_step({'shape':'regular-extrusion','dimensions':{'radius':.2,'length':.4,'sides':3},'pose':pose})
        result=step_mass.calculate(data,1000.,'part-1');mass=1000*3*math.sqrt(3)*.2**2*.4/4
        self.assertAlmostEqual(result['mass'],mass,places=7)
        for axis in ('x','y','z'):self.assertAlmostEqual(result['centerOfMass'][axis],pose[axis],places=7)
        iz=mass*.2**2/4;ix=iz/2+mass*.4**2/12
        for index,expected in enumerate((ix,ix,iz)):self.assertAlmostEqual(result['inertia'][index][index],expected,places=7)
        self.assertAlmostEqual(result['inertia'][0][1],0.,places=7)

    def test_spatial_primitive_preserves_noncommuting_pose_and_world_tensor(self):
        import step_mass
        from OCP.gp import gp_Quaternion
        pose={"x":.3,"y":-.2,"z":.4,"rx":20.,"ry":35.,"rz":-40.}
        dimensions={"x":.3,"y":.2,"z":.1}
        spec={"shape":"brick","dimensions":dimensions,"pose":pose}
        data=primitive_step.generate_step(spec)
        result=step_mass.calculate(data,1000.,"part-1")
        self.assertAlmostEqual(result["mass"],6.,places=7)
        for axis in ("x","y","z"):self.assertAlmostEqual(result["centerOfMass"][axis],pose[axis],places=7)
        # Independent quaternion composition provides the world inertia oracle.
        from OCP.gp import gp_Vec
        qs=[]
        for axis,key in (((1,0,0),"rx"),((0,1,0),"ry"),((0,0,1),"rz")):
            q=gp_Quaternion();q.SetVectorAndAngle(gp_Vec(*axis),math.radians(pose[key]));qs.append(q)
        q=qs[0]*qs[1]*qs[2];matrix=q.GetMatrix()
        d=[6*(.2**2+.1**2)/12,6*(.3**2+.1**2)/12,6*(.3**2+.2**2)/12]
        for i in range(3):
            for j in range(3):
                expected=sum(matrix.Value(i+1,k+1)*d[k]*matrix.Value(j+1,k+1) for k in range(3))
                self.assertAlmostEqual(result["inertia"][i][j],expected,delta=1e-8)

    def test_real_step_volume_centre_inertia_and_viewer_mesh(self):
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        cases=[('brick',{'x':.3,'y':.2,'z':1.},.3*.2*1.,((.2**2+1.)/12,(.3**2+1.)/12,(.3**2+.2**2)/12)),
               ('cylinder',{'radius':.2,'length':1.},math.pi*.2**2,((3*.2**2+1)/12,(3*.2**2+1)/12,.2**2/2)),
               ('sphere',{'radius':.2},4*math.pi*.2**3/3,(2*.2**2/5,)*3),
               ('ellipsoid',{'x':.3,'y':.2,'z':.4},4*math.pi*.3*.2*.4/3,((.2**2+.4**2)/5,(.3**2+.4**2)/5,(.3**2+.2**2)/5)),
               ('regular-extrusion',{'radius':.2,'length':1.,'sides':6},3*math.sqrt(3)*.2**2/2,(.2**2*2.5/12+1/12,.2**2*2.5/12+1/12,.2**2*2.5/6))]
        with tempfile.TemporaryDirectory() as directory:
            for shape,dimensions,volume,factors in cases:
                with self.subTest(shape=shape):
                    spec={'shape':shape,'dimensions':dimensions,'pose':{'x':.3,'z':-.4,'angleDeg':23.}}
                    original=copy.deepcopy(spec);data=primitive_step.generate_step(spec);self.assertEqual(spec,original)
                    self.assertIn(b'ISO-10303-21;',data[:1024]);path=Path(directory)/(shape+'.step');path.write_bytes(data)
                    reader=STEPControl_Reader();self.assertEqual(reader.ReadFile(str(path)),IFSelect_RetDone);self.assertGreater(reader.TransferRoots(),0)
                    props=GProp_GProps();BRepGProp.VolumeProperties_s(reader.OneShape(),props,1e-10)
                    self.assertAlmostEqual(props.Mass()/1e9,volume,delta=volume*1e-6)
                    cm=props.CentreOfMass();self.assertAlmostEqual(cm.X()/1000,.3,places=7);self.assertAlmostEqual(cm.Y()/1000,0,places=7);self.assertAlmostEqual(cm.Z()/1000,-.4,places=7)
                    tensor=props.MatrixOfInertia();angle=math.radians(23);c,s=math.cos(angle),math.sin(angle)
                    expected=(volume*(c*c*factors[0]+s*s*factors[2]),volume*factors[1],volume*(s*s*factors[0]+c*c*factors[2]))
                    for i in range(3):self.assertAlmostEqual(tensor.Value(i+1,i+1)/1e15,expected[i],delta=max(expected)*2e-5)
                    rendered=step_geometry.convert_step(data,shape+'.step')
                    self.assertEqual(rendered['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(rendered['units'],'m');self.assertEqual(len(rendered['parts']),1)
                    self.assertGreater(rendered['triangleCount'],0)
                    vertices=rendered['parts'][0]['positions'];mins=[min(vertices[i::3]) for i in range(3)];maxs=[max(vertices[i::3]) for i in range(3)]
                    for i,centre in enumerate((.3,0,-.4)):
                        self.assertAlmostEqual((mins[i]+maxs[i])/2,centre,delta=.002)


if __name__=='__main__':unittest.main()

