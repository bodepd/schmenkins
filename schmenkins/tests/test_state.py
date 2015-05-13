import json
import os.path
import shutil
import tempfile

from schmenkins import tests
from schmenkins.state import State

class RootState(State):
    attrs = ['children',
             'cfg1']

class ChildState(State):
    attrs = ['health',
             'children']

class GrandChildState(State):
    attrs = ['health']


class StateTests(tests.SchmenkinsTest):
    def test_state(self):
        tmpdir = tempfile.mkdtemp()
        try:
            state_path = lambda s:os.path.join(tmpdir, '%s.json' % (s,))

            root_state = RootState()
            child1_state = ChildState()
            child2_state = ChildState(path=state_path('child2'), health="OK")
            child3_state = ChildState(health="WARNING")
            child3_state.path = state_path('child3')
            root_state.children = [child1_state, child2_state, child3_state]
            grandchild1_state = GrandChildState()
            child1_state.children = [grandchild1_state]

            # All states created, some with paths, some without. Let's fill
            # in the missing paths

            child1_state.path = state_path('child1')
            grandchild1_state.path = state_path('grandchild1')
            root_state.path = state_path('root')

            grandchild1_state.health = 'GOOD'

            self.assertEquals(json.load(open(state_path('root'))),
                               {'cfg1': None,
                                'children': [
                                  {'children': [{'health': 'GOOD'}],
                                   'health': None},
                                  {'children': None,
                                   'health': 'OK'},
                                  {'children': None,
                                   'health': 'WARNING'}]})
            self.assertEquals(json.load(open(state_path('child1'))),
                              {'children': [{'health': 'GOOD'}],
                               'health': None})
            self.assertEquals(json.load(open(state_path('child2'))),
                              {'children': None,
                               'health': 'OK'})
            self.assertEquals(json.load(open(state_path('child3'))),
                              {'children': None,
                               'health': 'WARNING'})
            self.assertEquals(json.load(open(state_path('grandchild1'))),
                              {'health': 'GOOD'})
        finally:
            shutil.rmtree(tmpdir)
