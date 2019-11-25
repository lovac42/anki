import copy

from anki.fields import Field
from anki.templates import Template
from anki.utils import DictAugmentedIdUsn


class Model(DictAugmentedIdUsn):
    def load(self, manager, dict):
        super().load(manager, dict)
        self['tmpls'] = [Template(self, templateType) for templateType in self['tmpls']]
        self['flds'] = [Field(self, fieldType) for fieldType in self['flds']]

    def deepcopy(self):
        dict = {}
        for key in self:
            if key in {'tmpls', 'flds'}:
                image = [object.deepcopy() for object in self[key]]
            else:
                image = copy.deepcopy(self[key])
            dict[key] = image
        return self.__class__(self.manager, dict=dict)
