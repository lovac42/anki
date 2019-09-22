
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
    Addon("\"Close and lose current input ?\" for sticky fields", 1284221829, gitHash="8eb22c84dea7dfdf5e3f501db1c0d9b273de9f3e", gitRepo="https://github.com/Arthur-Milchior/anki-Close-and-lose-current-input-for-sticky-fields"),
}

incorporatedAddonsDict = {**{addon.name: addon for addon in incorporatedAddonsSet if addon.name},
                          **{addon.id: addon for addon in incorporatedAddonsSet if addon.id}}
