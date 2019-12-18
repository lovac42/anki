import re
from typing import Any, Dict

from anki.utils import DictAugmentedInModel

defaultField: Dict[str, Any] = {
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

class Field(DictAugmentedInModel):
    """Field are not necessarily in the model. If they are not, method add
    must be used to add them.  Only use them once the field is
    entirely configured (so that compilation of req is done correction
    for example)

    """

    def new(self, manager, name):
        """A new field, similar to the default one, whose name is name."""
        super().new(manager, name, defaultField)

    def add(self):
        """Append the field field as last element of the model model.
        todo
        Keyword arguments
        """
        # only mod schema if model isn't new
        if self.model['id']:
            self.model.manager.col.modSchema(check=True)
        self.model['flds'].append(self)
        self.model._updateFieldOrds()
        def add(fieldsContents):
            fieldsContents.append("")
            return fieldsContents
        self.model._transformFields(add)
        self.reqIfName()
        self.model.save(updateReqs=False)

    def reqIfName(self):
        """Recompute req for templates containing this field.

        Since the field may be included in plenty of different way, I
        just check for the field naem and not for {{.

        used when a field is aded or renamed, because the field may actually already be in templates.
        """
        for template in self.model['tmpls']:
            if self.getName() in template['qfmt']:
                template.setReq()

    def rename(self, newName):
        """Rename the field. In each template, find the mustache related to
        this field and change them.
        field -- the field dictionnary
        newName -- either a name. Or None if the field is deleted.
        """
        self.model.manager.col.modSchema(check=True)
        #Regexp associating to a mustache the name of its field
        pat = r'{{([^{}]*)([:#^/]|[^:#/^}][^:}]*?:|)%s}}'
        def repl(match):
            if newName is None:
                return ""
            else:
                return '{{' + match.group(1) + match.group(2) + newName +  '}}'
        def newTemplate(txt):
            return re.sub(pat % re.escape(self.getName()), repl, txt)
        for template in self.model['tmpls']:
            template.changeTemplates(
                newTemplate(template['qfmt']),
                newTemplate(template['afmt']))
        if newName is not None:
            self.setName(newName)
            self.reqIfName()
        self.model.save(updateReqs=False)

    def move(self, newIdx):
        """Move the field to position newIdx
        newIdx -- new position, integer
        field -- a field object
        """
        self.model.manager.col.modSchema(check=True)
        oldidx = self.model['flds'].index(self)
        if oldidx == newIdx:
            return
        # remember old sort self
        sortf = self.model['flds'][self.model['sortf']]
        # move
        self.model['flds'].remove(self)
        self.model['flds'].insert(newIdx, self)
        # restore sort self
        self.model['sortf'] = self.model['flds'].index(sortf)
        self.model._updateFieldOrds()
        self.model.save(updateReqs=False)
        def move(fields, oldidx=oldidx):
            val = fields[oldidx]
            del fields[oldidx]
            fields.insert(newIdx, val)
            return fields
        self.model._transformFields(move)

    def rem(self):
        """Remove a field from a model.
        Also remove it from each note of this model
        Move the position of the sortfield. Update the position of each field.
        Modify the template
        model -- the model
        field -- the field object"""
        self.model.manager.col.modSchema(check=True)
        # save old sort field
        sortFldName = self.model['flds'][self.model['sortf']].getName()
        idx = self.model['flds'].index(self)
        self.model['flds'].remove(self)
        # restore old sort field if possible, or revert to first field
        self.model['sortf'] = 0
        for index, fieldType in enumerate(self.model['flds']):
            if fieldType.getName() == sortFldName:
                self.model['sortf'] = index
                break
        self.model._updateFieldOrds()
        def delete(fieldsContents):
            del fieldsContents[idx]
            return fieldsContents
        self.model._transformFields(delete)
        if self.model['flds'][self.model['sortf']].getName() != sortFldName:
            # need to rebuild sort field
            self.model.manager.col.updateFieldCache(self.model.nids())
        # saves
        self.rename(None)
