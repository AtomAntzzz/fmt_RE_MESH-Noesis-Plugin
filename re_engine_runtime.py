"""Per-plugin view of legacy options, host APIs and orchestration callbacks.

The entry dictionary remains the sole storage for mutable legacy state. A bound
module closes over this view, never another module's globals or a cached host.
This also lets Noesis reload the entry without retargeting older callbacks.
"""


class PluginRuntime(object):
    def __init__(self, namespace):
        object.__setattr__(self, "_namespace", namespace)

    def __getattr__(self, name):
        try:
            return self._namespace[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self._namespace[name] = value
