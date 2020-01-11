import time

from anki.lang import _
from anki.utils import formatDay, formatMinute, strftimeIfArgument


class BrowserColumn:
    """
    type -- the internal name of the column in the list of columns
    name -- the (translated) name of the column
    note -- whether this show informations relative to note. Otherwise it's to the card.
    sort -- the text to use in finder to sort by this column. None means this columns can't be sorted.
    menu -- the list of submenus of context menu in which this column is
    """
    defaultSort = "note.id, card.ord"
    def __init__(self, type, name, menu=True, sort=None, note=None):
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
        if menu is True:
            menu = ["Note"] if self.note else ["Card"]
        assert(isinstance(menu, list))
        self.menus = [menu]

    def getBase(self, card):
        if self.note:
            return card.note()
        else:
            return card

    defaultSort = "note.id, card.ord"
    def getSort(self):
        return self.sort

    def __eq__(self, other):
        return self.type == other.type and self.name == other.name and self.__class__ == other.__class__

    def addMenu(self, menu):
        self.menus.append(menu)

class ColumnByMethod(BrowserColumn):
    """
    methodName -- a method in the class card/note according to self.note.
    """
    def __init__(self, type, name, sort=None, methodName=None, menu=True, note=None, *args, **kwargs):
        """All methods names ends with BrowserColumn. Only the part before has to be given.
        If methodName is not indicated, then it's assumed to be the same as
        type. Except if it starts with card or note, in which case
        those four letters are omitted, and the next letter is put in
        lower case.
        """
        self.args = args
        self.kwargs = kwargs
        if sort is None:
            sort = BrowserColumn.defaultSort
        super().__init__(type, name, menu, sort, note)
        if methodName is not None:
            self.methodName = methodName
        else:
            if type.startswith("note") or type.startswith("card"):
                self.methodName = type[4].lower() + type[5:]
            else:
                self.methodName = type
            self.methodName +=  "BrowserColumn"

    def content(self, card):
        return getattr(self.getBase(card), self.methodName)(*self.args, **self.kwargs)


class DateColumnFromQuery(BrowserColumn):
    def __init__(self, type, name, query, browserModel, menu=True):
        self.query = query
        self.browserModel = browserModel
        super().__init__(type, name, menu, sort=query)

    def content(self, card):
        base =self.getBase(card)
        object = "notes note" if self.note else "cards card"
        time = base.col.db.scalar(f"select {self.query} from {object} where id = ?", base.id)
        return formatMinute(time) if self.browserModel.minutes else formatDay(time)

    def getSort(self):
        return f"{self.query}, card.ord" #second is useless to sort card. Useful for notes

class TimeColumnFromQuery(BrowserColumn):
    def __init__(self, type, name, sort, limit=False):
        super().__init__(type, name, sort=sort, note=False, menu=True)
        self.limit = limit

    def content(self, card):
        return strftimeIfArgument(card.col.db.scalar(f"select {self.sort} from revlog where cid = ?"+(" limit 1" if self.limit else ""), card.id))

    def getSort(self):
        return f"(select {self.sort} from revlog where cid = card.id)"

class ColumnAttribute(BrowserColumn):
    def __init__(self, type, name, attribute=None, note=None):
        if attribute is None:
            attribute = type[1:]
        self.attribute = attribute
        if note is None:
            if type[0] == "n":
                note = True
            else:
                assert type[0] == 'c'
                note = False
        sort = ("note" if note else "card") + "." + attribute
        super().__init__(type, name, sort=sort, note=note)

    def content(self, card):
        return getattr(self.getBase(card), self.attribute)

    def getSort(self):
        return ("note" if self.note else "card") + "." + self.attribute

class UselessColumn(BrowserColumn):
    def __init__(self, type):
        super().__init__(type, _(type))

    def content(self, card):
        return ""
