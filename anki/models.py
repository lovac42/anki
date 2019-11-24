# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import copy
import json
import re
import time

from anki.consts import *
from anki.hooks import runHook
from anki.lang import _
from anki.utils import checksum, ids2str, intTime, joinFields, splitFields

"""This module deals with models, known as note type in Anki's documentation.

A model is composed of:
css -- CSS, shared for all templates of the model
did -- Long specifying the id of the deck that cards are added to by
default
flds -- JSONArray containing object for each field in the model. See flds
id -- model ID, matches notes.mid
latexPost -- String added to end of LaTeX expressions (usually \\end{document}),
latexPre -- preamble for LaTeX expressions,
mod -- modification time in milliseconds,
name -- the name of the model,
req -- Array of arrays describing which fields are required. See req
sortf -- Integer specifying which field is used for sorting in the
browser,
tags -- Anki saves the tags of the last added note to the current
model, use an empty array [],
tmpls -- The list of templates. See below
      -- In db:JSONArray containing object of CardTemplate for each card in
model.
type -- Integer specifying what type of model. 0 for standard, 1 for
cloze,
usn -- Update sequence number: used in same way as other usn vales in
db,
vers -- Legacy version number (unused), use an empty array []
changed -- Whether the Model has been changed and should be written in
the database."""


"""A field object (flds) is an array composed of:
font -- "display font",
media -- "array of media. appears to be unused",
name -- "field name",
ord -- "ordinal of the field - goes from 0 to num fields -1",
rtl -- "boolean, right-to-left script",
size -- "font size",
sticky -- "sticky fields retain the value that was last added
when adding new notes" """

"""req' fields are:
"the 'ord' value of the template object from the 'tmpls' array you are setting the required fields of",
'? string, "all" or "any"',
["? another array of 'ord' values from field object you
want to require from the 'flds' array"]"""


"""tmpls (a template): a dict with
afmt -- "answer template string",
bafmt -- "browser answer format:
used for displaying answer in browser",
bqfmt -- "browser question format:
used for displaying question in browser",
did -- "deck override (null by default)",
name -- "template name",
ord -- "template number, see flds",
qfmt -- "question format string"
"""


# Models
##########################################################################

# - careful not to add any lists/dicts/etc here, as they aren't deep copied

defaultModel = {
    'sortf': 0,
    'did': 1,
    'latexPre': """\
\\documentclass[12pt]{article}
\\special{papersize=3in,5in}
\\usepackage[utf8]{inputenc}
\\usepackage{amssymb,amsmath}
\\pagestyle{empty}
\\setlength{\\parindent}{0in}
\\begin{document}
""",
    'latexPost': "\\end{document}",
    'mod': 0,
    'usn': 0,
    'vers': [], # FIXME: remove when other clients have caught up
    'type': MODEL_STD,
    'css': """\
.card {
 font-family: arial;
 font-size: 20px;
 text-align: center;
 color: black;
 background-color: white;
}
"""
}

defaultField = {
    'name': "",
    'ord': None,
    'sticky': False,
    # the following alter editing, and are used as defaults for the
    # template wizard
    'rtl': False,
    'font': "Arial",
    'size': 20,
    # reserved for future use
    'media': [],
}

defaultTemplate = {
    'name': "",
    'ord': None,
    'qfmt': "",
    'afmt': "",
    'did': None,
    'bqfmt': "",
    'bafmt': "",
    # we don't define these so that we pick up system font size until set
    #'bfont': "Arial",
    #'bsize': 12,
}

