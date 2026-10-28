"""Reference-frame schema checks include old projects and invalid persisted input."""
import copy
import unittest
import reference_frames
import spatial_assembly


class ReferenceFrameTests(unittest.TestCase):
    def setUp(self):
        self.model = {'bodies': [{'id':'arm'}], 'frames': [{'id':'pivot','name':'Pivot','body':'arm',
            'translation':{'x':.1,'y':0.,'z':.2},'rotation':{'rx':10.,'ry':20.,'rz':30.}}]}

    def test_ground_body_and_legacy(self):
        self.assertEqual(reference_frames.validate_frames(self.model), [])
        self.model['frames'][0]['body']='ground';self.assertEqual(reference_frames.validate_frames(self.model), [])
        del self.model['frames'];self.assertEqual(reference_frames.validate_frames(self.model), [])

    def test_invalid_values_and_missing_body(self):
        for patch in ({'body':'missing'}, {'name':' '}, {'id':'ground'}, {'translation':{'x':True,'y':0,'z':0}},
                      {'rotation':{'rx':0,'ry':float('nan'),'rz':0}}, {'other':1}):
            with self.subTest(patch=patch):
                model=copy.deepcopy(self.model);model['frames'][0].update(patch)
                self.assertTrue(reference_frames.validate_frames(model))
        self.model['frames'].append(copy.deepcopy(self.model['frames'][0]))
        self.assertTrue(any(issue['field']=='frames.1.id' for issue in reference_frames.validate_frames(self.model)))

    def test_bad_frame_container(self):
        for value in (None, {}, [None], [self.model['frames'][0]]*65):
            with self.subTest(value=value):
                model={'bodies':[],'frames':value};self.assertTrue(reference_frames.validate_frames(model))

    def test_linked_axis_roundoff_stays_within_unit_vector_bounds(self):
        model=copy.deepcopy(next(item['model'] for item in spatial_assembly.EXAMPLES if item['id']=='spatial-revolute'))
        model['joints'][0]['axisA']={'x':0.,'y':0.,'z':1.}
        model['frames']=[{'id':'pivot','name':'Pivot','body':'arm','translation':copy.deepcopy(model['joints'][0]['anchorB']),'rotation':{'rx':12.,'ry':90.,'rz':168.}}]
        model['frameLinks']=[{'joint':'hinge','side':'b','frame':'pivot','axis':'x'}];reference_frames.sync_links(model)
        self.assertLessEqual(max(abs(value) for value in model['joints'][0]['axisB'].values()),1.)
        self.assertTrue(spatial_assembly.validate(model)['valid'],spatial_assembly.validate(model))

    def test_spatial_validation_and_deck_keep_frame_metadata_out_of_physics(self):
        model=copy.deepcopy(next(item['model'] for item in spatial_assembly.EXAMPLES if item['id']=='spatial-revolute'))
        original_deck=spatial_assembly.deck(model)
        model['frames']=copy.deepcopy(self.model['frames'])
        self.assertTrue(spatial_assembly.validate(model)['valid'])
        self.assertEqual(spatial_assembly.deck(model),original_deck)
        model['frames'][0]['body']='missing'
        self.assertTrue(any(issue['field']=='frames.0.body' for issue in spatial_assembly.validate(model)['issues']))

    def test_live_link_validation_and_synchronization(self):
        model=copy.deepcopy(next(item['model'] for item in spatial_assembly.EXAMPLES if item['id']=='spatial-revolute'))
        model['frames']=copy.deepcopy(self.model['frames']);model['frameLinks']=[{'joint':'hinge','side':'b','frame':'pivot','axis':'x'}]
        self.assertTrue(reference_frames.validate_links(model))
        reference_frames.sync_links(model);self.assertEqual(reference_frames.validate_links(model),[])
        self.assertEqual(model['joints'][0]['anchorB'],model['frames'][0]['translation'])
        expected=reference_frames.frame_axis(model['frames'][0],'x')
        for k in ('x','y','z'):self.assertAlmostEqual(model['joints'][0]['axisB'][k],expected[k])
        before=copy.deepcopy(model);model['frames'][0]['translation']['x']+=.1;self.assertTrue(reference_frames.validate_links(model))
        reference_frames.sync_links(model);self.assertAlmostEqual(model['joints'][0]['anchorB']['x'],.2)
        model['frameLinks']=[];model['frames'][0]['translation']['x']=.5;reference_frames.sync_links(model);self.assertAlmostEqual(model['joints'][0]['anchorB']['x'],.2)
        self.assertEqual(before['joints'][0]['anchorA'],model['joints'][0]['anchorA'])

    def test_live_link_rejects_missing_parent_duplicate_bad_values(self):
        model=copy.deepcopy(next(item['model'] for item in spatial_assembly.EXAMPLES if item['id']=='spatial-revolute'))
        model['frames']=copy.deepcopy(self.model['frames']);link={'joint':'hinge','side':'b','frame':'pivot','axis':'x'};model['frameLinks']=[link];reference_frames.sync_links(model)
        for patch in ({'frame':'missing'}, {'joint':'missing'}, {'side':'a'}, {'axis':'q'}, {'axis':True}):
            with self.subTest(patch=patch):
                bad=copy.deepcopy(model);bad['frameLinks'][0].update(patch);self.assertTrue(reference_frames.validate_links(bad))
        bad=copy.deepcopy(model);bad['frameLinks'].append(copy.deepcopy(link));self.assertTrue(reference_frames.validate_links(bad))
        bad=copy.deepcopy(model);bad['joints'][0]['anchorB']['x']=10**400;self.assertTrue(reference_frames.validate_links(bad))
        bad=copy.deepcopy(model);bad['frames'][0]['rotation']['rx']=None
        with self.assertRaises(ValueError):reference_frames.sync_links(bad)
