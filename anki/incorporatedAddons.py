
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
    Addon("Reviewer to Browser choosing what to display", 1555020859, 1565286616, "2e8ef9c8fa2648925807be43991432ae9211ba68", "https://github.com/Arthur-Milchior/anki-browser-from-reviewer"),
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
