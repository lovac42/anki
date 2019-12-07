class BrowserColumn:
    """
    type -- the internal name of the column in the list of columns
    name -- the (translated) name of the column
    note -- whether this show informations relative to note. Otherwise it's to the card.
    methodName -- a method in the class card/note according to self.note.
    """
    def __init__(self, type, name, methodName=None, note=None):
        """All methods names ends with BrowserColumn. Only the part before has to be given.
        If methodName is not indicated, then it's assumed to be the same as
        type. Except if it starts with card or note, in which case
        those four letters are omitted, and the next letter is put in
        lower case.

        if note is not set, then we assume that it's note related iff the type starts with "note".
        """
        self.type = type
        self.name = name
        if methodName is not None:
            self.methodName = methodName
        else:
            if type.startswith("note") or type.startswith("card"):
                self.methodName = type[4].lower() + type[5:]
            else:
                self.methodName = type
        self.methodName +=  "BrowserColumn"
        if note is not None:
            self.note = note
        else:
            self.note = type.startswith("note")

    def content(self, card):
        if self.note:
            base = card.note()
        else:
            base = card
        return getattr(base, self.methodName)()