class ModelManager:

    """This object is usually denoted mm as a variable. Or .models in
    collection."""
    # Saving/loading registry
    #############################################################

    def __init__(self, col):
        """Returns a ModelManager whose collection is col."""
        self.col = col

    def load(self, json_):
        "Load registry from JSON."
        self.changed = False
        self.models = dict()
        for id, dic in json.loads(json_):
            self.models[id] = Model(self, dic)

    def save(self, model=None, templates=False):
        """
        * Mark model modified if provided.
        * Schedule registry flush.
        * Calls hook newModel

        Keyword arguments:
        model -- A Model
        templates -- whether to check for cards not generated in this model
        """
        if model:
            model.save(template=template, saveManager=False)
        self.changed = True
        runHook("newModel") # By default, only refresh side bar of browser

    def flush(self):
        "Flush the registry if any models were changed."
        if self.changed:
            self.ensureNotEmpty()
            self.col.db.execute("update col set models = ?",
                                 json.dumps(self.models, default=lambda model: model.dumps()))
            self.changed = False

    def ensureNotEmpty(self):
        if not self.models:
            from anki.stdmodels import addBasicModel
            addBasicModel(self.col)
            return True

    # Retrieving and creating models
    #############################################################

    def current(self, forDeck=True):
        """Get current model.

        This mode is first considered using the current deck's mid, if
        forDeck is true(default).

        Otherwise, the curModel configuration value is used.

        Otherwise, the first model is used.

        Keyword arguments:
        forDeck -- Whether the model of the deck should be considered; assuming it exists."""
        "Get current model."
        model = self.col.decks.current().getModel()
        if not forDeck or not model:
            model = self.get(self.col.conf['curModel'])
        return model or list(self.models.values())[0]

    def get(self, id):
        "Get model object with ID, or None."
        id = str(id)
        if id in self.models:
            return self.models[id]

    def all(self, type=None):
        """Get all model objects.

        type -- standard or cloze. Restrcit to those models
        """
        models = self.models.values()
        if type is not None:
            models = filter(lambda model: model['type'] == type, models)
        return models

    def allNames(self, type=None):
        """Get all model names.

        type -- standard or cloze. Restrcit to those models
        """
        return map(lambda model:model['name'], self.all(type=type))

    def byName(self, name):
        """Get model whose name is name.

        keyword arguments
        name -- the name of the wanted model."""
        for model in list(self.models.values()):
            if model['name'] == name:
                return model

    def new(name):
        "Create a new model, save it in the registry, and return it."
        # caller should call save() after modifying
        return Model(self, name=name)

    def add(self, model):
        """Add a new model model in the database of models"""
        model._setID()
        model.update()
        model.setCurrent()
        self.save(model)

    def have(self, id):
        """Whether there exists a model whose id is did."""
        return str(id) in self.models

    def ids(self):
        """The list of id of models"""
        return list(self.models.keys())

    # Fields
    ##################################################

    @staticmethod
    def newField(name):
        """A new field, similar to the default one, whose name is name."""
        fieldType = defaultField.copy()
        fieldType['name'] = name
        return fieldType

    @staticmethod
    def fieldMap(model):
        """Mapping of (field name) -> (ord, field object).

        keyword arguments:
        model : a model
        """
        return dict((fieldType['name'], (fieldType['ord'], fieldType)) for fieldType in model['flds'])

    @staticmethod
    def fieldNames(model):
        """The list of names of fields of this model."""
        return [fieldType['name'] for fieldType in model['flds']]

    @staticmethod
    def sortIdx(model):
        """The index of the field used for sorting."""
        return model['sortf']

    def setSortIdx(self, model, idx):
        """State that the id of the sorting field of the model is idx.

        Mark the model as modified, change the cache.
        Keyword arguments
        model -- a model
        idx -- the identifier of a field
        """
        assert 0 <= idx < len(model['flds'])
        self.col.modSchema(check=True)
        model['sortf'] = idx
        self.col.updateFieldCache(model.nids())
        self.save(model)

    def addField(self, model, fieldType):
        """Append the field field as last element of the model model.

        todo

        Keyword arguments
        model -- a model
        field -- a field object
        """
        # only mod schema if model isn't new
        if model['id']:
            self.col.modSchema(check=True)
        model['flds'].append(fieldType)
        model._updateFieldOrds()
        self.save(model)
        def add(fieldsContents):
            fieldsContents.append("")
            return fieldsContents
        model._transformFields(add)

    def remField(self, model, fieldTypeToRemove):
        """Remove a field from a model.
        Also remove it from each note of this model
        Move the position of the sortfield. Update the position of each field.

        Modify the template

        model -- the model
        field -- the field object"""
        self.col.modSchema(check=True)
        # save old sort field
        sortFldName = model['flds'][model['sortf']]['name']
        idx = model['flds'].index(fieldTypeToRemove)
        model['flds'].remove(fieldTypeToRemove)
        # restore old sort field if possible, or revert to first field
        model['sortf'] = 0
        for index, fieldType in enumerate(model['flds']):
            if fieldType['name'] == sortFldName:
                model['sortf'] = index
                break
        model._updateFieldOrds()
        def delete(fieldsContents):
            del fieldsContents[idx]
            return fieldsContents
        model._transformFields(delete)
        if model['flds'][model['sortf']]['name'] != sortFldName:
            # need to rebuild sort field
            self.col.updateFieldCache(model.nids())
        # saves
        self.renameField(model, fieldTypeToRemove, None)

    def moveField(self, model, fieldType, idx):
        """Move the field to position idx

        idx -- new position, integer
        field -- a field object
        """
        self.col.modSchema(check=True)
        oldidx = model['flds'].index(fieldType)
        if oldidx == idx:
            return
        # remember old sort fieldType
        sortf = model['flds'][model['sortf']]
        # move
        model['flds'].remove(fieldType)
        model['flds'].insert(idx, fieldType)
        # restore sort fieldType
        model['sortf'] = model['flds'].index(sortf)
        model._updateFieldOrds()
        self.save(model)
        def move(fields, oldidx=oldidx):
            val = fields[oldidx]
            del fields[oldidx]
            fields.insert(idx, val)
            return fields
        model._transformFields(move)

    def renameField(self, model, fieldType, newName):
        """Rename the field. In each template, find the mustache related to
        this field and change them.

        model -- the model dictionnary
        field -- the field dictionnary
        newName -- either a name. Or None if the field is deleted.

        """
        self.col.modSchema(check=True)
        #Regexp associating to a mustache the name of its field
        pat = r'{{([^{}]*)([:#^/]|[^:#/^}][^:}]*?:|)%s}}'
        def wrap(txt):
            def repl(match):
                return '{{' + match.group(1) + match.group(2) + txt +  '}}'
            return repl
        for template in model['tmpls']:
            for fmt in ('qfmt', 'afmt'):
                if newName:
                    template[fmt] = re.sub(
                        pat % re.escape(fieldType['name']), wrap(newName), template[fmt])
                else:
                    template[fmt] = re.sub(
                        pat  % re.escape(fieldType['name']), "", template[fmt]) 
       fieldType['name'] = newName
        self.save(model)

    # Templates
    ##################################################

    @staticmethod
    def newTemplate(name):
        """A new template, whose content is the one of
        defaultTemplate, and name is name.

        It's used in order to import mnemosyn, and create the standard
        model during anki's first initialization. It's not used in day to day anki.
        """
        template = defaultTemplate.copy()
        template['name'] = name
        return template

    def addTemplate(self, model, template):
        """Add a new template in model, as last element. This template is a copy
        of the input template
        """
        if model['id']:
            self.col.modSchema(check=True)
        model['tmpls'].append(template)
        model._updateTemplOrds()
        self.save(model)

    def moveTemplate(self, model, template, idx):
        """Move input template to position idx in model.

        Move also every other template to make this consistent.

        Comment again after that TODODODO
        """
        oldidx = model['tmpls'].index(template)
        if oldidx == idx:
            return
        oldidxs = dict((id(template), template['ord']) for template in model['tmpls'])
        model['tmpls'].remove(template)
        model['tmpls'].insert(idx, template)
        model._updateTemplOrds()
        # generate change map
        map = []
        for template in model['tmpls']:
            map.append("when ord = %d then %d" % (oldidxs[id(template)], template['ord']))
        # apply
        self.save(model)
        self.col.db.execute("""
update cards set ord = (case %s end),usn=?,mod=? where nid in (
select id from notes where mid = ?)""" % " ".join(map),
                             self.col.usn(), intTime(), model['id'])

    # Model changing
    ##########################################################################
    # - maps are ord->ord, and there should not be duplicate targets
    # - newModel should be self if model is not changing

    def change(self, model, nids, newModel, fmap, cmap):
        """Change the model of the nodes in nids to newModel

        currently, fmap and cmap are null only for tests.

        keyword arguments
        model -- the previous model of the notes
        nids -- a list of id of notes whose model is model
        newModel -- the model to which the cards must be converted
        fmap -- the dictionnary sending to each fields'ord of the old model a field'ord of the new model
        cmap -- the dictionnary sending to each card type's ord of the old model a card type's ord of the new model
        """
        self.col.modSchema(check=True)
        assert newModel['id'] == model['id'] or (fmap and cmap)
        if fmap:
            self._changeNotes(nids, newModel, fmap)
        if cmap:
            self._changeCards(nids, model, newModel, cmap)
        self.col.genCards(nids)

    def _changeNotes(self, nids, newModel, map):
        """Change the note whose ids are nid to the model newModel, reorder
        fields according to map. Write the change in the database

        Note that if a field is mapped to nothing, it is lost

        keyword arguments:
        nids -- the list of id of notes to change
        newmodel -- the model of destination of the note
        map -- the dictionnary sending to each fields'ord of the old model a field'ord of the new model
        """
        noteData = []
        #The list of dictionnaries, containing the information relating to the new cards
        nfields = len(newModel['flds'])
        for (nid, flds) in self.col.db.execute(
            "select id, flds from notes where id in "+ids2str(nids)):
            newflds = {}
            flds = splitFields(flds)
            for old, new in list(map.items()):
                newflds[new] = flds[old]
            flds = []
            for index in range(nfields):
                flds.append(newflds.get(index, ""))
            flds = joinFields(flds)
            noteData.append(dict(nid=nid, flds=flds, mid=newModel['id'],
                      mod=intTime(),usn=self.col.usn()))
        self.col.db.executemany(
            "update notes set flds=:flds,mid=:mid,mod=:mod,usn=:usn where id = :nid", noteData)
        self.col.updateFieldCache(nids)

    def _changeCards(self, nids, oldModel, newModel, map):
        """Change the note whose ids are nid to the model newModel, reorder
        fields according to map. Write the change in the database

        Remove the cards mapped to nothing

        If the source is a cloze, it is (currently?) mapped to the
        card of same order in newModel, independtly of map.

        keyword arguments:
        nids -- the list of id of notes to change
        oldModel -- the soruce model of the notes
        newmodel -- the model of destination of the notes
        map -- the dictionnary sending to each card 'ord of the old model a card'ord of the new model or to None
        """
        cardData = []
        deleted = []
        for (cid, ord) in self.col.db.execute(
            "select id, ord from cards where nid in "+ids2str(nids)):
            # if the src model is a cloze, we ignore the map, as the gui
            # doesn't currently support mapping them
            if oldModel['type'] == MODEL_CLOZE:
                new = ord
                if newModel['type'] != MODEL_CLOZE:
                    # if we're mapping to a regular note, we need to check if
                    # the destination ord is valid
                    if len(newModel['tmpls']) <= ord:
                        new = None
            else:
                # mapping from a regular note, so the map should be valid
                new = map[ord]
            if new is not None:
                cardData.append(dict(
                    cid=cid,new=new,usn=self.col.usn(),mod=intTime()))
            else:
                deleted.append(cid)
        self.col.db.executemany(
            "update cards set ord=:new,usn=:usn,mod=:mod where id=:cid",
            cardData)
        self.col.remCards(deleted)

    # Sync handling
    ##########################################################################

    def beforeUpload(self):
        for model in self.all():
            model.beforeUpload()
        self.save()

