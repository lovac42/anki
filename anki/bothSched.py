# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from operator import itemgetter

from anki.consts import *


# it uses the following elements from anki.consts
# card types: 0=new, 1=lrn, 2=rev, 3=relrn
# queue types: 0=new, 1=(re)lrn, 2=rev, 3=day (re)lrn,
#   4=preview, -1=suspended, -2=sibling buried, -3=manually buried
# revlog types: 0=lrn, 1=rev, 2=relrn, 3=early review
# positive revlog intervals are in days (rev), negative in seconds (lrn)
# odue/odid store original due/did when cards moved to filtered deck

class BothScheduler:
    haveCustomStudy = True
    _burySiblingsOnAnswer = True

    """
    queueLimit -- maximum number of cards to queue simultaneously. Always 50 unless changed by an addon.
    reportLimit -- the maximal number to show in main windows
    today -- difference between the last time scheduler is seen and creation of the collection.
    _haveQueues -- whether the number of cards to see today for current decks have been set.
    """
    def __init__(self, col):
        self.col = col
        self.queueLimit = 50
        self.reportLimit = 1000
        self.reps = 0
        self.today = None
        self._haveQueues = False
        self._updateCutoff()

    def getCard(self):
        "Pop the next card from the queue. None if finished."
        self._checkDay()
        if not self._haveQueues:
            self.reset()
        card = self._getCard()
        if card:
            self.col.log(card)
            if not self._burySiblingsOnAnswer:
                self._burySiblings(card)
            self.reps += 1
            card.startTimer()
            return card

    def reset(self):
        """
        Deal with the fact that it's potentially a new day.
        Reset number of learning, review, new cards according to current decks
        empty queues. Set haveQueues to true
        """
        self._updateCutoff()
        self._resetLrn()
        self._resetRev()
        self._resetNew()
        self._haveQueues = True

    # Rev/lrn/time daily stats
    ##########################################################################

    def _updateStats(self, card, type, cnt=1):
        key = type+"Today"
        for ancestor in ([self.col.decks.get(card.did)] +
                  self.col.decks.parents(card.did)):
            # add
            ancestor[key][1] += cnt
            self.col.decks.save(ancestor)

    def extendLimits(self, new, rev):
        cur = self.col.decks.current()
        ancestors = self.col.decks.parents(cur['id'])
        children = [self.col.decks.get(did) for (name, did) in
                    self.col.decks.children(cur['id'])]
        for deck in [cur] + ancestors + children:
            # add
            deck['newToday'][1] -= new
            deck['revToday'][1] -= rev
            self.col.decks.save(deck)

    def _walkingCount(self, limFn=None, cntFn=None):
        tot = 0
        pcounts = {}
        # for each of the active decks
        nameMap = self.col.decks.nameMap()
        for did in self.col.decks.active():
            # early alphas were setting the active ids as a str
            did = int(did)
            # get the individual deck's limit
            lim = limFn(self.col.decks.get(did))
            if not lim:
                continue
            # check the parents
            ancestors = self.col.decks.parents(did, nameMap)
            for ancestor in ancestors:
                # add if missing
                if ancestor['id'] not in pcounts:
                    pcounts[ancestor['id']] = limFn(ancestor)
                # take minimum of child and parent
                lim = min(pcounts[ancestor['id']], lim)
            # see how many cards we actually have
            cnt = cntFn(did, lim)
            # if non-zero, decrement from parent counts
            for ancestor in ancestors:
                pcounts[ancestor['id']] -= cnt
            # we may also be a parent
            pcounts[did] = lim - cnt
            # and add to running total
            tot += cnt
        return tot

    # Deck list
    ##########################################################################

    def _groupChildren(self, decks):
        """[subdeck name without parent parts,
        did, rev, lrn, new (counting subdecks)
        [recursively the same things for the children]]

        Keyword arguments:
        decks -- [deckname, did, rev, lrn, new]
        """
        # first, split the group names into components
        for deck in decks:
            deck[0] = deck[0].split("::")
        # and sort based on those components
        decks.sort(key=itemgetter(0))
        # then run main function
        return self._groupChildrenMain(decks)

    # New cards
    ##########################################################################

    def _resetNewCount(self):
        cntFn = lambda did, lim: self.col.db.scalar(f"""
select count() from (select 1 from cards where
did = ? and queue = {QUEUE_NEW} limit ?)""", did, lim)
        self.newCount = self._walkingCount(self._deckNewLimitSingle, cntFn)

    def _resetNew(self):
        self._resetNewCount()
        self._newDids = self.col.decks.active()[:]
        self._newQueue = []
        self._updateNewCardRatio()
