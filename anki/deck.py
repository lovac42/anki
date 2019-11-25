import copy

from anki.errors import DeckRenameError
from anki.utils import intTime, DictAugmentedIdUsn


class Deck(DictAugmentedIdUsn):
    """
    dic -- the JSON object associated to this deck.
    """
    def __init__(self, manager, parent=None, dict=None, name=None, baseName=None, type=None):
        """
        dict -- json dict encoding the deck. If None then there must be the following values
        name -- base name of the deck; it's parent is parent
        type -- the deck to copy
        
        """
        self.children = []
        if dict:
            self.load(manager, dict, parent)
        else:
            self.create(manager, parent, basename, type)
        self.parent.addChild(self)

    def isDyn(self):
        return self['dyn']

    def isStd(self):
        return not self.isDyn()

    def load(self, manager, dict, parent):
        super().__init__(manager, dict)
        assert parent.isAncestorOf(self)
        #Adding potential missing ancestor
        if self.parent.isTopLevel():
            toAdd = self.name
        else:
            toAdd = self.name[len(self.parent.getName)+2:]
        baseNames =  #useful if there is a missing parent
        missingBaseNames = toAdd.split("::")[:-1]
        for baseName in missingBaseNames:
            deck = Deck(self.manager, parent=parent, baseName=baseName)
            self.col.log("fix deck with missing parent", deck.getName())
            parent = deck
        self.parent = parent

    def create(self, manager, parent, baseName, type=None):
        self.parent = parent
        self.baseName = baseName
        assert("::" not in baseName)
        if type=None:
            type = defaultDeck
        type = copy.deepcopy(type)
        while 1:
            type['id'] = intTime(1000)
            if str(type['id']) not in self.manager.decks:
                break
        super().__init__(manager, type)

    def copy(self, baseName):
        """A copy of self saved in deckManager"""
        dic = copy.deepcopy(self.dic)
        while 1:
            dic['id'] = intTime(1000)
            if str(dic['id']) not in self.manager.decks:
                break
        copy = Deck(self.manager, self.parent, dic, baseName=baseName)
        self.save()
        

    def getBaseName(self):
        return self.baseName

    def ancestors(self, includeSelf=False):
        current = self
        if not includeSelf:
            current = current.parent
        l = []
        while not current.isTopLevel():
            l.append(current)
            current = current.parent
        l.reverse()
        return l

    def getName(self, parentName=None):
        "::".join(self.path())

    def dumps(self):
        self['name'] = self.getName()
        return super.dumps()

    def path(self):
        return map (lambda deck: deck.getBaseName(), self.ancestors())

    def getParent(self):
        return self.parent

    def getChildren(self):
        return self.children

    def getChildrenIds(self):
        return map(operator.itemgetter('id'), self.getChildren())

    def getChildrenNames(self):
        return map(operator.itemgetter('name'), self.getChildren())

    def addChild(self, child, loading=False):
        if self.isDyn():
            if loading:
                child.dragOnto(self.manager.topLevel)
            else:
                raise DeckRenameError(_("A filtered deck cannot have subdecks."))
        if getChild(child.baseName):
            if loading:
                # two decks with the same name?
                self.manager.col.log("fix duplicate deck name", deck['name'])
                child.changeBaseName(child.getBaseName + "%d" % intTime(1000))
            else:
                raise DeckRenameError(_("We're trying to add twice the same child."))
        bisect.insort(self.children, child)

    def removeChild(self, child):
        # as in example https://docs.python.org/fr/3/library/bisect.html
        i = bisect_left(self.children, child)
        if i != len(self.children) and self.children[i] == child:
            self.children.pop(i)

    def getDescendants(self, includeSelf=False):
        l = [*children.getDescendant(True) for children in self.getChildren()]
        if includeSelf:
            l.insert(0, self)
        return l

    def getDescendantsIds(self, includeSelf=False):
        return map(operator.itemgetter('id'), self.getDescendants(includeSelf))

    def getDescendantsNames(self, includeSelf=False):
        return map(operator.itemgetter('name'), self.getDescendants(includeSelf))

    def collapse(self):
        self['collapsed'] = not self['collapsed']
        self.save()

    def collapseBrowser(self):
        deck['browserCollapsed'] = not deck.get('browserCollapsed', False)
        self.save()

    def cids(self, children=False):
        """Return the list of id of cards whose deck's id is did.

        If Children is set to true, returns also the list of the cards
        of the descendant."""
        if not children:
            return self.manager.col.db.list("select id from cards where did=?", self['did'])
        dids = self.get(did).getDescendantsIds(True)
        return self.manager.col.db.list("select id from cards where did in "+
                                ids2str(dids))

    def isAncestorOf(self, descendant, includeSelf=False):
        while descendant:
            if includeSelf and self == descendant:
                return True
            includeSelf = True
            descendant = descendant.parent
        return False

    def isParentOf(self, child):
        return child.parent == self

    def isChildOf(self, parent):
        return self.parent == parent

    def getChild(self, name):
        name = self.manager.normalizeName(name)
        for child in self.children:
            if name == self.manager.normalizeName(child.getBaseName):
                return child
        return None

    def isDescendantOf(self, ancestor, includeSelf=False):
        return ancestor.isAncestorOf(self, includeSelf)
    
    def dragOnto(self, newParent):
        if newParent is None:
            newParent = self.manager.topLevel
        if not self._canDragOnto(newParent):
            return
        self.parent.removeChild(self)
        self.parent = newParent
        newParent.addChild(self)

    def changeBaseName(self, newBaseName):
        self.baseName = newBaseName

    def rename(self, newName):
        """Whether it did occur"""
        newBaseName = self.manager._basename(newBaseName)
        newParentName = self.manager._parentName(newName)
        newParent = self.manager.get(self.manager.id(newParentName))
        if newParentName.getChild(newBaseName):
            raise DeckRenameError(_("That deck already exists."))
        self.changeBaseName(newBaseName)
        self.dragOnto(newParent)
        self.manager.maybeAddToActive()

    def __getitem__(self, key, value=None):
        if key == "name":
            return self.getName()
        return super().__getitem__(key, value)

    def __setitem__(self, key, value):
        if key == "name":
            self.rename(value)
        else:
            super.__setitem__(key, value)

    def isDefault(self):
        return str(self.getId()) == "1"

    def setDefaultConf(self):
        self['conf'] = 1

    def isDefaultConf(self):
        return self.getConfId() == 1

    def setConfId(self, confId):
        self['conf'] = confId
        self.save()

    def setConf(self, conf):
        self['conf'] = confId.getId
        self.save()

    def getConfId(self):
        return self['conf']

    def getConf(self):
        self.manager.getConf(self.getConfId())

    def rem(cardsToo=False, childrenToo=True):
        self.col._logRem([self.getId()], REM_DECK)
        if self.isDyn():
            # deleting a cramming self returns cards to their previous self
            # rather than deleting the cards
            self.manager.col.sched.emptyDyn(did)
        else:
            # delete children first
            if childrenToo:
                # we don't want to delete children when syncing
                for child in self.getChildren()
                    child.rem(cardsToo, childrenToo)
            # delete cards too?
            if cardsToo:
                # don't use cids(), as we want cards in cram selfs too
                cids = self.manager.col.db.list(
                    "select id from cards where did=? or odid=?", did, did)
                self.manager.col.remCards(cids)
        # delete the deck and add a grave (it seems no grave is added)
        if str(self.getId()) == '1':
            self.dragOnto(self.manager.topLevel)
            self.uniquifyName()
        else:
            del self.manager.decks[str(self.getId())]
            # ensure we have an active deck.
            if self.getId() in self.manager.active():
                self.get(int(list(self.manager.decks.keys())[0])).select()
        self.manager.save()

    def uniquifyName(self):
        for sibling in self.parent.getChildren():
            if sibling.getBaseName() == self.getBaseName() and sibling != self:
                self.changeBaseName(self.getBaseName() + "%d" % intTime(1000))

    def isTopLevel(self):
        return self.getName() == ""
                
    def _canDragOnto(self, onto):
        if (onto.isParentOf(self) or self.isAncestorOf(onto, True)):
            return False
        return True

    def select():
        """Change activeDecks to the list containing did and the did
        of its children.

        Also mark the manager as changed."""
        self.manager.col.conf['curDeck'] = int(self.getId())
        # and active decks (current + all children)
        self.col.conf['activeDecks'] = self.getDescendantsIds(True)
        self.manager.changed = True

    def moveCards(self, cids):
        """Change the deck of the cards of cids to did.

        Keyword arguments:
        did -- the id of the new deck
        cids -- a list of ids of cards
        """
        self.col.db.execute(
            "update cards set did=?,usn=?,mod=? where id in "+
            ids2str(cids), self.getId(), self.col.usn(), intTime())

    def getModel(self):
        self.manager.col.models.get(self['mid'])
                
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

    def remConf(self):
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
        for deck in self.all():
            # ignore cram decks
            if 'conf' not in deck:
                continue
            if str(confgetConfId()) == str(id):
                deck.setDefaultConf()
                deck.save()
        self.manager.save()
