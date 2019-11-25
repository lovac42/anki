import re

from anki.utils import DictAugmentedInModel

class Field(DictAugmentedInModel):
    """Field may not be in model, and will be added later by add method"""
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
        self.model.save()
        def add(fieldsContents):
            fieldsContents.append("")
            return fieldsContents
        self.model._transformFields(add)

    def new(self, name):
        """A new field, similar to the default one, whose name is name."""
        super().new(name, name, defaultField)

    def rem(self):
        """Remove a field from a model.
        Also remove it from each note of this model
        Move the position of the sortfield. Update the position of each field.

        Modify the template

        model -- the model
        field -- the field object"""
        self.model.manager.col.modSchema(check=True)
        # save old sort field
        sortFldName = self.model['flds'][self.model['sortf']]['name']
        idx = self.model['flds'].index(self)
        self.model['flds'].remove(self)
        # restore old sort field if possible, or revert to first field
        self.model['sortf'] = 0
        for index, fieldType in enumerate(self.model['flds']):
            if fieldType['name'] == sortFldName:
                self.model['sortf'] = index
                break
        self.model._updateFieldOrds()
        def delete(fieldsContents):
            del fieldsContents[idx]
            return fieldsContents
        self.model._transformFields(delete)
        if self.model['flds'][self.model['sortf']]['name'] != sortFldName:
            # need to rebuild sort field
            self.model.manager.col.updateFieldCache(self.model.nids())
        # saves
        self.rename(None)

    def rename(self, newName):
        """Rename the field. In each template, find the mustache related to
        this field and change them.

        field -- the field dictionnary
        newName -- either a name. Or None if the field is deleted.

        """
        self.model.manager.col.modSchema(check=True)
        #Regexp associating to a mustache the name of its field
        pat = r'{{([^{}]*)([:#^/]|[^:#/^}][^:}]*?:|)%s}}'
        def wrap(txt):
            def repl(match):
                return '{{' + match.group(1) + match.group(2) + txt +  '}}'
            return repl
        for template in self.model['tmpls']:
            for fmt in ('qfmt', 'afmt'):
                if newName:
                    template[fmt] = re.sub(
                        pat % re.escape(self['name']), wrap(newName), template[fmt])
                else:
                    template[fmt] = re.sub(
                        pat  % re.escape(self['name']), "", template[fmt])
       self['name'] = newName
       self.model.save()

    def move(self, idx):
        """Move the field to position idx

        idx -- new position, integer
        field -- a field object
        """
        self.model.manager.col.modSchema(check=True)
        oldidx = self.model['flds'].index(self)
        if oldidx == idx:
            return
        # remember old sort self
        sortf = self.model['flds'][self.model['sortf']]
        # move
        self.model['flds'].remove(self)
        self.model['flds'].insert(idx, self)
        # restore sort self
        self.model['sortf'] = self.model['flds'].index(sortf)
        self.model._updateFieldOrds()
        self.model()
        def move(fields, oldidx=oldidx):
            val = fields[oldidx]
            del fields[oldidx]
            fields.insert(idx, val)
            return fields
        self.model._transformFields(move)
