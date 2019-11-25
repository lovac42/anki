# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import copy
import json
import operator
import unicodedata

from anki.consts import *
from anki.errors import DeckRenameError
from anki.hooks import runHook
from anki.lang import _
from anki.utils import ids2str, intTime, json

"""This module deals with decks and their configurations.

self.decks is the dictionnary associating an id to the deck with this id
self.dconf is the dictionnary associating an id to the dconf with this id

A deck is a dict composed of:
new/rev/lrnToday -- two number array.
            First one is currently unused
            The second one is equal to the number of cards seen today in this deck minus the number of new cards in custom study today.
 BEWARE, it's changed in anki.sched(v2).Scheduler._updateStats and anki.sched(v2).Scheduler._updateCutoff.update  but can't be found by grepping 'newToday', because it's instead written as type+"Today" with type which may be new/rev/lrnToday
timeToday -- two number array used somehow for custom study,  seems to be currently unused
conf -- (string) id of option group from dconf, or absent in dynamic decks
usn -- Update sequence number: used in same way as other usn vales in db
desc -- deck description, it is shown when cards are learned or reviewd
dyn -- 1 if dynamic (AKA filtered) deck,
collapsed -- true when deck is collapsed,
extendNew -- extended new card limit (for custom study). Potentially absent, only used in aqt/customstudy.py. By default 10
extendRev -- extended review card limit (for custom study), Potentially absent, only used in aqt/customstudy.py. By default 10.
name -- name of deck,
browserCollapsed -- true when deck collapsed in browser,
id -- deck ID (automatically generated long),
mod -- last modification time,
mid -- the model of the deck
"""



"""A configuration of deck is a dictionnary composed of:
name -- its name, including the parents, and the "::"




A configuration of deck (dconf) is composed of:
name -- its name
new -- The configuration for new cards, see below.
lapse -- The configuration for lapse cards, see below.
rev -- The configuration for review cards, see below.
maxTaken -- The number of seconds after which to stop the timer
timer -- whether timer should be shown (1) or not (0)
autoplay -- whether the audio associated to a question should be
played when the question is shown
replayq -- whether the audio associated to a question should be
played when the answer is shown
mod -- Last modification time
usn -- see USN documentation
dyn -- Whether this deck is dynamic. Not present in the default configurations
id -- deck ID (automatically generated long). Not present in the default configurations.

The configuration related to new cards is composed of:
delays -- The list of successive delay between the learning steps of
the new cards, as explained in the manual.
ints -- The delays according to the button pressed while leaving the
learning mode.
initial factor -- The initial ease factor
separate -- delay between answering Good on a card with no steps left, and seeing the card again. Seems to be unused in the code
order -- In which order new cards must be shown. NEW_CARDS_RANDOM = 0
and NEW_CARDS_DUE = 1
perDay -- Maximal number of new cards shown per day
bury -- Whether to bury cards related to new cards answered

The configuration related to lapses card is composed of:
delays -- The delays between each relearning while the card is lapsed,
as in the manual
mult -- percent by which to multiply the current interval when a card
goes has lapsed
minInt -- a lower limit to the new interval after a leech
leechFails -- the number of lapses authorized before doing leechAction
leechAction -- What to do to leech cards. 0 for suspend, 1 for
mark. Numbers according to the order in which the choices appear in
aqt/dconf.ui


The configuration related to review card is composed of:
perDay -- Numbers of cards to review per day
ease4 -- the number to add to the easyness when the easy button is
pressed
fuzz -- The new interval is multiplied by a random number between
-fuzz and fuzz
minSpace -- not currently used
ivlFct -- multiplication factor applied to the intervals Anki
generates
maxIvl -- the maximal interval for review
bury -- If True, when a review card is answered, the related cards of
its notes are buried
"""

import bisect
import copy
import functools
import operator
import unicodedata

from anki.consts import *
from anki.deck import Deck
from anki.dconf import DConf
from anki.hooks import runHook
from anki.lang import _
from anki.utils import ids2str, json

# fixmes:
# - make sure users can't set grad interval < 1

defaultDeck = {
    'newToday': [0, 0], # currentDay, count
    'revToday': [0, 0],
    'lrnToday': [0, 0],
    'timeToday': [0, 0], # time in ms
    'conf': 1,
    'usn': 0,
    'desc': "",
    'dyn': DECK_STD,  # anki uses int/bool interchangably here
    'collapsed': False,
    # added in beta11
    'extendNew': 10,
    'extendRev': 50,
}

defaultDynamicDeck = {
    'newToday': [0, 0],
    'revToday': [0, 0],
    'lrnToday': [0, 0],
    'timeToday': [0, 0],
    'collapsed': False,
    'dyn': DECK_DYN,
    'desc': "",
    'usn': 0,
    'delays': None,
    'separate': True,
     # list of (search, limit, order); we only use first two elements for now
    'terms': [["", 100, 0]],
    'resched': True,
    'return': True, # currently unused

    # v2 scheduler
    "previewDelay": 10,
}

