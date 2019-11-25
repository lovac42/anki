import copy

from anki.templates import Template
from anki.utils import DictAugmentedIdUsn


class Model(DictAugmentedIdUsn):
    def load(self, manager, dict):
        super().load(manager, dict)
        self['tmpls'] = [Template(self, templateType) for templateType in self['tmpls']]

    def deepcopy(self):
        dict = {}
        for key in self:
            if key in {'tmpls'}:
                image = [object.deepcopy() for object in self[key]]
            else:
                image = copy.deepcopy(self[key])
            dict[key] = image
        return self.__class__(self.manager, dict=dict)
