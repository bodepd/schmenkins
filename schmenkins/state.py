import json
from schmenkins import exceptions

class State(object):
    all_states = set()

    def __init__(self, path=None, **kwargs):
        self.dict = {}

        for attr in self.attrs:
            self.dict[attr] = kwargs.get(attr, None)

        self.path = path

        if self.path:
            self.load()

        self.all_states.add(self)

    def __setattr__(self, attr, value):
        if attr in self.attrs:
            self.dict[attr] = value
        super(State, self).__setattr__(attr, value)
        if attr == 'path':
            if value is not None:
                self.load()
        else:
            [s.save() for s in self.all_states]

    def __hasattr__(self, attr):
        return attr in self.attrs

    def __getattr__(self, attr):
        if attr in self.attrs:
            return self.dict.get(attr, None)
        else:
            raise AttributeError()

    def load(self):
        try:
            with open(self.path, 'r') as fp:
                data = json.load(fp)
        except ValueError:
            data = {}
        except IOError:
            data = {}
        for (k,v) in data.iteritems():
            self.dict[k] = v

    def json_helper(self, obj):
        if isinstance(obj, State):
            return obj.dict
        return obj

    def dumps(self):
        return json.dumps(self.dict, default=self.json_helper)

    def save(self):
        if self.path is None:
            return

        with open(self.path, 'w') as fp:
            json.dump(self.dict, fp, default=self.json_helper)
