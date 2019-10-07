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

    """List of method to call to fix things. It can be edited by add-on, in order to add more method, or delete/change some. """
    listFix = [
        "noteWithMissingModel",
        "fixOverride",
        "fixReq",
        "fixInvalidCardOrdinal",
        "fixWrongNumberOfField",
        "fixNoteWithoutCard",
        "fixCardWithoutNote",
        "fixOdueType1",
        "fixOdueQueue2",
        "fixOdidOdue",
        "reasonableRevueDue",
        "fixFloatIvlInCard",
        "fixFloatIvlInRevLog",
        "fixFloatDue",
        "doubleCard",
        "ensureSomeNoteType",
        "registerNotes",
        "updateAllFieldcache",
        "atMost1000000Due",
    ]

    def fixIntegrity(self):
        """Find the problems which will be found. Then call last fixing."""
        #differences: not recomputing models' req. Giving reason to deletion
        self.problems = []
        self.col.save()
        ret = self.integrity()#If the database itself is broken, there is nothing else to do.
        if ret:
            return ret

        for fix in self.listFix:#execute all methods required to fix something
            getattr(self,fix)()
        # whether sqlite find a problem in its database
        self.col.optimize()
        newSize = os.stat(self.col.path)[stat.ST_SIZE]
        txt = _("Database rebuilt and optimized.")
        ok = not self.problems
        self.problems.append(txt)
        # if any self.problems were found, force a full sync
        if not ok:
            self.modSchema(check=False)
        self.col.save()
        return ("\n".join(self.problems), ok)

    def integrity(self):
        # whether sqlite find a problem in its database
        if self.db.scalar("pragma integrity_check") != "ok":
            return (_("Collection is corrupt. Please see the manual."), False)

    def template(self, query, messageByError, singular, plural, deletion=None, reason=None):
        """Execute query. If it returns some value, it means there was a
        problem. Append it to self.problems. Apply deletion to the
        list returned by the query to correct the error.

        query -- a sql query returning tuples with problem
        messageByError -- a message to add to the list of problems for each result of the query. It takes as many parameter as there are query columns
        singular, plurar -- a global message to tell all problems which occured
        deletion -- a method to apply to the tuples found
        reason -- not used currently
        """
        tups = self.db.all(query)
        for tup in tups:
            self.problems.append(messageByError.format(*tup))
        if tups:
            self.problems.append(ngettext(singular,
                                     plural, len(tups))
                            % len(tups))
            if deletion:
                deletion(tups)

    def noteWithMissingModel(self):
        self.template("""
        select id, flds, tags, mid from notes where mid not in """ + ids2str(self.col.models.ids()),
                  "Deleted note {}, with fields «{}», tags «{}» whose model id is {}, which does not exists.",
                  "Deleted %d note with missing note type.",
                  "Deleted %d notes with missing note type.",
                  lambda lines: self.remNotes([line[0]for line in lines])
        )

    def fixOverride(self):
        for model in self.col.models.all():
            for template in model['tmpls']:
                if template['did'] == "None":
                    template['did'] = None
                    self.problems.append(_("Fixed AnkiDroid deck override bug. (I.e. some template has did = to 'None', it is now None.)"))
                    self.col.models.save(model)

    def fixReq(self):
        for model in self.col.models.all():
            if model['type'] == MODEL_STD:
                # model with missing req specification
                if 'req' not in model:
                    self.col.models._updateRequired(model)
                    self.problems.append(_("Fixed note type: %s") % model['name'])

    def fixInvalidCardOrdinal(self):
        for model in self.col.models.all():
            if model['type'] == MODEL_STD:
                self.template(
                    f"""select id, nid, ord from cards where (ord <0 or ord >= {len(model['tmpls'])}) and nid in (select id from notes where mid = {model['id']})""",
                    "Deleted card {} of note {} because its ord {} does not belong to its model",
                    "Deleted %d card with missing template.",
                    "Deleted %d cards with missing template.",
                    lambda lines: self.remCards([line[0]for line in lines])
                )

    def fixWrongNumberOfField(self):
        for model in self.col.models.all():
            # notes with invalid field count
            l = self.db.all(
                "select id, flds from notes where mid = ?", model['id'])
            nids = []
            for (nid, flds) in l:
                nbFieldNote = flds.count("\x1f") + 1
                nbFieldModel = len(model['flds'])
                if nbFieldNote != nbFieldModel:
                    nids.append(nid)
                    self.problems.append(f"""Note {nid} with fields «{flds}» has {nbFieldNote} fields while its model {model['name']} has {nbFieldModel} fields""")
            if nids:
                self.remNotes([line[0]for line in lines])


    def fixNoteWithoutCard(self):
        noteWithoutCard = self.col.conf.get("noteWithoutCard", True)
        if noteWithoutCard:
            l = self.db.all("""select id, flds, tags, mid from notes where id not in (select distinct nid from cards)""")
            for nid, flds, tags, mid in l:
                note = self.getNote(nid)
                note.addTag("NoteWithNoCard")
                note.flush()
                model = note.model()
                template0 = model["tmpls"][0]
                self._newCard(note,template0, self.nextID("pos"))
                self.problems.append("No cards in note {} with fields «{}» and tags «{}» of model {}. Adding card 1 and tag «NoteWithNoCard».".format(nid, flds, tags, mid))
            if l:
                self.problems.append("Created %d cards for notes without card"% (len(l)))
        else:
            self.template(
                """select id, flds, tags, mid from notes where id not in (select distinct nid from cards)""",
                "Deleting note {} with fields «{}» and tags «{}» of model {} because it has no card.",
                "Deleted %d note with no cards.",
                "Deleted %d notes with no cards.",
                lambda lines: self.remNotes([line[0]for line in lines])
            )

    def fixCardWithoutNote(self):
        self.template(
            "select id, nid from cards where nid not in (select id from notes)",
            "Deleted card {} of note {} because this note does not exists.",
            "Deleted %d card with missing note.",
            "Deleted %d cards with missing note.",
            lambda lines: self.remCards([line[0]for line in lines])
        )

    def fixOdueType1(self):
         # cards with odue set when it shouldn't be
         self.template(
             f"select id,nid from cards where odue > 0 and type={CARD_LRN} and not odid",
             "set odue of card {} of note {} to 0, because it was positive while type was 1 (i.e. card in learning)",
             "Fixed %d card with invalid properties.",
             "Fixed %d cards with invalid properties.",
             lambda lines:(self.db.execute("update cards set odue=0 where id in "+ids2str([line[0] for line in lines]))))

    def fixOdueQueue2(self):
        self.template(
            f"select id, nid from cards where odue > 0 and queue={CARD_DUE} and not odid",
            "set odue of card {} of note {} to 0, because it was positive while queue was 2 (i.e. in the review queue).",
            "Fixed %d card with invalid properties.",
            "Fixed %d cards with invalid properties.",
             lambda lines:(self.db.execute("update cards set odue=0 where id in "+ids2str([line[0] for line in lines]))))



    def fixOdidOdue(self):
        self.template(
            """select id, odid, did from cards where odid > 0 and did in %s""" % ids2str([did for did in self.col.decks.allIds() if not self.col.decks.isDyn(did)]),# cards with odid set when not in a dyn deck
            "Card {}: Set odid and odue to 0 because odid was {} while its did was {} which is not filtered(a.k.a. not dymanic).",
            "Fixed %d card with invalid properties.",
            "Fixed %d cards with invalid properties.",
            lambda lists: self.db.execute("update cards set odid=0, odue=0 where id in "+
                                          ids2str([list[0] for list in lists]))
        )

    def registerNotes(self):
        # tags
        self.col.tags.registerNotes()

    def updateAllFieldcache(self):
        # field cache
        for model in self.col.models.all():
            self.updateFieldCache(self.col.models.nids(model))

    def atMost1000000Due(self):
        # new cards can't have a due position > 32 bits
        curs = self.db.cursor()
        curs.execute(f"""update cards set due = 1000000, mod = ?, usn = ? where due > 1000000
        and type = {CARD_NEW}""", (intTime(), self.col.usn()))
        if curs.rowcount:
            self.problems.append("Fixed %d cards with due greater than 1000000 due." % curs.rowcount)

    def setNextPos(self):
        # new card position
        self.col.conf['nextPos'] = self.db.scalar(
            "select max(due)+1 from cards where type = 0") or 0

    def reasonableRevueDue(self):
        self.template(# reviews should have a reasonable due #
            "select id, due from cards where queue = 2 and due > 100000",
            "Changue  of card {}, because its due is {} which is excessive",
            "Reviews had incorrect due date.",
            "Reviews had incorrect due date.",
            lambda lists: self.db.execute(
                "update cards set due = ?, ivl = 1, mod = ?, usn = ? where id in %s"
                % ids2str([list[0] for list in lists]), self.sched.today, intTime(), self.col.usn())
        )

    # v2 sched had a bug that could create decimal intervals
    def fixFloatIvlInCard(self):
        curs = self.db.cursor()
        curs.execute("update cards set ivl=round(ivl),due=round(due) where ivl!=round(ivl) or due!=round(due)")
        if curs.rowcount:
            self.problems.append("Fixed %d cards with v2 scheduler bug." % curs.rowcount)

    def fixFloatIvlInRevLog(self):
        curs = self.db.cursor()
        curs.execute("update revlog set ivl=round(ivl),lastIvl=round(lastIvl) where ivl!=round(ivl) or lastIvl!=round(lastIvl)")
        if curs.rowcount:
            self.problems.append("Fixed %d review history entires with v2 scheduler bug." % curs.rowcount)

    def fixFloatDue(self):
        self.template(
            "select id, due from cards where due != round(due)",
            "Round the due of card {} because it was {} (this is a known bug of schedule v2.",
            "Fixed %d cards with v2 scheduler bug.",
            "Fixed %d cards with v2 scheduler bug.")

    def doubleCard(self):
        l = self.db.all("""select nid, ord, count(*), GROUP_CONCAT(id) from cards group by ord, nid having count(*)>1""")
        toRemove = []
        for nid, ord, count, cids in l:
            cids = cids.split(",")
            cids = [int(cid) for cid in cids]
            cards = [anki.cards.Card(self,cid) for cid in cids]
            bestCard = max(cards, key = (lambda card: (card.ivl, card.factor, card.due)))
            bestCid = bestCard.id
            self.problems.append(f"There are {count} card for note {nid} at ord {ord}. They are {cids}. We only keep {bestCid}")
            toRemove += [cid for cid in cids  if cid!= bestCid]
        if toRemove:
            self.remCards(toRemove)

    def ensureSomeNoteType(self):
        if self.col.models.ensureNotEmpty():
            self.problems.append("Added missing note type.")
