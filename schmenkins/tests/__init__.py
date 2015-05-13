import unittest

from schmenkins import State

class SchmenkinsTest(unittest.TestCase):
    def tearDown(self):
        State.all_states = set()
