# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import random
import time
from operator import itemgetter

from anki.consts import *
from anki.lang import _
from anki.utils import ids2str, intTime

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

    def _fillNew(self):
        if self._newQueue:
            return True
        if not self.newCount:
            return False
        while self._newDids:
            did = self._newDids[0]
            lim = min(self.queueLimit, self._deckNewLimit(did))
            if lim:
                # fill the queue with the current did
                self._newQueue = self.col.db.list(f"""
                select id from cards where did = ? and queue = {QUEUE_NEW} order by due,ord limit ?""", did, lim)
                if self._newQueue:
                    self._newQueue.reverse()
                    return True
            # nothing left in the deck; move to next
            self._newDids.pop(0)
        if self.newCount:
            # if we didn't get a card but the count is non-zero,
            # we need to check again for any cards that were
            # removed from the queue but not buried
            self._resetNew()
            return self._fillNew()

    def _getNewCard(self):
        if self._fillNew():
            self.newCount -= 1
            return self.col.getCard(self._newQueue.pop())

    def _updateNewCardRatio(self):
        if self.col.conf['newSpread'] == NEW_CARDS_DISTRIBUTE:
            if self.newCount:
                self.newCardModulus = (
                    (self.newCount + self.revCount) // self.newCount)
                # if there are cards to review, ensure modulo >= 2
                if self.revCount:
                    self.newCardModulus = max(2, self.newCardModulus)
                return
        self.newCardModulus = 0

    def _timeForNewCard(self):
        "True if it's time to display a new card when distributing."
        if not self.newCount:
            return False
        if self.col.conf['newSpread'] == NEW_CARDS_LAST:
            return False
        elif self.col.conf['newSpread'] == NEW_CARDS_FIRST:
            return True
        elif self.newCardModulus:
            return self.reps and self.reps % self.newCardModulus == 0

    def _deckNewLimit(self, did, fn=None):
        if not fn:
            fn = self._deckNewLimitSingle
        sel = self.col.decks.get(did)
        lim = -1
        # for the deck and each of its parents
        for ancestor in [sel] + self.col.decks.parents(did):
            rem = fn(ancestor)
            if lim == -1:
                lim = rem
            else:
                lim = min(rem, lim)
        return lim

    def _newForDeck(self, did, lim):
        "New count for a single deck."
        if not lim:
            return 0
        lim = min(lim, self.reportLimit)
        return self.col.db.scalar(f"""
select count() from
(select 1 from cards where did = ? and queue = {QUEUE_NEW} limit ?)""", did, lim)

    def _deckNewLimitSingle(self, deck):
        "Limit for deck without parent limits."
        if deck['dyn']:
            return self.reportLimit
        conf = self.col.decks.confForDid(deck['id'])
        return max(0, conf['new']['perDay'] - deck['newToday'][1])

    def totalNewForCurrentDeck(self):
        return self.col.db.scalar(
            f"""
select count() from cards where id in (
select id from cards where did in %s and queue = {QUEUE_NEW} limit ?)"""
            % ids2str(self.col.decks.active()), self.reportLimit)

    # Learning queues
    ##########################################################################

    def _resetLrn(self):
        """Set lrnCount and _lrnDids. Empty _lrnQueue, lrnDayQueu."""
        self._resetLrnCount()
        self._lrnQueue = []
        self._lrnDayQueue = []
        self._lrnDids = self.col.decks.active()[:]

    # sub-day learning
    def _fillLrn(self, cutoff, queue):
        if not self.lrnCount:
            return False
        if self._lrnQueue:
            return True
        self._lrnQueue = self.col.db.all(f"""
select due, id from cards where
did in %s and {queue} and due < :lim
limit %d""" % (self._deckLimit(), self.reportLimit), lim=cutoff)
        # as it arrives sorted by did first, we need to sort it
        self._lrnQueue.sort()
        return self._lrnQueue

    # daily learning
    def _fillLrnDay(self):
        if not self.lrnCount:
            return False
        if self._lrnDayQueue:
            return True
        while self._lrnDids:
            did = self._lrnDids[0]
            # fill the queue with the current did
            self._lrnDayQueue = self.col.db.list(f"""
select id from cards where
did = ? and queue = {QUEUE_DAY_LRN} and due <= ? limit ?""",
                                    did, self.today, self.queueLimit)
            if self._lrnDayQueue:
                # order
                rand = random.Random()
                rand.seed(self.today)
                rand.shuffle(self._lrnDayQueue)
                # is the current did empty?
                if len(self._lrnDayQueue) < self.queueLimit:
                    self._lrnDids.pop(0)
                return True
            # nothing left in the deck; move to next
            self._lrnDids.pop(0)

    def _getLrnDayCard(self):
        if self._fillLrnDay():
            self.lrnCount -= 1
            return self.col.getCard(self._lrnDayQueue.pop())

    def _leftToday(self, delays, left, now=None):
        """The number of the last ```left``` steps that can be completed
        before the day cutoff. Assuming the first step is done
        ```now```.

        delays -- the list of delays
        left -- the number of step to consider (at the end of the
        list)
        now -- the time at which the first step is done.
        """
        if not now:
            now = intTime()
        delays = delays[-left:]
        ok = 0
        for i in range(len(delays)):
            now += delays[i]*60
            if now > self.dayCutoff:
                break
            ok = i
        return ok+1

    def _delayForGrade(self, conf, left):
        """The number of second for the delay until the next time the card can
        be reviewed. Assuming the number of left steps is left,
        according to configuration conf

        """
        left = left % 1000
        try:
            delay = conf['delays'][-left]
        except IndexError:
            if conf['delays']:
                delay = conf['delays'][0]
            else:
                # user deleted final step; use dummy value
                delay = 1
        return delay*60

    def _rescheduleNew(self, card, conf, early):
        """Reschedule a new card that's graduated for the first time.

        Set its factor according to conf.
        Set its interval. If it's lapsed in dynamic deck, use
        _dynIvlBoost.
        Otherwise, the interval is found in conf['ints'][1 if early
        else 0].
        Change due date according to the interval.
        Put initial factor.
        """
        card.ivl = self._graduatingIvl(card, conf, early)
        card.due = self.today+card.ivl
        card.factor = conf['initialFactor']

    def _logLrn(self, card, ease, conf, leaving, type, lastLeft):
        lastIvl = -(self._delayForGrade(conf, lastLeft))
        ivl = card.ivl if leaving else -(self._delayForGrade(conf, card.left))
        def log():
            self.col.db.execute(
                "insert into revlog values (?,?,?,?,?,?,?,?,?)",
                int(time.time()*1000), card.id, self.col.usn(), ease,
                ivl, lastIvl, card.factor, card.timeTaken(), type)
        try:
            log()
        except:
            # duplicate pk; retry in 10ms
            time.sleep(0.01)
            log()

    # Reviews
    ##########################################################################

    def _deckRevLimitSingle(self, deck):
        """Maximum number of card to review today in deck d.

        self.reportLimit for dynamic deck. Otherwise the number of review according to deck option, plus the number of review added in custom study today.
        keyword arguments:
        d -- a deck object"""
        # invalid deck selected?
        if deck['dyn']:
            return self.reportLimit
        conf = self.col.decks.confForDid(deck['id'])
        return max(0, conf['rev']['perDay'] - deck['revToday'][1])

    def _resetRev(self):
        """Set revCount, empty _revQueue, _revDids"""
        self._resetRevCount()
        self._revQueue = []

    def _getRevCard(self):
        if self._fillRev():
            self.revCount -= 1
            return self.col.getCard(self._revQueue.pop())

    def totalRevForCurrentDeck(self):
        return self.col.db.scalar(
            f"""
select count() from cards where id in (
select id from cards where did in %s and queue = {QUEUE_REV} and due <= ? limit ?)"""
            % ids2str(self.col.decks.active()), self.today, self.reportLimit
)

    # Interval management
    ##########################################################################

    def _fuzzedIvl(self, ivl):
        """Return a randomly chosen number of day for the interval,
        not far from ivl.

        See ../documentation/computing_intervals for a clearer version
        of this documentation
        """
        min, max = self._fuzzIvlRange(ivl)
        return random.randint(min, max)

    def _fuzzIvlRange(self, ivl):
        """Return an increasing pair of numbers.  The new interval will be a
        number randomly selected between the first and the second
        element.

        See ../documentation/computing_intervals for a clearer version
        of this documentation

        """
        if ivl < 2:
            return [1, 1]
        elif ivl == 2:
            return [2, 3]
        elif ivl < 7:
            fuzz = int(ivl*0.25)
        elif ivl < 30:
            fuzz = max(2, int(ivl*0.15))
        else:
            fuzz = max(4, int(ivl*0.05))
        # fuzz at least a day
        fuzz = max(fuzz, 1)
        return [ivl-fuzz, ivl+fuzz]

    def _daysLate(self, card):
        "Number of days later than scheduled."
        due = card.odue if card.odid else card.due
        return max(0, self.today - due)

    # Dynamic deck handling
    ##########################################################################

    def rebuildDyn(self, did=None):
        "Rebuild a dynamic deck."
        did = did or self.col.decks.selected()
        deck = self.col.decks.get(did)
        assert deck['dyn']
        # move any existing cards back first, then fill
        self.emptyDyn(did)
        ids = self._fillDyn(deck)
        if not ids:
            return
        # and change to our new deck
        self.col.decks.select(did)
        return ids

    def remFromDyn(self, cids):
        self.emptyDyn(None, "id in %s and odid" % ids2str(cids))

    def _dynOrder(self, order, limit, default):
        if order == DYN_OLDEST:
            sort = "(select max(id) from revlog where cid=card.id)"
        elif order == DYN_RANDOM:
            sort = "random()"
        elif order == DYN_SMALLINT:
            sort = "ivl"
        elif order == DYN_BIGINT:
            sort = "ivl desc"
        elif order == DYN_LAPSES:
            sort = "lapses desc"
        elif order == DYN_ADDED:
            sort = "note.id"
        elif order == DYN_REVADDED:
            sort = "note.id desc"
        elif order == DYN_DUEPRIORITY:
            sort = f"(case when queue={QUEUE_REV} and due <= %d then (ivl / cast(%d-due+0.001 as real)) else 100000+due end)" % (
                    self.today, self.today)
        else:# DYN_DUE or unknown
            sort = default
        return sort + " limit %d" % limit

    # Tools
    ##########################################################################

    def _cardConf(self, card):
        """The configuration of this card's deck. See decks.py
        documentation to read more about them."""
        return self.col.decks.confForDid(card.did)

    def _newConf(self, card):
        """The configuration for "new" of this card's deck.See decks.py
        documentation to read more about them.

        """
        conf = self._cardConf(card)
        # normal deck
        if not card.odid:
            return conf['new']
        # dynamic deck; override some attributes, use original deck for others
        oconf = self.col.decks.confForDid(card.odid)
        return dict(
            # original deck
            ints=oconf['new']['ints'],
            initialFactor=oconf['new']['initialFactor'],
            bury=oconf['new'].get("bury", True),
            delays=self._getDelay(conf, oconf, 'new'),
            # overrides
            separate=conf['separate'],
            order=NEW_CARDS_DUE,
            perDay=self.reportLimit
        )

    def _lapseConf(self, card):
        """The configuration for "lapse" of this card's deck.See decks.py
        documentation to read more about them.

        """
        conf = self._cardConf(card)
        # normal deck
        if not card.odid:
            return conf['lapse']
        # dynamic deck; override some attributes, use original deck for others
        oconf = self.col.decks.confForDid(card.odid)
        return dict(
            # original deck
            minInt=oconf['lapse']['minInt'],
            leechFails=oconf['lapse']['leechFails'],
            leechAction=oconf['lapse']['leechAction'],
            mult=oconf['lapse']['mult'],
            delays=self._getDelay(conf, oconf, 'lapse'),
            # overrides
            resched=conf['resched'],
        )

    def _revConf(self, card):
        """The configuration for "review" of this card's deck.See decks.py
        documentation to read more about them.

        """
        conf = self._cardConf(card)
        # normal deck
        if not card.odid:
            return conf['rev']
        # dynamic deck
        return self.col.decks.confForDid(card.odid)['rev']

    def _deckLimit(self):
        """The list of active decks, as comma separated parenthesized
        string"""
        return ids2str(self.col.decks.active())

    # Daily cutoff
    ##########################################################################

    def _checkDay(self):
        # check if the day has rolled over
        if time.time() > self.dayCutoff:
            self.reset()

    # Deck finished state
    ##########################################################################

    def finishedMsg(self):
        return ("<b>"+_(
            "Congratulations! You have finished this deck for now.")+
            "</b><br><br>" + self._nextDueMsg())

    def _nextDueMsg(self):
        line = []
        # the new line replacements are so we don't break translations
        # in a point release
        if self.revDue():
            line.append(_("""\
Today's review limit has been reached, but there are still cards
waiting to be reviewed. For optimum memory, consider increasing
the daily limit in the options.""").replace("\n", " "))
        if self.newDue():
            line.append(_("""\
There are more new cards available, but the daily limit has been
reached. You can increase the limit in the options, but please
bear in mind that the more new cards you introduce, the higher
your short-term review workload will become.""").replace("\n", " "))
        if self.haveBuried():
            if self.haveCustomStudy:
                now = " " +  _("To see them now, click the Unbury button below.")
            else:
                now = ""
            line.append(_("""\
Some related or buried cards were delayed until a later session.""")+now)
        if self.haveCustomStudy and not self.col.decks.current()['dyn']:
            line.append(_("""\
To study outside of the normal schedule, click the Custom Study button below."""))
        return "<p>".join(line)
