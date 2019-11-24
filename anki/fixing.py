import os
import stat

from anki.consts import *
from anki.decks import defaultConf as defaultDeckConf
from anki.decks import defaultDeck, defaultDynamicDeck
from anki.lang import _, ngettext
from anki.utils import ids2str, intTime


class FixingManager:

    def __init__(self, col):
        self.col = col
        self.db = col.db

    listFix = [
        "noteWithMissingModel",
        "override",
        "req",
        "invalidCardOrdinal",
        "wrongNumberOfField",
        "noteWithoutCard",
        "odueNotInDyn",
        "odidNotInDyn",
        "tags",
        "fieldCache",
        "atMost1000000Due",
        "setNextPos",
        "reasonnableDueRev",
        "floatIvlInCard",
        "floatIvlInRevLog",
        "ensureSomeNoteType",
    ]


    def _template(self, query, messageByError, singular, plural, deletion=None, params=(), reason=None):
        """Execute query. If it returns some value, it means there was a
        problem. Append it to self.problems. Apply deletion to the
        list returned by the query to correct the error.
        query -- a sql query returning tuples with problem
        messageByError -- a message to add to the list of problems for each result of the query. It takes as many parameter as there are query columns
        singular, plurar -- a global message to tell all problems which occured
        deletion -- a method to apply to the tuples found
        reason -- not used currently
        """
        problems = []
        tups = self.db.all(query, params)
        for tup in tups:
            problems.append(messageByError.format(*tup))
        if tups:
            problems.append(ngettext(singular,
                                          plural, len(tups))
                                 % len(tups))
            if deletion:
                deletion(tups)
        return problems

    def fixIntegrity(self):
        "Fix possible problems and rebuild caches."
        problems = []
        curs = self.db.cursor()
        self.col.save()
        oldSize = os.stat(self.col.path)[stat.ST_SIZE]
        # whether sqlite find a problem in its database
        if self.db.scalar("pragma integrity_check") != "ok":
            return (_("Collection is corrupt. Please see the manual."), False)
        for fix in self.listFix:#execute all methods required to fix something
            problems += (getattr(self,fix)())
        # and finally, optimize
        self.col.optimize()
        newSize = os.stat(self.col.path)[stat.ST_SIZE]
        txt = _("Database rebuilt and optimized.")
        ok = not problems
        print("Adding in collection.py")
        problems.append(txt)
        # if any problems were found, force a full sync
        if not ok:
            self.col.modSchema(check=False)
        self.col.save()
        return ("\n".join(problems), ok)

    def noteWithMissingModel(self):
        # note types with a missing model
        return self._template(
            """select id from notes where mid not in """ + ids2str(self.col.models.ids()),
            "Note {} removed because it has no known model",
            "Deleted %d note with missing note type.",
            "Deleted %d notes with missing note type.",
            self.col.remNotes(ids))

    def override(self):
        # for each model
        problems = []
        for model in self.col.models.all():
            for template in model['tmpls']:
                if template['did'] == "None":
                    template['did'] = None
                    problems.append(_("Fixed AnkiDroid deck override bug."))
                    self.col.models.save(model)
        return problems

    def req(self):
        # model with missing req specification
        problems = []
        for model in self.col.models.all(MODEL_STD):
            if 'req' not in model:
                model._updateRequired()
                problems.append(_("Fixed note type: %s") % model['name'])
        return problems

    def invalidCardOrdinal(self):
        # cards with invalid ordinal
        problems = []
        for model in self.col.models.all(MODEL_STD):
            problems += self._template(
                """select id from cards where ord not in %s and nid in ( select id
                from notes where mid = ?)""" %
                ids2str([template['ord'] for template in model['tmpls']]),
                "Delete note {} because its template is missing",
                "Deleted %d card with missing template.",
                "Deleted %d cards with missing template.",
                self.col.remCards
                params=(model['id'],)
            )
        return problems

    def wrongNumberOfField(self):
        # notes with invalid field count
        problems = []
        for model in self.col.models.all():
            problems += self._template(
                """select id from notes where mid = ? and (LEN(flds)-LEN(REPLACE(flds, '\x1f', ''))) <> ?""",
                "Delete note {} because it has a wrong number of fields.",
                "Deleted %d note with wrong field count.",
                "Deleted %d notes with wrong field count.",
                self.col.remNotes,
                params = (model['id'], len(model['flds'])))
        return problems


    def noteWithoutCard(self):
        # delete any notes with missing cards
        return self._template(
            """select id from notes where id not in
            (select distinct nid from cards)""",
            "Delete note {} because it has no cards",
            "Deleted %d note with no cards.",
            "Deleted %d notes with no cards.",
            self.col._remNotes)

    def odueNotInDyn(self):
        # cards with odue set when it shouldn't be
        self._template(
            f"""select id from cards where odue > 0 and (type={CARD_LRN} or
            queue={CARD_DUE}) and not odid""",
            "Unset odue of card {} because its not filtered",
            "Fixed %d card with invalid properties.",
            "Fixed %d cards with invalid properties.",
            lambda ids: self.db.execute("update cards set odue=0 where id in "+
                                        ids2str(ids))
        )


        def odidNotInDyn(self):
        # cards with odid set when not in a dyn deck
        dids = [deck.getId() for deck in self.col.decks.all() if deck.isStd()]
        return self._template("""
        select id from cards where odid > 0 and did in %s""" % ids2str(dids),
                      "unset odid, odue in card {} because not in dynamic deck",
                      "Fixed %d card with invalid properties.",
                      "Fixed %d cards with invalid properties.",
                      lambda ids: self.db.execute("update cards set odid=0, odue=0 where id in "+
                                                  ids2str(ids))
                      )

    def tags(self):
        # tags
        self.col.tags.registerNotes()

    def fieldCache(self):
        # field cache
        for model in self.col.models.all():
            self.col.updateFieldCache(model.nids())

    def atMost1000000Due(self):
        # new cards can't have a due position > 32 bits, so wrap items over
        # 2 million back to 1 million
        curs.execute(
            f"""update cards set due=1000000+due%1000000,mod=?,usn=? where
            due>=1000000 and type = {CARD_NEW}""",
            [intTime(), self.col.usn()])
        if curs.rowcount:
            return [
                "Found %d new cards with a due number >= 1,000,000 - consider repositioning them in the Browse screen." % curs.rowcount
                ]

    def setNextPos(self):
        # new card position
        self.col.conf['nextPos'] = self.db.scalar(
            f"""select max(due)+1 from cards where type = {CARD_NEW}""",
        ) or 0

    def reasonnableDueRev(self):
        # reviews should have a reasonable due #
        ids = self.db.list(
            f"""select id from cards where queue = {QUEUE_REV} and due > 100000""",
        )
        if ids:
            self.db.execute(
                """update cards set due = ?, ivl = 1, mod = ?, usn = ? where id in %s"""
                % ids2str(ids),
                self.col.sched.today, intTime(), self.col.usn())
            return ["Reviews had incorrect due date."]

    def floatIvlInCard(self):
        # v2 sched had a bug that could create decimal intervals
        curs.execute(
            """update cards set ivl=round(ivl),due=round(due) where ivl!=round(ivl) or due!=round(due)""",
        )
        if curs.rowcount:
            return ["Fixed %d cards with v2 scheduler bug." % curs.rowcount]

    def floatIvlInRevLog(self):
        curs.execute(
            """update revlog set ivl=round(ivl),lastIvl=round(lastIvl) where ivl!=round(ivl) or lastIvl!=round(lastIvl)""",
        )
        if curs.rowcount:
            return ["Fixed %d review history entries with v2 scheduler bug." % curs.rowcount]

    def ensureSomeNoteType(self):
        # models
        if self.col.models.ensureNotEmpty():
            return ["Added missing note type."]
