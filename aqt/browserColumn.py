import time

from anki.utils import formatDay


class BrowserColumn:
    """
    type -- the internal name of the column in the list of columns
    name -- the (translated) name of the column
    note -- whether this show informations relative to note. Otherwise it's to the card.
    sort -- the text to use in finder to sort by this column. None means this columns can't be sorted.
    """
    defaultSort = "note.id, card.ord"
    def __init__(self, type, name, sort=None, note=None):
        """All methods names ends with BrowserColumn. Only the part before has to be given.
        If methodName is not indicated, then it's assumed to be the same as
        type. Except if it starts with card or note, in which case
        those four letters are omitted, and the next letter is put in
        lower case.

        if note is not set, then we assume that it's note related iff the type starts with "note".
        """
        if note is None:
            note = type.startswith("note")
        self.type = type
        self.name = name
        self.note = note
        if sort is None:
            sort = self.defaultSort
        self.sort = sort

    def getBase(self, card):
        if self.note:
            return card.note()
        else:
            return card

    defaultSort = "note.id, card.ord"
    def getSort(self):
        return self.sort
            

class ColumnByMethod(BrowserColumn):
    """
    methodName -- a method in the class card/note according to self.note.
    """
    def __init__(self, type, name, sort=None, methodName=None, note=None):
        """All methods names ends with BrowserColumn. Only the part before has to be given.
        If methodName is not indicated, then it's assumed to be the same as
        type. Except if it starts with card or note, in which case
        those four letters are omitted, and the next letter is put in
        lower case.

        """
        super().__init__(type, name, sort, note)
        if methodName is not None:
            self.methodName = methodName
        else:
            if type.startswith("note") or type.startswith("card"):
                self.methodName = type[4].lower() + type[5:]
            else:
                self.methodName = type
            self.methodName +=  "BrowserColumn"

    def content(self, card):
        return getattr(self.getBase(card), self.methodName)()


class DateColumnFromQuery(BrowserColumn):
    def __init__(self, type, name, query):
        self.query = query
        super().__init__(type, name, sort=query)

    def content(self, card):
        base =self.getBase(card)
        object = "notes note" if self.note else "cards card"
        return formatDay(base.col.db.scalar(f"select {self.query} from {object} where id = ?", base.id))

    def getSort(self):
        return f"{self.query}, card.ord" #second is useless to sort card. Useful for notes
