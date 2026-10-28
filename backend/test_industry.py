"""Physical limits and independent reduced-model checks; real runs in verify_industry.py."""
import copy
import math
import unittest

import industry_models
import models


class IndustryTests(unittest.TestCase):
    def project(self,kind):
        return copy.deepcopy(next(e["model"] for e in industry_models.EXAMPLES if e["id"] == kind))

    def test_defaults_and_changed_fields_generate_physical_decks(self):
        for example in industry_models.EXAMPLES:
            model = copy.deepcopy(example["model"])
            self.assertTrue(models.validate(model)["valid"])
            model["parameters"]["sprungMass"] = 725
            self.assertIn("body: 1, 1, 725",models.deck(model))
            model["parameters"]["sprungMass"] = float("nan")
            self.assertFalse(models.validate(model)["valid"])
            model["parameters"]["sprungMass"] = 10**400
            self.assertFalse(models.validate(model)["valid"])

    def test_equilibrium_and_prescribed_road(self):
        project = self.project("suspension")
        p = project["parameters"]
        self.assertAlmostEqual(industry_models.road(project,p["bumpStart"]+p["bumpDuration"]/2),p["bumpHeight"])
        self.assertEqual(industry_models.road(project,p["bumpStart"]+p["bumpDuration"]),0)
        p["bumpHeight"] = 0
        values = models.preview(project)
        for q in values:
            self.assertEqual(q["zSprung"],0)
            self.assertEqual(q["zUnsprung"],0)
            self.assertAlmostEqual(q["tireForce"],(p["sprungMass"]+p["unsprungMass"])*p["gravity"])

    def test_static_eigenfrequencies_and_linearity(self):
        project = self.project("suspension")
        p = project["parameters"]
        frequencies = models.validate(project)["summary"]["naturalFrequenciesHz"]
        for frequency in frequencies:
            w2=(2*math.pi*frequency)**2
            determinant=(p["suspensionStiffness"]-w2*p["sprungMass"])*(p["suspensionStiffness"]+p["tireStiffness"]-w2*p["unsprungMass"])-p["suspensionStiffness"]**2
            self.assertAlmostEqual(determinant/1e10,0,delta=1e-10)
        a=models.preview(project)
        p["bumpHeight"]*=2
        b=models.preview(project)
        self.assertLess(max(abs(2*x["zSprung"]-y["zSprung"]) for x,y in zip(a,b)),1e-12)

    def test_drop_freefall_unilateral_contact_and_energy(self):
        project = self.project("landing-gear-drop")
        p=project["parameters"]
        values=models.preview(project)
        for q in values:
            if q["time"] < .02:
                self.assertAlmostEqual(q["zUnsprung"],p["dropHeight"]-p["sinkVelocity"]*q["time"]-.5*p["gravity"]*q["time"]**2,delta=1e-12)
                self.assertEqual(q["tireForce"],0)
            self.assertGreaterEqual(q["tireForce"],0)
        metrics=models.metrics(project,values)
        self.assertLess(metrics["finalEnergy"],metrics["initialEnergy"])
        p["strutDamping"]=0
        conservative=models.metrics(project,models.preview(project))
        self.assertAlmostEqual(conservative["finalEnergy"]/conservative["initialEnergy"],1,delta=2e-6)

    def test_model_validity_bounds_are_actionable(self):
        project=self.project("landing-gear-drop")
        project["parameters"]["strutLength"] = .2
        check=models.validate(project)
        self.assertFalse(check["valid"])
        self.assertTrue(any("80%" in q["message"] for q in check["issues"]))
        project=self.project("suspension")
        project["parameters"]["bumpStart"]=5
        self.assertFalse(models.validate(project)["valid"])
        project=self.project("suspension")
        project["simulation"]["step"]=.05
        self.assertFalse(models.validate(project)["valid"])


if __name__ == "__main__":
    unittest.main()
