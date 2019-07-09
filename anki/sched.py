# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.bothSched import *

class Scheduler(BothScheduler):
    name = "std"
    _spreadRev = True

    def answerCard(self, card, ease):
        self.col.log()
        assert 1 <= ease <= 4
        self.col.markReview(card)
        if self._burySiblingsOnAnswer:
            self._burySiblings(card)
        card.reps += 1
        # former is for logging new cards, latter also covers filt. decks
        card.wasNew = card.type == CARD_NEW
        wasNewQ = card.queue == QUEUE_NEW_CRAM
        if wasNewQ:
            # came from the new queue, move to learning
            card.queue = QUEUE_LRN
            # if it was a new card, it's now a learning card
            if card.type == CARD_NEW:
                card.type = CARD_LRN
            # init reps to graduation
            card.left = self._startingLeft(card)
            # dynamic?
            if card.odid and card.type == CARD_DUE:
                if self._resched(card):
                    # reviews get their ivl boosted on first sight
                    card.ivl = self._dynIvlBoost(card)
                    card.odue = self.today + card.ivl
            self._updateStats(card, 'new')
        if card.queue in (QUEUE_LRN, QUEUE_DAY_LRN):
            self._answerLrnCard(card, ease)
            if not wasNewQ:
                self._updateStats(card, 'lrn')
        elif card.queue == QUEUE_REV:
            self._answerRevCard(card, ease)
            self._updateStats(card, 'rev')
        else:
            raise Exception("Invalid queue")
        self._updateStats(card, 'time', card.timeTaken())
        card.mod = intTime()
        card.usn = self.col.usn()
        card.flushSched()

    def counts(self, card=None):
        counts = [self.newCount, self.lrnCount, self.revCount]
        if card:
            idx = self.countIdx(card)
            if idx == QUEUE_LRN:
                counts[1] += card.left // 1000
            else:
                counts[idx] += 1
        return tuple(counts)

    def countIdx(self, card):
        if card.queue == QUEUE_DAY_LRN:
            return QUEUE_LRN
        return card.queue

    def answerButtons(self, card):
        """The number of buttons to show in the reviewer for `card`"""
        if card.odue:
            # normal review in dyn deck?
            if card.odid and card.queue == QUEUE_REV:
                return BUTTON_FOUR
            conf = self._lrnConf(card)
            if card.type in (CARD_NEW,CARD_LRN) or len(conf['delays']) > 1:
                return BUTTON_THREE
            return BUTTON_TWO
        elif card.queue == QUEUE_REV:
            return BUTTON_FOUR
        else:
            return BUTTON_THREE

    def unburyCards(self):
        "Unbury cards."
        self.col.conf['lastUnburied'] = self.today
        self.col.log(
            self.col.db.list(f"select id from cards where queue = {QUEUE_USER_BURIED}"))
        self.col.db.execute(
            f"update cards set queue=type where queue = {QUEUE_USER_BURIED}")

    def unburyCardsForDeck(self):
        sids = ids2str(self.col.decks.active())
        self.col.log(
            self.col.db.list(f"select id from cards where queue = {QUEUE_USER_BURIED} and did in %s"
                             % (sids)))
        self.col.db.execute(
            f"update cards set mod=?,usn=?,queue=type where queue = {QUEUE_USER_BURIED} and did in %s"
            % (sids), intTime(), self.col.usn())

    # Rev/lrn/time daily stats
    ##########################################################################

    # Deck list
    ##########################################################################

    def deckDueList(self):
        "Returns [deckname, did, rev, lrn, new]"
        self._checkDay()
        self.col.decks.checkIntegrity()
        decks = self.col.decks.all()
        decks.sort(key=itemgetter('name'))
        lims = {}
        data = []
        def parent(name):
            parts = name.split("::")
            if len(parts) < 2:
                return None
            parts = parts[:-1]
            return "::".join(parts)
        for deck in decks:
            p = parent(deck['name'])
            # new
            nlim = self._deckNewLimitSingle(deck)
            if p:
                nlim = min(nlim, lims[p][0])
            new = self._newForDeck(deck['id'], nlim)
            # learning
            lrn = self._lrnForDeck(deck['id'])
            # reviews
            rlim = self._deckRevLimitSingle(deck)
            if p:
                rlim = min(rlim, lims[p][1])
            rev = self._revForDeck(deck['id'], rlim)
            # save to list
            data.append([deck['name'], deck['id'], rev, lrn, new])
            # add deck as a parent
            lims[deck['name']] = [nlim, rlim]
        return data

    def deckDueTree(self):
        return self._groupChildren(self.deckDueList())

    def _groupChildrenMain(self, grps):
        tree = []
        # group and recurse
        def key(grp):
            return grp[0][0]
        for (head, tail) in itertools.groupby(grps, key=key):
            tail = list(tail)
            did = None
            rev = 0
            new = 0
            lrn = 0
            children = []
            for c in tail:
                if len(c[0]) == 1:
                    # current node
                    did = c[1]
                    rev += c[2]
                    lrn += c[3]
                    new += c[4]
                else:
                    # set new string to tail
                    c[0] = c[0][1:]
                    children.append(c)
            children = self._groupChildrenMain(children)
            # tally up children counts
            for ch in children:
                rev += ch[2]
                lrn += ch[3]
                new += ch[4]
            # limit the counts to the deck's limits
            conf = self.col.decks.confForDid(did)
            deck = self.col.decks.get(did)
            if not conf['dyn']:
                rev = max(0, min(rev, conf['rev']['perDay']-deck['revToday'][1]))
                new = max(0, min(new, conf['new']['perDay']-deck['newToday'][1]))
            tree.append((head, did, rev, lrn, new, children))
        return tuple(tree)

    # Getting the next card
    ##########################################################################

    def _getCard(self):
        "Return the next due card id, or None."
        # learning card due?
        c = self._getLrnCard()
        if c:
            return c
        # new first, or time for one?
        if self._timeForNewCard():
            c = self._getNewCard()
            if c:
                return c
        # card due for review?
        c = self._getRevCard()
        if c:
            return c
        # day learning card due?
        c = self._getLrnDayCard()
        if c:
            return c
        # new cards left?
        c = self._getNewCard()
        if c:
            return c
        # collapse or finish
        return self._getLrnCard(collapse=True)

    # Learning queues
    ##########################################################################

    def _resetLrnCount(self):
        # sub-day
        self.lrnCount = self.col.db.scalar(f"""
select sum(left/1000) from (select left from cards where
did in %s and queue = {QUEUE_LRN} and due < ? limit %d)""" % (
            self._deckLimit(), self.reportLimit),
            self.dayCutoff) or 0
        # day
        self.lrnCount += self.col.db.scalar(f"""
select count() from cards where did in %s and queue = {QUEUE_DAY_LRN}
and due <= ? limit %d""" % (self._deckLimit(),  self.reportLimit),
                                            self.today)

    # sub-day learning
    def _fillLrn(self):
        return super()._fillLrn(self.dayCutoff, f"({QUEUE_LRN})")

    def _getLrnCard(self, collapse=False):
        if self._fillLrn():
            cutoff = time.time()
            if collapse:
                cutoff += self.col.conf['collapseTime']
            if self._lrnQueue[0][0] < cutoff:
                id = heappop(self._lrnQueue)[1]
                card = self.col.getCard(id)
                self.lrnCount -= card.left // 1000
                return card

    def _answerLrnCard(self, card, ease):
        # ease 1=no, 2=yes, 3=remove
        conf = self._lrnConf(card)
        if card.odid and not card.wasNew:
            type = REVLOG_CRAM
        elif card.type == CARD_DUE:
            type = REVLOG_RELRN
        else:
            type = REVLOG_LRN
        leaving = False
        # lrnCount was decremented once when card was fetched
        lastLeft = card.left
        # immediate graduate?
        if ease == BUTTON_THREE:
            self._rescheduleAsRev(card, conf, True)
            leaving = True
        # graduation time?
        elif ease == BUTTON_TWO and (card.left%1000)-1 <= 0:
            self._rescheduleAsRev(card, conf, False)
            leaving = True
        else:
            # one step towards graduation
            if ease == BUTTON_TWO:
                # decrement real left count and recalculate left today
                left = (card.left % 1000) - 1
                card.left = self._leftToday(conf['delays'], left)*1000 + left
            # failed
            else:
                card.left = self._startingLeft(card)
                resched = self._resched(card)
                if 'mult' in conf and resched:
                    # review that's lapsed
                    card.ivl = max(1, conf['minInt'], card.ivl*conf['mult'])
                else:
                    # new card; no ivl adjustment
                    pass
                if resched and card.odid:
                    card.odue = self.today + 1
            delay = self._delayForGrade(conf, card.left)
            if card.due < time.time():
                # not collapsed; add some randomness
                delay *= random.uniform(1, 1.25)
            card.due = int(time.time() + delay)
            # due today?
            if card.due < self.dayCutoff:
                self.lrnCount += card.left // 1000
                # if the queue is not empty and there's nothing else to do, make
                # sure we don't put it at the head of the queue and end up showing
                # it twice in a row
                card.queue = QUEUE_LRN
                if self._lrnQueue and not self.revCount and not self.newCount:
                    smallestDue = self._lrnQueue[0][0]
                    card.due = max(card.due, smallestDue+1)
                heappush(self._lrnQueue, (card.due, card.id))
            else:
                # the card is due in one or more days, so we need to use the
                # day learn queue
                ahead = ((card.due - self.dayCutoff) // 86400) + 1
                card.due = self.today + ahead
                card.queue = QUEUE_DAY_LRN
        self._logLrn(card, ease, conf, leaving, type, lastLeft)

    def _lrnConf(self, card):
        if card.type == CARD_DUE:
            return self._lapseConf(card)
        else:
            return self._newConf(card)

    def _rescheduleAsRev(self, card, conf, early):
        lapse = card.type == CARD_DUE
        if lapse:
            if self._resched(card):
                card.due = max(self.today+1, card.odue)
            else:
                card.due = card.odue
            card.odue = 0
        else:
            self._rescheduleNew(card, conf, early)
        card.queue = QUEUE_REV
        card.type = CARD_DUE
        # if we were dynamic, graduating means moving back to the old deck
        resched = self._resched(card)
        if card.odid:
            card.did = card.odid
            card.odue = 0
            card.odid = 0
            # if rescheduling is off, it needs to be set back to a new card
            if not resched and not lapse:
                card.queue = QUEUE_NEW_CRAM
                card.type = CARD_NEW
                card.due = self.col.nextID("pos")

    def _startingLeft(self, card):
        if card.type == CARD_DUE:
            conf = self._lapseConf(card)
        else:
            conf = self._lrnConf(card)
        tot = len(conf['delays'])
        tod = self._leftToday(conf['delays'], tot)
        return tot + tod*1000

    def _graduatingIvl(self, card, conf, early, adj=True):
        if card.type == CARD_DUE:
            # lapsed card being relearnt
            if card.odid:
                if conf['resched']:
                    return self._dynIvlBoost(card)
            return card.ivl
        if not early:
            # graduate
            ideal =  conf['ints'][0]
        else:
            # early remove
            ideal = conf['ints'][1]
        if adj:
            return self._adjRevIvl(card, ideal)
        else:
            return ideal

    def removeLrn(self, ids=None):
        "Remove cards from the learning queues."
        if ids:
            extra = " and id in "+ids2str(ids)
        else:
            # benchmarks indicate it's about 10x faster to search all decks
            # with the index than scan the table
            extra = " and did in "+ids2str(self.col.decks.allIds())
        # review cards in relearning
        self.col.db.execute(f"""
update cards set
due = odue, queue = {QUEUE_REV}, mod = %d, usn = %d, odue = 0
where queue in ({QUEUE_LRN},{QUEUE_DAY_LRN}) and type = {CARD_DUE}
%s
""" % (intTime(), self.col.usn(), extra))
        # new cards in learning
        self.forgetCards(self.col.db.list(
            f"select id from cards where queue in ({QUEUE_LRN}, {QUEUE_DAY_LRN}) %s" % extra))

    def _lrnForDeck(self, did):
        cnt = self.col.db.scalar(
            f"""
select sum(left/1000) from
(select left from cards where did = ? and queue = {QUEUE_LRN} and due < ? limit ?)""",
            did, intTime() + self.col.conf['collapseTime'], self.reportLimit) or 0
        return cnt + self.col.db.scalar(
            f"""
select count() from
(select 1 from cards where did = ? and queue = {QUEUE_DAY_LRN}
and due <= ? limit ?)""" ,
            did, self.today, self.reportLimit)

    # Reviews
    ##########################################################################

    def _deckRevLimit(self, did):
        return self._deckNewLimit(did, self._deckRevLimitSingle)

    def _revForDeck(self, did, lim):
        lim = min(lim, self.reportLimit)
        return self.col.db.scalar(
            f"""
select count() from
(select 1 from cards where did = ? and queue = {QUEUE_REV}
and due <= ? limit ?)""",
            did, self.today, lim)

    def _resetRevCount(self):
        def cntFn(did, lim):
            return self.col.db.scalar(f"""
select count() from (select id from cards where
did = ? and queue = {QUEUE_REV} and due <= ? limit %d)""" % (lim),
                                      did, self.today)
        self.revCount = self._walkingCount(
            self._deckRevLimitSingle, cntFn)

    def _resetRev(self):
        super()._resetRev()
        self._revDids = self.col.decks.active()[:]

    def _fillRev(self):
        if self._revQueue:
            return True
        if not self.revCount:
            return False
        while self._revDids:
            did = self._revDids[0]
            lim = min(self.queueLimit, self._deckRevLimit(did))
            if lim:
                # fill the queue with the current did
                self._revQueue = self.col.db.list(f"""
select id from cards where
did = ? and queue = {QUEUE_REV} and due <= ? limit ?""",
                                                  did, self.today, lim)
                if self._revQueue:
                    # ordering
                    if self.col.decks.get(did)['dyn']:
                        # dynamic decks need due order preserved
                        self._revQueue.reverse()
                    else:
                        # random order for regular reviews
                        r = random.Random()
                        r.seed(self.today)
                        r.shuffle(self._revQueue)
                    # is the current did empty?
                    if len(self._revQueue) < lim:
                        self._revDids.pop(0)
                    return True
            # nothing left in the deck; move to next
            self._revDids.pop(0)
        if self.revCount:
            # if we didn't get a card but the count is non-zero,
            # we need to check again for any cards that were
            # removed from the queue but not buried
            self._resetRev()
            return self._fillRev()

    def _getRevCard(self):
        if self._fillRev():
            self.revCount -= 1
            return self.col.getCard(self._revQueue.pop())

    def totalRevForCurrentDeck(self):
        return self.col.db.scalar(
            """
select count() from cards where id in (
select id from cards where did in %s and queue = {QUEUE_REV} and due <= ? limit ?)"""
            % ids2str(self.col.decks.active()), self.today, self.reportLimit)

    # Answering a review card
    ##########################################################################

    def _answerRevCard(self, card, ease):
        delay = 0
        if ease == BUTTON_ONE:
            delay = self._rescheduleLapse(card)
        else:
            self._rescheduleRev(card, ease)
        self._logRev(card, ease, delay)

    def _rescheduleLapse(self, card):
        conf = self._lapseConf(card)
        card.lastIvl = card.ivl
        if self._resched(card):
            card.lapses += 1
            card.ivl = self._nextLapseIvl(card, conf)
            card.factor = max(1300, card.factor-200)
            card.due = self.today + card.ivl
            # if it's a filtered deck, update odue as well
            if card.odid:
                card.odue = card.due
        # if suspended as a leech, nothing to do
        delay = 0
        if self._checkLeech(card, conf) and card.queue == QUEUE_SUSPENDED:
            return delay
        # if no relearning steps, nothing to do
        if not conf['delays']:
            return delay
        # record rev due date for later
        if not card.odue:
            card.odue = card.due
        delay = self._delayForGrade(conf, 0)
        card.due = int(delay + time.time())
        card.left = self._startingLeft(card)
        # queue LRN
        if card.due < self.dayCutoff:
            self.lrnCount += card.left // 1000
            card.queue = QUEUE_LRN
            heappush(self._lrnQueue, (card.due, card.id))
        else:
            # day learn queue
            ahead = ((card.due - self.dayCutoff) // 86400) + 1
            card.due = self.today + ahead
            card.queue = QUEUE_DAY_LRN
        return delay

    def _nextLapseIvl(self, card, conf):
        return max(conf['minInt'], int(card.ivl*conf['mult']))

    def _rescheduleRev(self, card, ease):
        # update interval
        card.lastIvl = card.ivl
        if self._resched(card):
            self._updateRevIvl(card, ease)
            # then the rest
            card.factor = max(1300, card.factor+[-150, 0, 150][ease-2])
            card.due = self.today + card.ivl
        else:
            card.due = card.odue
        if card.odid:
            card.did = card.odid
            card.odid = 0
            card.odue = 0

    def _logRev(self, card, ease, delay):
        def log():
            self.col.db.execute(
                "insert into revlog values (?,?,?,?,?,?,?,?,?)",
                int(time.time()*1000), card.id, self.col.usn(), ease,
                -delay or card.ivl, card.lastIvl, card.factor, card.timeTaken(),
                1)
        try:
            log()
        except:
            # duplicate pk; retry in 10ms
            time.sleep(0.01)
            log()

    # Interval management
    ##########################################################################

    def _nextRevIvl(self, card, ease):
        "Ideal next interval for CARD, given EASE."
        delay = self._daysLate(card)
        conf = self._revConf(card)
        fct = card.factor / 1000
        ivl2 = self._constrainedIvl((card.ivl + delay // 4) * 1.2, conf, card.ivl)
        ivl3 = self._constrainedIvl((card.ivl + delay // 2) * fct, conf, ivl2)
        ivl4 = self._constrainedIvl(
            (card.ivl + delay) * fct * conf['ease4'], conf, ivl3)
        if ease == BUTTON_TWO:
            interval = ivl2
        elif ease == BUTTON_THREE:
            interval = ivl3
        elif ease == BUTTON_FOUR:
            interval = ivl4
        # interval capped?
        return min(interval, conf['maxIvl'])

    def _constrainedIvl(self, ivl, conf, prev):
        "Integer interval after interval factor and prev+1 constraints applied."
        new = ivl * conf.get('ivlFct', 1)
        return int(max(new, prev+1))

    def _updateRevIvl(self, card, ease):
        idealIvl = self._nextRevIvl(card, ease)
        card.ivl = min(max(self._adjRevIvl(card, idealIvl), card.ivl+1),
                       self._revConf(card)['maxIvl'])

    def _adjRevIvl(self, card, idealIvl):
        if self._spreadRev:
            idealIvl = self._fuzzedIvl(idealIvl)
        return idealIvl

    # Dynamic deck handling
    ##########################################################################

    def _fillDyn(self, deck):
        search, limit, order = deck['terms'][0]
        orderlimit = self._dynOrder(order, limit)
        if search.strip():
            search = "(%s)" % search
        search = "%s -is:suspended -is:buried -deck:filtered -is:learn" % search
        try:
            ids = self.col.findCards(search, order=orderlimit)
        except:
            ids = []
            return ids
        # move the cards over
        self.col.log(deck['id'], ids)
        self._moveToDyn(deck['id'], ids)
        return ids

    def emptyDyn(self, did, lim=None):
        if not lim:
            lim = "did = %s" % did
        self.col.log(self.col.db.list("select id from cards where %s" % lim))
        # move out of cram queue
        self.col.db.execute(f"""
update cards set did = odid, queue = (case when type = {CARD_LRN} then {QUEUE_NEW_CRAM}
else type end), type = (case when type = {CARD_LRN} then {CARD_NEW} else type end),
due = odue, odue = 0, odid = 0, usn = ? where %s""" % (lim),
                            self.col.usn())

    def _moveToDyn(self, did, ids):
        deck = self.col.decks.get(did)
        data = []
        t = intTime(); u = self.col.usn()
        for c, id in enumerate(ids):
            # start at -100000 so that reviews are all due
            data.append((did, -100000+c, u, id))
        # due reviews stay in the review queue. careful: can't use
        # "odid or did", as sqlite converts to boolean
        queue = f"""
(case when type={CARD_DUE} and (case when odue then odue <= %d else due <= %d end)
 then {QUEUE_REV} else {QUEUE_NEW_CRAM} end)"""
        queue %= (self.today, self.today)
        self.col.db.executemany("""
update cards set
odid = (case when odid then odid else did end),
odue = (case when odue then odue else due end),
did = ?, queue = %s, due = ?, usn = ? where id = ?""" % queue, data)

    def _dynIvlBoost(self, card):
        assert card.odid and card.type == CARD_DUE
        assert card.factor
        elapsed = card.ivl - (card.odue - self.today)
        factor = ((card.factor/1000)+1.2)/2
        ivl = int(max(card.ivl, elapsed * factor, 1))
        conf = self._revConf(card)
        return min(conf['maxIvl'], ivl)

    # Leeches
    ##########################################################################

    def _checkLeech(self, card, conf):
        "Leech handler. True if card was a leech."
        lf = conf['leechFails']
        if not lf:
            return
        # if over threshold or every half threshold reps after that
        if (card.lapses >= lf and
            (card.lapses-lf) % (max(lf // 2, 1)) == 0):
            # add a leech tag
            f = card.note()
            f.addTag("leech")
            f.flush()
            # handle
            a = conf['leechAction']
            if a == LEECH_SUSPEND:
                # if it has an old due, remove it from cram/relearning
                if card.odue:
                    card.due = card.odue
                if card.odid:
                    card.did = card.odid
                card.odue = card.odid = 0
                card.queue = QUEUE_SUSPENDED
            # notify UI
            runHook("leech", card)
            return True

    # Tools
    ##########################################################################

    def _delays(self, conf, oconf, type):
        if conf['delays']:
            r = conf['delays']
        else:
            r = oconf[type]['delays']
        return r

    def _resched(self, card):
        conf = self._cardConf(card)
        if not conf['dyn']:
            return True
        return conf['resched']

    # Daily cutoff
    ##########################################################################

    def _updateCutoff(self):
        oldToday = self.today
        # days since col created
        self.today = int((time.time() - self.col.crt) // 86400)
        # end of day cutoff
        self.dayCutoff = self.col.crt + (self.today+1)*86400
        if oldToday != self.today:
            self.col.log(self.today, self.dayCutoff)
        # update all daily counts, but don't save decks to prevent needless
        # conflicts. we'll save on card answer instead
        def update(g):
            for t in "new", "rev", "lrn", "time":
                key = t+"Today"
                if g[key][0] != self.today:
                    g[key] = [self.today, 0]
        for deck in self.col.decks.all():
            update(deck)
        # unbury if the day has rolled over
        unburied = self.col.conf.get("lastUnburied", 0)
        if unburied < self.today:
            self.unburyCards()

    # Deck finished state
    ##########################################################################

    def haveBuried(self):
        return self.haveBuriedSiblings()

    # Next time reports
    ##########################################################################

    def nextIvl(self, card, ease):
        "Return the next interval for CARD, in seconds."
        if card.queue in (QUEUE_NEW_CRAM, QUEUE_LRN, QUEUE_DAY_LRN):
            r = self._nextLrnIvl(card, ease)
            return r
        elif ease == BUTTON_ONE:
            # lapsed
            conf = self._lapseConf(card)
            if conf['delays']:
                return conf['delays'][0]*60
            r = self._nextLapseIvl(card, conf)*86400
            return r
        else:
            # review
            r = self._nextRevIvl(card, ease)*86400
            return r

    # this isn't easily extracted from the learn code
    def _nextLrnIvl(self, card, ease):
        if card.queue == QUEUE_NEW_CRAM:
            card.left = self._startingLeft(card)
        conf = self._lrnConf(card)
        if ease == BUTTON_ONE:
            # fail
            return self._delayForGrade(conf, len(conf['delays']))
        elif ease == BUTTON_THREE:
            # early removal
            if not self._resched(card):
                return 0
            return self._graduatingIvl(card, conf, True, adj=False) * 86400
        else:
            left = card.left%1000 - 1
            if left <= 0:
                # graduate
                if not self._resched(card):
                    return 0
                return self._graduatingIvl(card, conf, False, adj=False) * 86400
            else:
                return self._delayForGrade(conf, left)

    # Suspending
    ##########################################################################

    def suspendCards(self, ids):
        "Suspend cards."
        self.col.log(ids)
        self.remFromDyn(ids)
        self.removeLrn(ids)
        self.col.db.execute(
            (f"update cards set queue={QUEUE_SUSPENDED},mod=?,usn=? where id in ")+
            ids2str(ids), intTime(), self.col.usn())

    def unsuspendCards(self, ids):
        "Unsuspend cards."
        self.col.log(ids)
        self.col.db.execute(
            (f"update cards set queue=type,mod=?,usn=? "
            f"where queue = {QUEUE_SUSPENDED} and id in ")+ ids2str(ids),
            intTime(), self.col.usn())

    def buryCards(self, cids):
        self.col.log(cids)
        self.remFromDyn(cids)
        self.removeLrn(cids)
        self.col.db.execute((f"""
        update cards set queue={QUEUE_USER_BURIED},mod=?,usn=? where id in """)+ids2str(cids),
                            intTime(), self.col.usn())

    # Sibling spacing
    ##########################################################################

    def _burySiblings(self, card):
        toBury = super()._burySiblings(card)
        # then bury
        if toBury:
            self.col.db.execute(
                (f"update cards set queue={QUEUE_USER_BURIED},mod=?,usn=? where id in ")+ids2str(toBury),
                intTime(), self.col.usn())
            self.col.log(toBury)