class Model(DictAugmented):
    def __init__(self, manager, dic=None, name=None):
        if dict:
            self.load(manager, dic)
        else:
            self.new(manager, name)

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

    def save(self, template=False, saveManager=False):
        """
        * Mark model modified.
        * Schedule registry flush if saveManager

        Keyword arguments:
        model -- A Model
        templates -- whether to check for cards not generated in this model
        """
        if self.getId():
            model['mod'] = intTime()
            model['usn'] = self.col.usn()
            model._updateRequired(model)
            if templates:
                model._syncTemplates()

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

    def beforeUpload(self):
        self['usn'] = 0

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
        map = self.manager.fieldMap(self)
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
        """For each note of the model model, apply model to the set of field's value,
        and save the note modified.

        fn -- a function taking and returning a list of field."""
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

class Template(DictAugmented):
    def __init__(self, model, dic):
        self.model = model
        self.dic = dic

    # Required field/text cache
    ##########################################################################

    def _reqForTemplate(self, flds):
        """A rule which is supposed to determine whether a card should be
        generated or not according to its fields.

        See ../documentation/templates_generation_rules.md

        """
        ankiflagFlds = ["ankiflag"] * len(flds)
        emptyFlds = [""] * len(flds)
        data = [1, 1, self.self.getId(), 1, self['ord'], "", joinFields(ankiflagFlds), 0]
        # The html of the card at position ord where each field's content is "ankiflag"
        full = self.model.manager.col._renderQA(data)['q']
        data = [1, 1, self.self.getId(), 1, self['ord'], "", joinFields(emptyFlds), 0]
        # The html of the card at position ord where each field's content is the empty string ""
        empty = self.model.manager.col._renderQA(data)['q']

        # if full and empty are the same, the self is invalid and there is
        # no way to satisfy it
        if full == empty:
            return "none", [], []
        type = 'all'
        req = []
        for i in range(len(flds)):
            tmp = ankiflagFlds[:]
            tmp[i] = ""
            data[6] = joinFields(tmp)
            # if no field content appeared, field is required
            if "ankiflag" not in self.model.manager.col._renderQA(data)['q']:
                req.append(i)
        if req:
            return type, req
        # if there are no required fields, switch to any mode
        type = 'any'
        req = []
        for i in range(len(flds)):
            tmp = emptyFlds[:]
            tmp[i] = "1"
            data[6] = joinFields(tmp)
            # if not the same as empty, this field can make the card non-blank
            if self.model.manager.col._renderQA(data)['q'] != empty:
                req.append(i)
        return type, req

    def rem(self):
        """Remove the input template from the model model.

        Return False if removing template would leave orphan
        notes. Otherwise True
        """
        assert len(self.model['tmpls']) > 1
        # find cards using this template
        ord = self.model['tmpls'].index(template)
        cids = self.model.manager.col.db.list("""
select card.id from cards card, notes note where card.nid=note.id and mid = ? and ord = ?""",
                                 self.self.getId(), ord)
        # all notes with this template must have at least two cards, or we
        # could end up creating orphaned notes
        if self.model.manager.col.db.scalar("""
select nid, count() from cards where
nid in (select nid from cards where id in %s)
group by nid
having count() < 2
limit 1""" % ids2str(cids)):
            return False
        # ok to proceed; remove cards
        self.model.manager.col.modSchema(check=True)
        self.model.manager.col.remCards(cids)
        # shift ordinals
        self.model.manager.col.db.execute("""
update cards set ord = ord - 1, usn = ?, mod = ?
 where nid in (select id from notes where mid = ?) and ord > ?""",
                             self.model.manager.col.usn(), intTime(), self.self.getId(), ord)
        self.model['tmpls'].remove(template)
        self.model._updateTemplOrds()
        self.model.save(True)
        return True

    # Tools
    ##################################################

    def tmplUseCount(self):
        """The number of cards which used template number ord of the
        model obj.

        Keyword arguments
        model -- a model object."""
        return self.col.db.scalar("""
select count() from cards, notes where cards.nid = notes.id
and notes.mid = ? and cards.ord = ?""", self.model['id'], self['ord'])

    def copy(self, model):
        return Template(model, copy.deepcopy(self.dic))

class Field(DictAugmented):
    def __init__(self, model, dic):
        self.model = model
        self.dic = dic

    def copy(self, model):
        return Field(model, copy.deepcopy(self.dic))
