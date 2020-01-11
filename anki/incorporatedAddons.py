
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
    Addon("Adding note and changing note type become quicker", 802285486, gitHash = "f1b2df03f4040e7820454052a2088a7672d819b2", gitRepo = "https://github.com/Arthur-Milchior/anki-fast-note-type-editor"),
    Addon("Advanced Browser", 874215009, 1552544150, "3f3f2c2855c4ad811a40705c565233acced1c1de", "https://github.com/hssm/advanced-browser"),
    Addon("CTRL+F5 to Refresh the Browser", 1347728560, 1564463100, "056a2cf4b0096c42e077876578778b1cfe3cc90c", "https://github.com/Arthur-Milchior/anki-addons-misc/tree/refreshBrowser/src/browser_refresh"),
    Addon("Edit new note type without needing a full sync", 1988880085, gitHash="28972c05ac638e6d5a5b781386d817a98821cd84", gitRepo="https://github.com/Arthur-Milchior/anki-freely-edit-new-note-type"),
    Addon("Empty cards returns more usable informations", 25425599, 1560126141, "299a0a7b3092923f5932da0bf8ec90e16db269af", "https://github.com/Arthur-Milchior/anki-clearer-empty-card"),
    Addon("Export cards selected in the Browser", 1983204951, 1560768960, "f8990da153af2745078e7b3c33854d01cb9fa304", "https://github.com/Arthur-Milchior/anki-export-from-browser"),
    Addon("F5 to Refresh the Browser", 832679841, gitRepo="https://github.com/glutanimate/anki-addons-misc/tree/master/src/browser_refresh"),
    Addon("Keep model of add cards", 424778276, 1553438887, "64bdf3c7d8e252d6f69f0a423d2db3c23ce6bc04", "https://github.com/Arthur-Milchior/anki-keep-model-in-add-cards"),
    Addon("«Check database» Explain errors and what is done to fix it", 1135180054, gitHash = "371c360e5611ad3eec5dcef400d969e7b1572141", gitRepo = "https://github.com/Arthur-Milchior/anki-database-check-explained"), #mod unkwon because it's not directly used by the author anymore
}

incompatibleAddons = {
    Addon("Enhance main window", 877182321, 1560116344, "4ca79998acd46f4fe295526db5fe4fe7c04889a5", "https://github.com/Arthur-Milchior/anki-enhance-main-window"), # because it uses function from scheduler which are removed
    Addon("More consistent cards generation", 1666697962, gitHash="24d6523be4e0dafaf0c55d9c51237e81629ba5a1", gitRepo="https://github.com/Arthur-Milchior/anki-correct-card-generation"), # because it uses _renderQA which did change
    Addon("Limit number of cards by day both new and review", 602339056, 1563554921, "76d2c55a9d853e692999d8ffeab240f14610fd25", "https://github.com/Arthur-Milchior/anki-limit-to-both-new-and-revs"), # becauses it uses counts as number and not as method
    Addon("More consistent cards generation", 1713990897, 1565620593, "55040b13944f9ef4c85a86f947e9844e5342f0a7", "https://github.com/Arthur-Milchior/anki-correct-card-generation"),#_renderQA did change
    Addon("Improve speed of change of note type", 115825506, 1551823299, "3a9608d46a97c755c0f802cdd0b3d023ace2bb70", "https://github.com/Arthur-Milchior/anki-better-card-generation"), #render_sections did change
}

addonsNotToLoad = {}
def up(set):
    addonsNotToLoad.update({addon.name: addon for addon in set if addon.name})
    addonsNotToLoad.update({addon.id: addon for addon in set if addon.id})
up(incorporatedAddonsSet)
up(incompatibleAddons)
