"""Run with python -m unittest discover -s backend -p 'test_*.py'."""

import copy
import http.client
import json
import math
import threading
import unittest

import models
from server import Handler, ThreadingHTTPServer


class ModelTests(unittest.TestCase):
    def test_invalid_physics_and_json_types(self):
        for value in [None, [], {"kind": []}, {"kind": "unsupported"}]:
            self.assertFalse(models.validate(value)["valid"])
        for invalid in [float("nan"), float("inf"), 0, -1, True, "1"]:
            project = copy.deepcopy(models.EXAMPLES[0]["model"])
            project["parameters"]["mass"] = invalid
            self.assertFalse(models.validate(project)["valid"])
        project = copy.deepcopy(models.EXAMPLES[0]["model"])
        project["parameters"]["unsupported"] = 1
        self.assertFalse(models.validate(project)["valid"])

    def test_resolution_guard_and_parameter_generation(self):
        project = copy.deepcopy(models.EXAMPLES[1]["model"])
        project["parameters"]["stiffness"] = 1000000
        self.assertFalse(models.validate(project)["valid"])
        project["parameters"]["stiffness"] = 81
        project["parameters"]["mass"] = 2.5
        output = models.deck(project)
        self.assertIn("body: 1, 2, 2.5", output)
        self.assertIn("diag, 81,0,0", output)

    def test_small_angle_period_and_energy(self):
        project = copy.deepcopy(models.EXAMPLES[0]["model"])
        project["parameters"]["angle"] = 1
        project["simulation"]["step"] = 0.001
        samples = models.preview(project)
        crossing = next(q["time"] for q in samples if q["angle"] < 0)
        period = 2*math.pi*math.sqrt(1/9.81)
        self.assertAlmostEqual(crossing, period/4, delta=0.002)
        values = models.metrics(project,samples)
        self.assertAlmostEqual(values["finalEnergy"]/values["initialEnergy"], 1, delta=1e-7)
        self.assertLess(values["maxConstraintError"], 1e-12)

    def test_oscillator_frequency_and_damping(self):
        project = copy.deepcopy(models.EXAMPLES[1]["model"])
        project["parameters"]["damping"] = 0
        project["simulation"]["step"] = 0.001
        values = models.preview(project)
        quarter = min(values, key=lambda q: abs(q["time"]-math.pi/20))
        self.assertAlmostEqual(quarter["x"], 0, delta=0.0001)
        self.assertAlmostEqual(quarter["velocity"], -1, delta=0.0001)
        for damping in [0.5, 20, 50]:
            project["parameters"]["damping"] = damping
            energies = models.metrics(project,models.preview(project))
            self.assertLess(energies["finalEnergy"], energies["initialEnergy"])

    def test_coupled_reference_constraints_energy_and_parameter_changes(self):
        project = copy.deepcopy(models.DOUBLE_PENDULUM)
        project["parameters"].update(mass1=0.8,mass2=0.35,length1=1.7,length2=0.9,angle1=-10,angle2=35)
        check = models.validate(project)
        self.assertTrue(check["valid"])
        self.assertEqual(check["summary"]["degreesOfFreedom"],2)
        self.assertEqual(check["summary"]["bodies"],2)
        values = models.preview(project)
        self.assertAlmostEqual(values[0]["angle"],-10)
        self.assertAlmostEqual(values[0]["angle2"],35)
        self.assertGreater(max(abs(q["angle2"]-q["angle"]) for q in values),20)
        checked = models.metrics(project,values)
        self.assertLess(checked["maxConstraintError"],1e-12)
        self.assertAlmostEqual(checked["finalEnergy"]/checked["initialEnergy"],1,delta=1e-6)
        generated = models.deck(project)
        self.assertIn("body: 1, 1, 0.8",generated)
        self.assertIn("body: 2, 2, 0.35",generated)
        self.assertIn("joint: 2, revolute hinge",generated)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self,method,path,body=None,headers=None):
        client = http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        client.request(method,path,body=body,headers=headers or {})
        result = client.getresponse()
        payload = json.loads(result.read())
        client.close()
        return result.status,payload

    def test_example_edit_validate_and_export(self):
        status, data = self.request("GET","/api/health")
        self.assertEqual(status,200)
        self.assertEqual(data["application"],"mbdyn-studio")
        status, data = self.request("GET","/api/examples")
        self.assertEqual(status,200)
        project = data["examples"][0]["model"]
        project["parameters"]["length"] = 2.1
        status, data = self.request("POST","/api/deck",json.dumps({"model":project}),{"Content-Type":"application/json"})
        self.assertEqual(status,200)
        self.assertTrue(data["valid"])
        self.assertIn("1.05",data["deck"])

    def test_browser_origin_host_and_nonfinite_input(self):
        model = json.dumps({"model":models.EXAMPLES[0]["model"]})
        status,_ = self.request("POST","/api/run",model,{"Content-Type":"application/json","Origin":"https://example.com"})
        self.assertEqual(status,403)
        status,_ = self.request("GET","/api/examples",headers={"Host":"attacker.example"})
        self.assertEqual(status,403)
        status,_ = self.request("POST","/api/validate",'{"model":NaN}',{"Content-Type":"application/json"})
        self.assertEqual(status,400)
        status,_ = self.request("POST","/api/validate",model,{"Content-Type":"text/plain"})
        self.assertEqual(status,415)

    def test_kinematics_http_contract_and_failure_boundaries(self):
        import test_kinematics
        import server
        request=test_kinematics.request(test_kinematics.slider_crank())
        status,result=self.request("POST","/api/kinematics",json.dumps(request),{"Content-Type":"application/json"})
        self.assertEqual(status,200);self.assertTrue(result["ok"]);self.assertEqual(result["jacobianRank"],7)
        request["variables"][0]["initial"]=10**400
        status,result=self.request("POST","/api/kinematics",json.dumps(request),{"Content-Type":"application/json"})
        self.assertEqual(status,422);self.assertFalse(result["ok"]);self.assertIn("finite",result["error"])
        status,_=self.request("POST","/api/kinematics",'{"model":{},"model":{},"variables":[],"targets":[]}',{"Content-Type":"application/json"})
        self.assertEqual(status,400)
        status,_=self.request("POST","/api/kinematics",json.dumps(request),{"Content-Type":"application/json","Origin":"https://example.com"})
        self.assertEqual(status,403)
        self.assertTrue(server.KINEMATICS_LOCK.acquire(blocking=False))
        try:
            status,_=self.request("POST","/api/kinematics",json.dumps(request),{"Content-Type":"application/json"})
            self.assertEqual(status,409)
        finally:server.KINEMATICS_LOCK.release()

    def test_preview_is_explicit_and_artifact_traversal_rejected(self):
        status,data = self.request("POST","/api/preview",json.dumps({"model":models.EXAMPLES[1]["model"]}),{"Content-Type":"application/json"})
        self.assertEqual(status,200)
        self.assertEqual(data["source"],"Reference preview")
        self.assertNotIn("runId",data)
        status,_ = self.request("GET","/api/runs/../../backend/solver.json")
        self.assertEqual(status,404)


if __name__ == "__main__":
    unittest.main()
