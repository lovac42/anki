# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import random
import time
from operator import itemgetter

from anki.consts import *
from anki.lang import _
from anki.utils import fmtTimeSpan, ids2str, intTime

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

    def revCount(self):
        return self._revCount

    def setRevCount(self, value):
        self._revCount = value

    def _updateStats(self, card, type, cnt=1):
        key = type+"Today"
        for ancestor in card.currentDeck().getAncestors(includeSelf=True):
            # add
            ancestor[key][1] += cnt
            ancestor.save()

    def extendLimits(self, new, rev):
        cur = self.col.decks.current()
        ancestors = cur.getAncestors()
        children = cur.getDescendants()
        for deck in [cur] + ancestors + children:
            # add
            deck['newToday'][1] -= new
            deck['revToday'][1] -= rev
            deck.save()

    def _walkingCount(self, limFn=None, cntFn=None):
        tot = 0
        pcounts = {}
        # for each of the active decks
        for did in self.col.decks.active():
            # early alphas were setting the active ids as a str
            did = int(did)
            # get the individual deck's limit
            lim = limFn(self.col.decks.get(did))
            if not lim:
                continue
            # check the parents
            ancestors = self.col.decks.get(did).getAncestors()
            for ancestor in ancestors:
                # add if missing
                if ancestor.getId() not in pcounts:
                    pcounts[ancestor.getId()] = limFn(ancestor)
                # take minimum of child and parent
                lim = min(pcounts[ancestor.getId()], lim)
            # see how many cards we actually have
            cnt = cntFn(did, lim)
            # if non-zero, decrement from parent counts
            for ancestor in ancestors:
                pcounts[ancestor.getId()] -= cnt
            # we may also be a parent
            pcounts[did] = lim - cnt
            # and add to running total
            tot += cnt
        return tot

    # Deck list
    ##########################################################################

    def deckDueTree(self):
        """Generate the node of the main deck. See deckbroser introduction to see what a node is
        """
        self.deckDueList()
        for top in self.col.decks.topLevel.getChildren():
            self._groupChildrenMain(top)

    def deckDueList(self):
        """
        Set singleDue and lim for values we need to compute for the browser
        """
        self._checkDay()
        self.col.decks.checkIntegrity()
        decks = self.col.decks.all(sort=True)
        for deck in decks:
            parent = deck.getParent()
            # new
            deck.count['lim']['new'] = self._deckNewLimitSingle(deck)
            if not parent.isAboveTopLevel():
                deck.count['lim']['new'] = min(deck.count['lim']['new'], parent.count['lim']['new'])

            deck.count['singleDue']['new'] = self._newForDeck(deck.getId(), deck.count['lim']['new'])
            # learning
            self._dayLrnForDeck(deck)
            self._todayNbCardLrnForDeck(deck)
            self._todayStepLrnForDeck(deck)
            self._todayLrnForDeck(deck)
            # reviews
            deck.count['lim']['rev'] = self._deckRevLimitSingle(deck)
            if not parent.isAboveTopLevel():
                deck.count['lim']['rev'] = min(deck.count['lim']['rev'], parent.count['lim']['rev'])
            self._dueForDeck(deck)
            deck.count['singleDue']['rev'] = self._revForDeck(deck, deck.count['lim']['rev'])
            # add deck as a parent

    def _deckLimitSingle(self, deck, kind):
        "Limit for deck without parent limits."
        if deck.isDyn():
            return self.reportLimit
        conf = self.col.decks.get(deck.getId()).getConf()
        return max(0, conf[kind]['perDay'] - deck[kind+'Today'][1])

    # New cards
    ##########################################################################

    def _resetNewCount(self):
        cntFn = lambda did, lim: self.col.db.scalar(f"""
select count() from (select 1 from cards where
did = ? and queue = {QUEUE_NEW} limit ?)""", did, lim)
        self.setNewCount(self._walkingCount(self._deckNewLimitSingle, cntFn))

    def newCount(self):
        return self._newCount

    def setNewCount(self, value):
        self._newCount = value

    def _resetNew(self):
        self._resetNewCount()
        self._newDids = self.col.decks.active()[:]
        self._newQueue = []
        self._updateNewCardRatio()

    def _fillNew(self):
        if self._newQueue:
            return True
        if not self.newCount():
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
        if self.newCount():
            # if we didn't get a card but the count is non-zero,
            # we need to check again for any cards that were
            # removed from the queue but not buried
            self._resetNew()
            return self._fillNew()

    def _getNewCard(self):
        if self._fillNew():
            self.setNewCount(self.newCount() - 1)
            return self.col.getCard(self._newQueue.pop())

    def _updateNewCardRatio(self):
        if self.col.conf['newSpread'] == NEW_CARDS_DISTRIBUTE:
            if self.newCount():
                self.newCardModulus = (
                    (self.newCount() + self.revCount()) // self.newCount())
                # if there are cards to review, ensure modulo >= 2
                if self.revCount():
                    self.newCardModulus = max(2, self.newCardModulus)
                return
        self.newCardModulus = 0

    def _timeForNewCard(self):
        "True if it's time to display a new card when distributing."
        if not self.newCount():
            return False
        if self.col.conf['newSpread'] == NEW_CARDS_LAST:
            return False
        elif self.col.conf['newSpread'] == NEW_CARDS_FIRST:
            return True
        elif self.newCardModulus:
            return self.reps and self.reps % self.newCardModulus == 0

    def _deckNewLimit(self, did):
        return self._deckLimit(did, self._deckNewLimitSingle)

    def _deckLimit(self, did, fn):
        lim = -1
        # for the deck and each of its parents
        for ancestor in self.col.decks.get(did).getAncestors(includeSelf=True):
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
        return self._deckLimitSingle(deck, 'new')

    def totalNewForCurrentDeck(self):
        return self.col.db.scalar(
            f"""
select count() from cards where id in (
select id from cards where did in %s and queue = {QUEUE_NEW} limit ?)"""
            % ids2str(self.col.decks.active()), self.reportLimit)

    # Getting the next card
    ##########################################################################

    def _getCard(self):
        "Return the next due card id, or None."
        # learning card due?
        card = self._getLrnCard()
        if card:
            return card

        # new first, or time for one?
        if self._timeForNewCard():
            card = self._getNewCard()
            if card:
                return card

        # day learning first and card due?
        dayLearnFirst = self.col.conf.get("dayLearnFirst", False)
        if dayLearnFirst:
            card = self._getLrnDayCard()
            if card:
                return card

        # card due for review?
        card = self._getRevCard()
        if card:
            return card

        # day learning card due?
        if not dayLearnFirst:
            card = self._getLrnDayCard()
            if card:
                return card

        # new cards left?
        card = self._getNewCard()
        if card:
            return card

        # collapse or finish
        return self._getLrnCard(collapse=True)

    # Learning queues
    ##########################################################################

    def lrnCount(self):
        return self._lrnCount

    def setLrnCount(self, value):
        self._lrnCount = value

    def _resetLrn(self):
        """Set lrnCount and _lrnDids. Empty _lrnQueue, lrnDayQueu."""
        self._resetLrnCount()
        self._lrnQueue = []
        self._lrnDayQueue = []
        self._lrnDids = self.col.decks.active()[:]

    # sub-day learning
    def _fillLrn(self, cutoff, queue):
        if not self.lrnCount():
            return False
        if self._lrnQueue:
            return True
        self._lrnQueue = self.col.db.all(f"""
select due, id from cards where
did in %s and {queue} and due < :lim
limit %d""" % (self.col.decks._deckLimit(), self.reportLimit), lim=cutoff)
        # as it arrives sorted by did first, we need to sort it
        self._lrnQueue.sort()
        return self._lrnQueue

    # daily learning
    def _fillLrnDay(self):
        if not self.lrnCount():
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
            self.setLrnCount(self.lrnCount() - 1)
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

    def _dayLrnForDeck(self, deck):
        deck.count['singleDue']['dayLrn'] = self.col.db.scalar(
            f"""
select count() from
(select null from cards where did = ? and queue = {QUEUE_DAY_LRN}
and due <= ? limit ?)""",
            deck.getId(), self.today, self.reportLimit)

    def _lrnForDeck(self, deck):
        deck.count['singleDue']['lrn'] = deck.count['singleDue']['dayLrn'] + deck.count['singleDue']['todayLrn']

    def _todayLrnForDeckAux(self, deck, count):
        """Number of review of cards in learing of deck did. """
        return self.col.db.scalar(
            f"""
select {count} from
(select left from cards where did = ? and queue = {QUEUE_LRN} and due < ? limit ?)""",
            deck.getId(), intTime() + self.col.conf['collapseTime'], self.reportLimit) or 0

    def _todayStepLrnForDeck(self, deck):
        """Number of review of cards in learing of deck did. """
        deck.count['singleDue']['todayStepLrn'] = self._todayLrnForDeckAux(deck, "sum(left/1000)")

    def _todayNbCardLrnForDeck(self, deck):
        deck.count['singleDue']['todayNbCardLrn'] = self._todayLrnForDeckAux(deck, "count()")

    # Reviews
    ##########################################################################

    def _deckRevLimitSingle(self, deck):
        return self._deckLimitSingle(deck, 'rev')

    def _resetRev(self):
        """Set revCount, empty _revQueue, _revDids"""
        self._resetRevCount()
        self._revQueue = []

    def _getRevCard(self):
        if self._fillRev():
            self.setRevCount(self.revCount() - 1)
            return self.col.getCard(self._revQueue.pop())

    def totalRevForCurrentDeck(self):
        return self.col.db.scalar(
            f"""
select count() from cards where id in (
select id from cards where did in %s and queue = {QUEUE_REV} and due <= ? limit ?)"""
            % ids2str(self.col.decks.active()), self.today, self.reportLimit
)

    def _dueForDeck(self, deck):
        """number of cards due today for deck did """
        deck.count['singleDue']['due'] = self.col.db.scalar(
            f"""
select count() from
(select 1 from cards where did = ? and queue = {QUEUE_REV}
and due <= ?)""",
            deck.getId(), self.today)

    def _fillRev(self):
        if self._revQueue:
            return True
        if not self.revCount():
            return False
        if self._fillRevInternal():
            return True
        if self.revCount():
            # if we didn't get a card but the count is non-zero,
            # we need to check again for any cards that were
            # removed from the queue but not buried
            self._resetRev()
            return self._fillRev()

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
        due = card.odue if card.isFiltered() else card.due
        return max(0, self.today - due)

    # Dynamic deck handling
    ##########################################################################

    def rebuildDyn(self, did=None):
        "Rebuild a dynamic deck."
        did = did or self.col.decks.selected()
        deck = self.col.decks.get(did)
        assert deck.isDyn()
        # move any existing cards back first, then fill
        self.emptyDyn(did)
        ids = self._fillDyn(deck)
        if not ids:
            return
        # and change to our new deck
        self.col.decks.get(did).select()
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

    def _newConf(self, card):
        """The configuration for "new" of this card's deck.See decks.py
        documentation to read more about them.

        """
        conf = card.currentConf()
        # normal deck
        if not card.isFiltered():
            return conf['new']
        # dynamic deck; override some attributes, use original deck for others
        oconf = card.originalConf()
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
        conf = card.currentConf()
        # normal deck
        if not card.isFiltered():
            return conf['lapse']
        # dynamic deck; override some attributes, use original deck for others
        oconf = card.originalConf()
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
        return card.originalConf()['rev']

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
        if self.haveCustomStudy and not self.col.decks.current().isDyn():
            line.append(_("""\
To study outside of the normal schedule, click the Custom Study button below."""))
        return "<p>".join(line)

    def revDue(self):
        "True if there are any rev cards due."
        return self.col.db.scalar(
            (f"select 1 from cards where did in %s and queue = {QUEUE_REV} "
             "and due <= ? limit 1") % self.col.decks._deckLimit(),
            self.today)

    def newDue(self):
        "True if there are any new cards due."
        return self.col.db.scalar(
            (f"select 1 from cards where did in %s and queue = {QUEUE_NEW} "
             "limit 1") % (self.col.decks._deckLimit(),))

    # Next time reports
    ##########################################################################

    def nextIvlStr(self, card, ease, short=False):
        "Return the next interval for CARD as a string."
        ivl = self.nextIvl(card, ease)
        if not ivl:
            return _("(end)")
        ivlStr = fmtTimeSpan(ivl, short=short)
        if ivl < self.col.conf['collapseTime']:
            ivlStr = "<"+ivlStr
        return ivlStr

    # Suspending
    ##########################################################################

    def buryNote(self, nid):
        "Bury all cards for note until next session."
        cids = self.col.db.list(
            "select id from cards where nid = ? and queue >= 0", nid)
        self.buryCards(cids)

    # Sibling spacing
    ##########################################################################

    def _burySiblings(self, card):
        toBury = []
        nconf = self._newConf(card)
        buryNew = nconf.get("bury", True)
        rconf = self._revConf(card)
        buryRev = rconf.get("bury", True)
        # loop through and remove from queues
        for cid,queue in self.col.db.execute(f"""
select id, queue from cards where nid=? and id!=?
and (queue={QUEUE_NEW} or (queue={QUEUE_REV} and due<=?))""",
                card.nid, card.id, self.today):
            if queue == QUEUE_REV:
                if buryRev:
                    toBury.append(cid)
                # if bury disabled, we still discard to give same-day spacing
                try:
                    self._revQueue.remove(cid)
                except ValueError:
                    pass
            else:#Queue new Cram
                # if bury disabled, we still discard to give same-day spacing
                if buryNew:
                    toBury.append(cid)
                try:
                    self._newQueue.remove(cid)
                except ValueError:
                    pass
        # burying is done by the concrete class
        return toBury

    # Resetting
    ##########################################################################

    def forgetCards(self, ids):
        "Put cards at the end of the new queue."
        self.remFromDyn(ids)
        self.col.db.execute(
            (f"update cards set type={CARD_NEW},queue={QUEUE_NEW},ivl=0,due=0,odue=0,factor=?"
             " where id in ")+ids2str(ids), STARTING_FACTOR)
        pmax = self.col.db.scalar(
            f"select max(due) from cards where type={CARD_NEW}") or 0
        # takes care of mod + usn
        self.sortCards(ids, start=pmax+1)
        self.col.log(ids)

    def reschedCards(self, ids, imin, imax):
        "Put cards in review queue with a new interval in days (min, max)."
        cardData = []
        today = self.today
        mod = intTime()
        for id in ids:
            randValue = random.randint(imin, imax)
            cardData.append(dict(id=id, due=randValue+today, ivl=max(1, randValue), mod=mod,
                          usn=self.col.usn(), fact=STARTING_FACTOR))
        self.remFromDyn(ids)
        self.col.db.executemany(f"""
update cards set type={CARD_DUE},queue={QUEUE_REV},ivl=:ivl,due=:due,odue=0,
usn=:usn,mod=:mod,factor=:fact where id=:id""",
                                cardData)
        self.col.log(ids)

    def resetCards(self, ids):
        "Completely reset cards for export."
        sids = ids2str(ids)
        # we want to avoid resetting due number of existing new cards on export
        nonNew = self.col.db.list(
            f"select id from cards where id in %s and (queue != {QUEUE_NEW} or type != {CARD_NEW})"
            % (sids))
        # reset all cards
        self.col.db.execute(
            f"update cards set reps=0,lapses=0,odid=0,odue=0,queue={QUEUE_NEW}"
            " where id in %s" % (sids)
        )
        # and forget any non-new cards, changing their due numbers
        self.forgetCards(nonNew)
        self.col.log(ids)

    # Repositioning new cards
    ##########################################################################

    def sortCards(self, cids, start=1, step=1, shuffle=False, shift=False):
        scids = ids2str(cids)
        now = intTime()
        nids = []
        nidsSet = set()
        for id in cids:
            nid = self.col.db.scalar("select nid from cards where id = ?", id)
            if nid not in nidsSet:
                nids.append(nid)
                nidsSet.add(nid)
        if not nids:
            # no new cards
            return
        # determine nid ordering
        due = {}
        if shuffle:
            random.shuffle(nids)
        for index, nid in enumerate(nids):
            due[nid] = start+index*step
        # pylint: disable=undefined-loop-variable
        high = start+index*step
        # shift?
        if shift:
            low = self.col.db.scalar(
                f"select min(due) from cards where due >= ? and type = {CARD_NEW} "
                "and id not in %s" % (scids),
                start)
            if low is not None:
                shiftby = high - low + 1
                self.col.db.execute(f"""
update cards set mod=?, usn=?, due=due+? where id not in %s
and due >= ? and queue = {QUEUE_NEW}""" % (scids), now, self.col.usn(), shiftby, low)
        # reorder cards
        cardData = [dict(now=now, due=due[nid], usn=self.col.usn(), cid=id)
                    for id, nid in self.col.db.execute((f"select id, nid from cards where type = {CARD_NEW} and id in ")+scids)
        ]
        self.col.db.executemany(
            "update cards set due=:due,mod=:now,usn=:usn where id = :cid", cardData)

    def randomizeCards(self, did):
        cids = self.col.db.list("select id from cards where did = ?", did)
        self.sortCards(cids, shuffle=True)

    def orderCards(self, did):
        cids = self.col.db.list("select id from cards where did = ? order by id", did)
        self.sortCards(cids)

    def resortConf(self, conf):
        for did in conf.getDids():
            if conf['new']['order'] == NEW_CARDS_RANDOM:
                self.randomizeCards(did)
            else:
                self.orderCards(did)

    # for post-import
    def maybeRandomizeDeck(self, did=None):
        if not did:
            did = self.col.decks.selected()
        conf = self.col.decks.get(did).getConf()
        # in order due?
        if conf['new']['order'] == NEW_CARDS_RANDOM:
            self.randomizeCards(did)
