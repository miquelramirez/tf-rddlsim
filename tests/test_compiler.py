from tfrddlsim.parser import RDDLParser
from tfrddlsim.compiler import Compiler

import numpy as np
import tensorflow as tf

import unittest


class TestCompiler(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open('rddl/Reservoir.rddl', mode='r') as file:
            RESERVOIR = file.read()

        parser = RDDLParser()
        parser.build()
        cls.rddl = parser.parse(RESERVOIR)

    def setUp(self):
        self.graph = tf.Graph()
        self.compiler = Compiler(self.rddl, self.graph)
        self.assertIs(self.compiler._rddl, self.rddl)
        self.assertIs(self.compiler._graph, self.graph)

    def test_build_object_table(self):
        self.compiler._build_object_table()
        self.assertIn('res', self.compiler._object_table)
        size = self.compiler._object_table['res']['size']
        idx = self.compiler._object_table['res']['idx']
        self.assertEqual(size, 8)
        objs = ['t1', 't2', 't3', 't4', 't5', 't6', 't7', 't8']
        for i, obj in enumerate(objs):
            self.assertIn(obj, idx)
            self.assertEqual(idx[obj], i)

    def test_build_pvariable_table(self):
        self.compiler._build_pvariable_table()

        expected = {
            'non_fluents': {
                'MAX_RES_CAP/1',
                'UPPER_BOUND/1',
                'LOWER_BOUND/1',
                'RAIN_SHAPE/1',
                'RAIN_SCALE/1',
                'DOWNSTREAM/2',
                'SINK_RES/1',
                'MAX_WATER_EVAP_FRAC_PER_TIME_UNIT/0',
                'LOW_PENALTY/1',
                'HIGH_PENALTY/1'
            },
            'intermediate_fluents': {
                'evaporated/1',
                'rainfall/1',
                'overflow/1'
            },
            'state_fluents': {
                'rlevel/1'
            },
            'action_fluents': {
                'outflow/1'
            }
        }

        self.assertIsInstance(self.compiler._pvariable_table, dict)
        for fluent_type, fluents in self.compiler._pvariable_table.items():
            self.assertIn(fluent_type, expected)
            self.assertSetEqual(set(fluents), expected[fluent_type])

    def test_build_action_preconditions_table(self):
        self.compiler._build_pvariable_table()
        self.compiler._build_preconditions_table()

        local_preconds = self.compiler._local_action_preconditions
        self.assertIsInstance(local_preconds, dict)
        self.assertEqual(len(local_preconds), 1)
        self.assertIn('outflow/1', local_preconds)
        self.assertEqual(len(local_preconds['outflow/1']), 2)

        global_preconds = self.compiler._global_action_preconditions
        self.assertIsInstance(global_preconds, list)
        self.assertEqual(len(global_preconds), 0)

    def test_instantiate_non_fluents(self):
        self.compiler._build_object_table()
        nf = self.compiler._instantiate_non_fluents()

        expected_non_fluents = {
            'MAX_RES_CAP/1': { 'shape': (8,), 'dtype': tf.float32 },
            'UPPER_BOUND/1': { 'shape': (8,), 'dtype': tf.float32 },
            'LOWER_BOUND/1': { 'shape': (8,), 'dtype': tf.float32 },
            'RAIN_SHAPE/1': { 'shape': (8,), 'dtype': tf.float32 },
            'RAIN_SCALE/1': { 'shape': (8,), 'dtype': tf.float32 },
            'DOWNSTREAM/2': { 'shape': (8,8), 'dtype': tf.bool },
            'SINK_RES/1': { 'shape': (8,), 'dtype': tf.bool },
            'MAX_WATER_EVAP_FRAC_PER_TIME_UNIT/0': { 'shape': (), 'dtype': tf.float32 },
            'LOW_PENALTY/1': { 'shape': (8,), 'dtype': tf.float32 },
            'HIGH_PENALTY/1': { 'shape': (8,), 'dtype': tf.float32 }
        }
        self.assertIsInstance(nf, dict)
        self.assertEqual(len(nf), len(expected_non_fluents))
        for name, tensor in nf.items():
            self.assertIn(name, expected_non_fluents)
            shape = expected_non_fluents[name]['shape']
            dtype = expected_non_fluents[name]['dtype']
            self.assertEqual(tensor.name, '{}:0'.format(name))
            self.assertIsInstance(tensor, tf.Tensor)
            self.assertEqual(tensor.dtype, dtype)
            self.assertEqual(tensor.shape, tf.TensorShape(shape))

        expected_initializers = {
            'MAX_RES_CAP/1': [ 100.,  100.,  200.,  300.,  400.,  500.,  800., 1000.],
            'UPPER_BOUND/1': [ 80.,  80., 180., 280., 380., 480., 780., 980.],
            'LOWER_BOUND/1': [20., 20., 20., 20., 20., 20., 20., 20.],
            'RAIN_SHAPE/1': [1., 1., 1., 1., 1., 1., 1., 1.],
            'RAIN_SCALE/1': [ 5.,  3.,  9.,  7., 15., 13., 25., 30.],
            'DOWNSTREAM/2': [
                [False, False, False, False, False, True, False, False],
                [False, False, True, False, False, False, False, False],
                [False, False, False, False, True, False, False, False],
                [False, False, False, False, False, False, False, True],
                [False, False, False, False, False, False, True, False],
                [False, False, False, False, False, False, True, False],
                [False, False, False, False, False, False, False, True],
                [False, False, False, False, False, False, False, False]
            ],
            'SINK_RES/1': [False, False, False, False, False, False, False, True],
            'MAX_WATER_EVAP_FRAC_PER_TIME_UNIT/0': 0.05,
            'LOW_PENALTY/1': [-5., -5., -5., -5., -5., -5., -5., -5.],
            'HIGH_PENALTY/1': [-10., -10., -10., -10., -10., -10., -10., -10.]
        }
        with tf.Session(graph=self.graph) as sess:
            for name, tensor in nf.items():
                value = sess.run(tensor)
                list1 = list(value.flatten())
                list2 = list(np.array(expected_initializers[name]).flatten())
                for v1, v2 in zip(list1, list2):
                    self.assertAlmostEqual(v1, v2)

    def test_instantiate_initial_state_fluents(self):
        self.compiler._build_object_table()
        sf = self.compiler._instantiate_initial_state_fluents()

        expected_state_fluents = {
            'rlevel/1': { 'shape': (8,) , 'dtype': tf.float32 }
        }
        self.assertIsInstance(sf, dict)
        self.assertEqual(len(sf), len(expected_state_fluents))
        for name, tensor in sf.items():
            self.assertIn(name, expected_state_fluents)
            shape = expected_state_fluents[name]['shape']
            dtype = expected_state_fluents[name]['dtype']
            self.assertEqual(tensor.name, '{}:0'.format(name))
            self.assertIsInstance(tensor, tf.Tensor)
            self.assertEqual(tensor.dtype, dtype)
            self.assertEqual(tensor.shape, tf.TensorShape(shape))

        expected_initializers = {
            'rlevel/1': [75., 50., 50., 50., 50., 50., 50., 50.]
        }
        with tf.Session(graph=self.graph) as sess:
            for name, tensor in sf.items():
                value = sess.run(tensor)
                list1 = list(value.flatten())
                list2 = list(np.array(expected_initializers[name]).flatten())
                for v1, v2 in zip(list1, list2):
                    self.assertAlmostEqual(v1, v2)

    def test_instantiate_default_action_fluents(self):
        self.compiler._build_object_table()
        af = self.compiler._instantiate_default_action_fluents()

        expected_action_fluents = {
            'outflow/1': { 'shape': (8,) , 'dtype': tf.float32 }
        }
        self.assertIsInstance(af, dict)
        self.assertEqual(len(af), len(expected_action_fluents))
        for name, tensor in af.items():
            self.assertIn(name, expected_action_fluents)
            shape = expected_action_fluents[name]['shape']
            dtype = expected_action_fluents[name]['dtype']
            self.assertEqual(tensor.name, '{}:0'.format(name))
            self.assertIsInstance(tensor, tf.Tensor)
            self.assertEqual(tensor.dtype, dtype)
            self.assertEqual(tensor.shape, tf.TensorShape(shape))

        expected_initializers = {
            'outflow/1': [0., 0., 0., 0., 0., 0., 0., 0.]
        }
        with tf.Session(graph=self.graph) as sess:
            for name, tensor in af.items():
                value = sess.run(tensor)
                list1 = list(value.flatten())
                list2 = list(np.array(expected_initializers[name]).flatten())
                for v1, v2 in zip(list1, list2):
                    self.assertAlmostEqual(v1, v2)
