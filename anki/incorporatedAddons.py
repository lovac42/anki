
## Add-ons incorporated in this fork.

class Addon:
    def __init__(self, name = None, id = None, mod = None, gitHash = None, gitRepo = None):
        self.name = name
        self.id = id
        self.mod = mod
        self.gitHash = gitHash
        self.gitRepo = gitRepo

    def __hash__(self):
        return self.id or hash(self.name)

""" Set of characteristic of Add-ons incorporated here"""
incorporatedAddonsSet = {
    Addon("3 add-ons merged quicker anki explain deletion explain database check", 777545149, 1560838078, "https://github.com/Arthur-Milchior/anki-big-addon", "9138f06acf75df3eeb79a9b3cabdcfb0c6d964b9"),
    Addon("3 add-ons merged quicker anki explain deletion explain database check", 777545149, 1565577705, "https://github.com/Arthur-Milchior/anki-big-addon", "eb255bbccee683171596a26a667cc2b5611cb858"),
    Addon("Adding note and changing note type become quicker", 802285486, gitHash = "f1b2df03f4040e7820454052a2088a7672d819b2", gitRepo = "https://github.com/Arthur-Milchior/anki-fast-note-type-editor"),
    Addon("Advanced note editor Multi-column Frozen fields", 2064123047, 1561905302, "82a27f2726598c25d06f3065d23eb988815efd25", "https://github.com/Arthur-Milchior/anki-Multi-column-edit-window"),
    Addon("Multi-column note editor", 3491767031, 1560844854, "ad7a4014f184a1ec5d5d5c43a3fc4bab8bb8f6df", "https://github.com/hssm/anki-addons/tree/master/multi_column_editor"),
    Addon("«Check database» Explain errors and what is done to fix it", 1135180054, 1565577705, gitHash = "1d671710e624c4f7b620ce4e86b834ddf5569ae8", gitRepo = "https://github.com/Arthur-Milchior/anki-database-check-explained"), #mod unkwon because it's not directly used by the author anymore
    Addon("«Check database» Explain errors and what is done to fix it", 1135180054, gitHash = "371c360e5611ad3eec5dcef400d969e7b1572141", gitRepo = "https://github.com/Arthur-Milchior/anki-database-check-explained"), #mod unkwon because it's not directly used by the author anymore
}

incorporatedAddonsDict = {**{addon.name: addon for addon in incorporatedAddonsSet if addon.name},
                          **{addon.id: addon for addon in incorporatedAddonsSet if addon.id}}
