import copy

from anki.consts import *
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

    # Tools
    ##################################################

    def nids(self):
        """The ids of notes whose model is model.
        Keyword arguments
        model -- a model object."""
        return self.manager.col.db.list(
            "select id from notes where mid = ?", self.getId())
    # Templates
    ##################################################

    def _syncTemplates(self):
        """Generate all cards not yet generated, whose note's model is model.
        It's called only when model is saved, a new model is given and template is asked to be computed"""
        self.manager.col.genCards(self.nids())

    # Required field/text cache
    ##########################################################################

    def _updateRequired(self):
        """Entirely recompute the model's req value"""
        if self['type'] == MODEL_CLOZE:
            # nothing to do
            return
        req = []
        flds = [fieldType['name'] for fieldType in self['flds']]
        for template in self['tmpls']:
            ret = template._req(flds)
            req.append([template['ord'], ret[0], ret[1]])
        self['req'] = req
