import copy
import re

from anki.consts import *
from anki.field import Field
from anki.template import Template
from anki.utils import DictAugmentedIdUsn

class Model(DictAugmentedIdUsn):
    def load(self, manager, dic):
        super.__init__(manager, dic)
        self['tmpls'] = map(Template, self['tmpls'])
        self['flds'] = map(Field, self['flds'])

    def new(self, manager, name):
        "Create a new model, save it in the registry, and return it."
        # caller should call save() after modifying
        new = copy.deepcopy(defaultModel)
        new['name'] = name
        new['mod'] = intTime()
        new['flds'] = []
        new['tmpls'] = []
        new['tags'] = []
        new['id'] = None
        self.load(manager, new)

    def save(self, template=False):
        """
        * Mark model modified.

        Keyword arguments:
        model -- A Model
        templates -- whether to check for cards not generated in this model
        """
        self._updateRequired(model)
        if templates:
            model._syncTemplates()
        super.save()

    def setCurrent(self, model):
        """Change curModel value and marks the collection as modified."""
        self.manager.col.conf['curModel'] = model['id']
        self.manager.col.setMod()

    def rem(self):
        "Delete model, and all its cards/notes."
        self.manager.col.modSchema(check=True)
        current = self.manager.current().getId() == self.getId()
        # delete notes/cards
        self.manager.col.remCards(self.manager.col.db.list("""
select id from cards where nid in (select id from notes where mid = ?)""",
                                      self.getId()))
        # then the model
        del self.manager.models[str(self.getId())]
        self.manager.save()
        # GUI should ensure last model is not deleted
        if current:
            list(self.models.values())[0].setCurrent()

    def ensureNameUnique(self):
        """Transform the name of model into a new name.

        If a model with this name but a distinct id exists in the
        manager, the name of this object is appended by - and by a
        5 random digits generated using the current time.
        Keyword arguments"""
        for mcur in self.manager.all():
            if (mcur['name'] == self['name'] and mcur['id'] != self['id']):
                self['name'] += "-" + checksum(str(time.time()))[:5]
                break


    def update(self):
        "Add or update an existing model. Used for syncing and merging."
        self.ensureNameUnique()
        self.models[str(model['id'])] = self
        # mark registry changed, but don't bump mod time
        self.manager.save()

    def _setID(self):
        """Set the id of model to a new unique value."""
        while 1:
            id = str(intTime(1000))
            if id not in self.manager.models:
                break
        self['id'] = id

    def nids(self):
        """The ids of notes whose model is model.

        Keyword arguments
        model -- a model object."""
        return self.manager.col.db.list(
            "select id from notes where mid = ?", self.getId())

    # Schema hash
    ##########################################################################

    def scmhash(self):
        """Return a hash of the schema, to see if models are
        compatible. Consider only name of fields and of card type, and
        not the card type itself.

        """
        scm = ""
        for fieldType in self['flds']:
            scm += fieldType['name']
        for template in self['tmpls']:
            scm += template['name']
        return checksum(scm)

    def _updateRequired(self):
        """Entirely recompute the model's req value"""
        if self['type'] == MODEL_CLOZE:
            # nothing to do
            return
        req = []
        flds = [fieldType['name'] for fieldType in self['flds']]
        for template in self['tmpls']:
            ret = template._reqForTemplate(flds)
            req.append((template['ord'], ret[0], ret[1]))
        self['req'] = req

    def availOrds(self, flds):
        """Given a joined field string, return ordinal of card type which
        should be generated. See
        ../documentation/templates_generation_rules.md for the detail

        """
        if self['type'] == MODEL_CLOZE:
            return self._availClozeOrds(flds)
        fields = {}
        for index, fieldType in enumerate(splitFields(flds)):
            fields[index] = fieldType.strip()
        avail = []
        for ord, type, req in self['req']:
            # unsatisfiable template
            if type == "none":
                continue
            # AND requirement?
            elif type == "all":
                ok = True
                for idx in req:
                    if not fields[idx]:
                        # missing and was required
                        ok = False
                        break
                if not ok:
                    continue
            # OR requirement?
            elif type == "any":
                ok = False
                for idx in req:
                    if fields[idx]:
                        ok = True
                        break
                if not ok:
                    continue
            avail.append(ord)
        return avail

    def _availClozeOrds(self, flds, allowEmpty=True):
        """The list of fields F which are used in some {{cloze:F}} in a template

        keyword arguments:
        flds: a list of fields as in the database
        allowEmpty: allows to treat a note without cloze field as a note with a cloze number 1
        """
        sflds = splitFields(flds)
        map = self.fieldMap()
        ords = set()
        matches = re.findall("{{[^}]*?cloze:(?:[^}]?:)*(.+?)}}", self['tmpls'][0]['qfmt'])
        matches += re.findall("<%cloze:(.+?)%>", self['tmpls'][0]['qfmt'])
        for fname in matches:
            if fname not in map:
                continue#Do not consider cloze not related to an existing field
            ord = map[fname][0]
            ords.update([int(match)-1 for match in re.findall(
                r"(?s){{c(\d+)::.+?}}", sflds[ord])])#The number of the cloze of this field, minus one
        if -1 in ords:#remove cloze 0
            ords.remove(-1)
        if not ords and allowEmpty:
            # empty clozes use first ord
            return [0]
        return list(ords)

    def _syncTemplates(self):
        """Generate all cards not yet generated, whose note's model is model.

        It's called only when model is saved, a new model is given and template is asked to be computed"""
        self.col.genCards(self.nids())

    def _updateTemplOrds(self):
        """Change the value of 'ord' in each template of this model to reflect its new position"""
        for index, template in enumerate(self['tmpls']):
            template['ord'] = index

    def _transformFields(self, fn):
        """For each note of the model self, apply fn to the set of field's
        value, and save the note modified.

        fn -- a function taking and returning a list of field.

        """
        # model hasn't been added yet?
        if not self.getId():
            return
        notesUpdates = []
        for (id, flds) in self.manager.col.db.execute(
            "select id, flds from notes where mid = ?", self.getId()):
            notesUpdates.append((joinFields(fn(splitFields(flds))),
                      intTime(), self.manager.col.usn(), id))
        self.manager.col.db.executemany(
            "update notes set flds=?,mod=?,usn=? where id = ?", notesUpdates)

    def _updateFieldOrds(self):
        """
        Change the order of the field of the model in order to copy
        the order in model['flds'].

        Keyword arguments
        model -- a model"""
        for index, fieldType in enumerate(self['flds']):
            fieldType['ord'] = index

    def useCount(self):
        """Number of note using the model model.

        Keyword arguments
        model -- a model object."""
        return self.manager.col.db.scalar(
            "select count() from notes where mid = ?", self.getId())

    def getTemplate(self, which):
        if isinstance(which, int):
            return self._getTemplateByOrd(which)
        elif isinstance(which, str):
            return self._getTemplateByName(which)
        assert (False)

    def _getTemplateByOrd(self, ord):
        return self['tmpls'].get(ord)

    def _getTemplateByName(self, name):
        for tmpl in self['tmpls']:
            if tmpl['name'] == name:
                return tmpl
        return None

    def getField(self, which):
        if isinstance(which, int):
            return self._getFieldByOrd(which)
        elif isinstance(which, str):
            return self._getFieldByName(which)
        assert (False)

    def _getFieldByOrd(self, ord):
        return self['tmpls'].get(ord)

    def _getFieldByName(self, name):
        for tmpl in self['tmpls']:
            if tmpl['name'] == name:
                return tmpl
        return None

    def isStd(self):
        return self['type'] == MODEL_STD:

    def isCloze(self):
        return self['type'] == MODEL_CLOZE:

    # Copying
    ##################################################

    def copy(self):
        "A copy of model, already in the collection."
        m2Dict = copy.deepcopy(self.dic)
        m2Dict['name'] = _("%s copy") % m2['name']
        model = Model(self.manager, m2Dict)
        m2Dict['tmpls'] = map(lambda template: template.copy(model), m2Dict['tmpls'])
        m2Dict['flds'] = map(lambda field: field.copy(model), m2Dict['tmpls'])
        self.manager.add(model)
        return model

    # Fields
    ##################################################

    def fieldMap(self):
        """Mapping of (field name) -> (ord, field object).

        keyword arguments:
        model : a model
        """
        return dict((fieldType['name'], (fieldType['ord'], fieldType)) for fieldType in self['flds'])

    def fieldNames(self):
        """The list of names of fields of this model."""
        return [fieldType['name'] for fieldType in self['flds']]

    def sortIdx(self):
        """The index of the field used for sorting."""
        return self['sortf']

    def setSortIdx(self, idx):
        """State that the id of the sorting field of the model is idx.

        Mark the model as modified, change the cache.
        Keyword arguments
        idx -- the identifier of a field
        """
        assert 0 <= idx < len(self['flds'])
        self.manager.col.modSchema(check=True)
        self['sortf'] = idx
        self.manager.col.updateFieldCache(self.nids())
        self.save()

    def newTemplate(self, name):
        return Template(self, name=name)

    def newField(self, name):
        return Field(self, name=name)

    # Model changing
    ##########################################################################
    # - maps are ord->ord, and there should not be duplicate targets
    # - newModel should be self if model is not changing

    def change(self, oldModel, nids, fmap, cmap):
        """Change the model of the nodes in nids to self

        currently, fmap and cmap are null only for tests.

        keyword arguments
        oldModel -- the previous oldModel of the notes
        nids -- a list of id of notes whose oldModel is oldModel
        self -- the model to which the cards must be converted
        fmap -- the dictionnary sending to each fields'ord of the old model a field'ord of the new model
        cmap -- the dictionnary sending to each card type's ord of the old model a card type's ord of the new model
        """
        self.manager.col.modSchema(check=True)
        assert self['id'] == oldModel['id'] or (fmap and cmap)
        if fmap:
            self._changeNotes(nids, fmap)
        if cmap:
            self._changeCards(nids, oldModel, cmap)
        self.manager.col.genCards(nids)

    def _changeNotes(self, nids, map):
        """Change the note whose ids are nid to the model self, reorder
        fields according to map. Write the change in the database

        Note that if a field is mapped to nothing, it is lost

        keyword arguments:
        nids -- the list of id of notes to change
        newmodel -- the model of destination of the note
        map -- the dictionnary sending to each fields'ord of the old model a field'ord of the new model
        """
        noteData = []
        #The list of dictionnaries, containing the information relating to the new cards
        nfields = len(self['flds'])
        for (nid, flds) in self.manager.col.db.execute(
            "select id, flds from notes where id in "+ids2str(nids)):
            newflds = {}
            flds = splitFields(flds)
            for old, new in list(map.items()):
                newflds[new] = flds[old]
            flds = []
            for index in range(nfields):
                flds.append(newflds.get(index, ""))
            flds = joinFields(flds)
            noteData.append(dict(nid=nid, flds=flds, mid=self['id'],
                      mod=intTime(),usn=self.manager.col.usn()))
        self.manager.col.db.executemany(
            "update notes set flds=:flds,mid=:mid,mod=:mod,usn=:usn where id = :nid", noteData)
        self.manager.col.updateFieldCache(nids)

    def _changeCards(self, nids, oldModel, map):
        """Change the note whose ids are nid to the model self, reorder
        fields according to map. Write the change in the database

        Remove the cards mapped to nothing

        If the source is a cloze, it is (currently?) mapped to the
        card of same order in self, independtly of map.

        keyword arguments:
        nids -- the list of id of notes to change
        oldModel -- the soruce model of the notes
        newmodel -- the model of destination of the notes
        map -- the dictionnary sending to each card 'ord of the old model a card'ord of the new model or to None
        """
        cardData = []
        deleted = []
        for (cid, ord) in self.manager.col.db.execute(
            "select id, ord from cards where nid in "+ids2str(nids)):
            # if the src model is a cloze, we ignore the map, as the gui
            # doesn't currently support mapping them
            if oldModel['type'] == MODEL_CLOZE:
                new = ord
                if self['type'] != MODEL_CLOZE:
                    # if we're mapping to a regular note, we need to check if
                    # the destination ord is valid
                    if len(newModel['tmpls']) <= ord:
                        new = None
            else:
                # mapping from a regular note, so the map should be valid
                new = map[ord]
            if new is not None:
                cardData.append(dict(
                    cid=cid,new=new,usn=self.manager.col.usn(),mod=intTime()))
            else:
                deleted.append(cid)
        self.manager.col.db.executemany(
            "update cards set ord=:new,usn=:usn,mod=:mod where id=:cid",
            cardData)
        self.manager.col.remCards(deleted)
