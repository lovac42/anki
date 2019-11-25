import copy

from anki.utils import intTime, DictAugmentedIdUsn

class DConf(DictAugmentedIdUsn):
    """
    dic -- the JSON object associated to this conf.
    """
    def create(self, manager, cloneFrom):
        if cloneFrom is None:
            cloneFrom = defaultConf
        conf = copy.deepcopy(cloneFrom)
        while 1:
            id = intTime(1000)
            if str(id) not in self.manager.dconf:
                break
        conf['id'] = id
        conf['name'] = name
        self.manager.dconf[str(id)] = self
        self.save()
        
    def load(self, manager, dict):
        super.__init__(manager, dict)
        # set limits to within bounds
        for type in ('rev', 'new'):
            pd = 'perDay'
            if conf[type][pd] > 999999:
                conf[type][pd] = 999999
                conf.save()
                self.manager.changed = True

    def getName(self):
        return self['name']

    def isDefault(self):
        return str(self['id']) == "1"

    def dids(self, conf):
        """The dids of the decks using the configuration conf."""
        dids = []
        for deck in list(self.manager.all()):
            if 'conf' in deck and deck.getConfId() == conf.getId():
                dids.append(deck.getId())
        return dids

    def rem(self):
        """Remove a configuration and update all decks using it.

        The new conf of the deck using this configuation is the
        default one.

        Keyword arguments:
        id -- The id of the configuration to remove. Should not be the
        default conf."""
        id = self.getId()
        assert id != 1
        self.manager.col.modSchema(check=True)
        del self.manager.dconf[str(id)]
        for deck in self.manager.all():
            # ignore cram decks
            if 'conf' not in deck:
                continue
            if str(confgetConfId()) == str(id):
                deck.setDefaultConf()
                deck.save()
        self.manager.save()
