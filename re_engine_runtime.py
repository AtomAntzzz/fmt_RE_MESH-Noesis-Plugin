"""Per-plugin view of legacy options, host APIs and orchestration callbacks.

The entry dictionary remains the sole storage for mutable legacy state. A bound
module closes over this view, never another module's globals or a cached host.
This also lets Noesis reload the entry without retargeting older callbacks.
"""


class ImportSelectionDraft(object):
    def __init__(self):
        self.loadItems = []
        self.fullLoadItems = []
        self.loadedMlists = {}
        self.selectionSources = {}
        self.selectedActions = []


class ImportSelectionState(object):
    def __init__(self):
        self.currentDir = ""
        self.dialog = None
        self.motDialog = None
        self.drafts = []


class ImportSession(object):
    """Resources owned by one import, or borrowed from an existing scene."""
    def __init__(self, kind, input_path, profile=None, resources=None):
        self.kind = kind
        self.input_path = input_path
        self.profile = profile
        self.resources = (resources if resources is not None else
                          dict((key, []) for key in ('bones', 'remap', 'textures', 'materials')))
        self.selection = ImportSelectionState()


def beginImportSession(runtime, kind, input_path):
    session = ImportSession(kind, input_path)
    runtime.importSession = session
    return session


def currentImportSession(runtime):
    session = getattr(runtime, "importSession", None)
    if session is None:
        session = beginImportSession(runtime, "compatibility", "")
    return session


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