defaultConf = {
    'name': _("Default"),
    'new': {
        'delays': [1, 10],
        'ints': [1, 4, 7], # 7 is not currently used
        'initialFactor': STARTING_FACTOR,
        'separate': True,
        'order': NEW_CARDS_DUE,
        'perDay': 20,
        # may not be set on old decks
        'bury': False,
    },
    'lapse': {
        'delays': [10],
        'mult': 0,
        'minInt': 1,
        'leechFails': 8,
        # type 0=suspend, 1=tagonly
        'leechAction': LEECH_SUSPEND,
    },
    'rev': {
        'perDay': 200,
        'ease4': 1.3,
        'fuzz': 0.05,
        'minSpace': 1, # not currently used
        'ivlFct': 1,
        'maxIvl': 36500,
        # may not be set on old decks
        'bury': False,
        'hardFactor': 1.2,
    },
    'maxTaken': 60,
    'timer': 0,
    'autoplay': True,
    'replayq': True,
    'mod': 0,
    'usn': 0,
}

class DeckManager:

    """
    col -- the collection associated to this Deck manager
    decks -- associating to each id (as string) its deck
    dconf -- associating to each id (as string) its configuration(option)
    """
    # Registry save/load
    #############################################################

    def __init__(self, col):
        """State that the collection of the created object is the first argument."""
        self.col = col

    def load(self, decks, dconf):
        """Assign decks and dconf of this object using the two parameters.

        It also ensures that the number of cards per day is at most
        999999 or correct this error.

        Keyword arguments:
        decks -- json dic associating to each id (as string) its deck
        dconf -- json dic associating to each id (as string) its configuration(option)
        """
        decks = list(json.loads(decks).values())
        list.sort(operator.itemgetter("name"))
        self.toplevel = Deck(self, None, {"name": "", "id":"-1"})
        parents = [self.toplevel]
        self.decks = dict()
        for deckDict in decks:
            name = deckDict["name"]
            while parents[-1] != self.toplevel and not self._isAncestor(parents[-1], name):
                parents.pop(-1)

            deck = Deck(self, greatestAncestor, deckDict)
            self.decks[deck['key']] = deck
            greatestAncestor.addChild(deck, loading=True)
        for key, dconf in json.loads(dconf):
            self.dconf[key] = DConf(dconf, self)

    def save(self):
        self.changed = True

    def flush(self):
        """Puts the decks and dconf in the db if the manager state that some
        changes happenned.
        """
        if self.changed:
            self.col.db.execute("update col set decks=?, dconf=?",
                                 json.dumps(self.decks, default=lambda object: object.dumps()),
                                 json.dumps(self.dconf, default=lambda object: object.dumps()))
            self.changed = False

    # Deck save/load
    #############################################################

    def id(self, name, create=True, deckToCopy=None):
        """Returns a deck's id with a given name. Potentially creates it.

        Keyword arguments:
        name -- the name of the new deck. " are removed.
        create -- States whether the deck must be created if it does
        not exists. Default true, otherwise return None
        deckToCopy -- A deck to copy in order to create this deck
        """
        return self.byName(name, create, type).getId()

    def rem(self, did, cardsToo=False, childrenToo=True):
        """Remove the deck whose id is did.

        Does not delete the default deck, but rename it.

        Log the removal, even if the deck does not exists, assuming it
        is not default.

        Keyword arguments:
        cardsToo -- if set to true, delete its card.
        ChildrenToo -- if set to false,
        """
        if not str(did) in self.decks:
            # log the removal regardless of whether we have the deck or not
            self.col._logRem([did], REM_DECK)
            # do nothing else if doesn't exist
            return
        else:
            self.get(did).rem(cardsToo, childrenToo)

    def allNames(self, dyn=None, sort=False):
        """A list of all deck names.

        Keyword arguments:
        dyn -- What kind of decks to get
        sort -- whether to sort
        """
        decks = self.all(dyn=dyn)
        decksNames = map(operator.itemgetter('name'), decks)
        if sort:
            decksNames.sort()
        return decksNames

    def all(self, sort=False, dyn=None):
        """A list of all deck objects.

        dyn -- What kind of decks to get
        standard -- whether to incorporate non dynamic deck
        """
        decks = list(self.decks.values())
        if dyn is not None:
            decks = filter(lambda deck: deck.isDyn()==dyn, decks)
        if sort:
            decks.sort(key=operator.itemgetter("name"))
        return decks

    def allIds(self, sort=False, dyn=None):
        """A list of all deck's id.

        sort -- whether to sort by name"""
        return map(operator.itemgetter("id"), self.all(sort=sort, dyn=dyn))

    def count(self):
        """The number of decks."""
        return len(self.decks)

    def getDefaultDeck(self):
        return self.decks['1']

    def get(self, did, default=True):
        """Returns the deck objects whose id is did.

        If Default, return the default deck, otherwise None.

        """
        id = str(did)
        if id in self.decks:
            return self.decks[id]
        elif default:
            return getDefaultDeck()

    def byName(self, name, create=False, type=None):
        if type is None:
            type = defaultDeck
        name = name.replace('"', '')
        name = unicodedata.normalize("NFC", name)
        path = self._path(name)
        current = self.toplevel
        create = False
        for baseName in path:
            child = current.byName(baseName)
            if (child is None) and create:
                child = type.copy(baseName)
                self.decks[str(child.getId())] = child
                created = True
            else:
                return None
            current = child
        if created:
            runHook("newDeck")
            self.maybeAddToActive()
        return current

    def update(self, deck):
        "Add or update an existing deck. Used for syncing and merging."
        self.decks[str(deck.getId())] = deck
        self.maybeAddToActive()
        # mark registry changed, but don't bump mod time
        self.save()

    @staticmethod
    def _isParent(parent, child):
        """Whether child is a direct child of parent."""
        child = DeckManager.getName(child)
        return child == DeckManager.parentName(parent)

    @staticmethod
    def _isAncestor(ancestor, descendant, includeSelf=False):
        """Whether ancestorDeckName is an ancestor of
        descendantDeckName; or itself."""
        ancestor = DeckManager.getName(ancestor)
        descendant = DeckManager.getName(descendant)
        if ancestor == "":
            return True
        return (includeSelf and ancestor == descendant) or
                descendant.startswith(parent+"::")

    @staticmethod
    def getName(deck):
        "The name of the deck. If deck is already a name, returns it."
        if isinstance(deck, str):
            return deck
        return deck['name']

    @staticmethod
    def _path(name):
        """The list of decks and subdecks of name"""
        return DeckManager.getName(name).split("::")

    @staticmethod
    def _basename(name):
        """The name of the last subdeck, without its ancestors"""
        return DeckManager._path(name)[-1]

    @staticmethod
    def parentName(name):
        """The name of the parent of this deck, or empty string if there is none"""
        return "::".join(DeckManager._path(name)[:-1])

    # Deck configurations
    #############################################################

    def allConf(self):
        "A list of all deck config object."
        return list(self.dconf.values())

    def getConf(self, confId):
        """The dconf object whose id is confId."""
        return self.dconf[str(confId)]

    def updateConf(self, conf):
        """Add g to the set of dconf's. Potentially replacing a dconf with the
same id."""
        self.dconf[str(conf['id'])] = conf
        self.save()

    def restoreToDefault(self, conf):
        """Change the configuration to default.

        The only remaining part of the configuration are: the order of
        new card, the name and the id.
        """
        oldOrder = conf['new']['order']
        new = copy.deepcopy(defaultConf)
        new['id'] = conf['id']
        new['name'] = conf['name']
        self.dconf[str(conf['id'])] = new
        new.save()
        # if it was previously randomized, resort
        if not oldOrder:
            self.col.sched.resortConf(new)

    # Deck utils
    #############################################################

    def nameOrNone(self, did):
        """The name of the deck whose id is did, if it exists. None
        otherwise."""
        deck = self.get(did, default=False)
        if deck:
            return deck['name']
        return None

    def maybeAddToActive(self):
        """reselect current deck, or default if current has
        disappeared."""
        #It seems that nothing related to default happen in this code
        #nor in the function called by this code.
        #maybe is not appropriate, since no condition occurs
        self.current().select()

    def _recoverOrphans(self):
        """Move the cards whose deck does not exists to the default
        deck, without changing the mod date."""
        dids = list(self.decks.keys())
        mod = self.col.db.mod
        self.col.db.execute("update cards set did = 1 where did not in "+
                            ids2str(dids))
        self.col.db.mod = mod

    def checkIntegrity(self):
        self._recoverOrphans()

    # Deck selection
    #############################################################

    def active(self):
        "The currrently active dids. Make sure to copy before modifying."
        return self.col.conf['activeDecks']

    def selected(self):
        """The did of the currently selected deck."""
        return self.col.conf['curDeck']

    def current(self):
        """The currently selected deck object"""
        return self.get(self.selected())

    # Sync handling
    ##########################################################################

    def beforeUpload(self):
        for deck in self.all():
            deck.beforeUpload()
        for conf in self.allConf():
            conf.beforeUpload()
        self.save()

    # Dynamic decks
    ##########################################################################

    def newDyn(self, name):
        "Return a new dynamic deck and set it as the current deck."
        did = self.id(name, type=defaultDynamicDeck)
        self.get(did).select()
        return did

    @staticmethod
    def normalizeName(name):
        return unicodedata.normalize("NFC", name.lower())

    @staticmethod
    def equalName(name1, name2):
        return DeckManager.normalizeName(name1) == DeckManager.normalizeName(name2)
