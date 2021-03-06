# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import re
import sre_constants
import unicodedata

from anki.consts import *
from anki.hooks import *
from anki.utils import (fieldChecksum, ids2str, intTime, joinFields, nthField,
                        splitFields, stripHTMLMedia)

# Find
##########################################################################

class Finder:
    """
    col: the collection used for opening this Finder.
    search: a dictionnary such that the query key:value is evaluated by self.search[key]((value,args)), with args a list of tag. This function potentially add tags (in _findTag) and return a sql part to put after the where. It may also return "skip", in which case the code is not added to sql.
    """

    def __init__(self, col):
        self.col = col
        self.search = dict(
            added=self._findAdded,
            card=self._findTemplate,
            deck=self._findDeck,
            mid=self._findMid,
            did=self._findDid,
            nid=self._findNids,
            cid=self._findCids,
            note=self._findModel,
            prop=self._findProp,
            rated=self._findRated,
            tag=self._findTag,
            dupe=self._findDupes,
            flag=self._findFlag,
        )
        self.search['is'] = self._findCardState
        runHook("search", self.search)

    def _find(self, query, select, order, ifInvalid, tuples=False, groupBy=""):
        tokens = self._tokenize(query)
        preds, args = self._where(tokens)
        if preds is None:
            return ifInvalid()
        order = self._order(order)
        _from = self._from([select, preds, order])
        sql = select + _from + preds + groupBy + order
        try:
            if tuples:
                l = self.col.db.all(sql, *args)
            else:
                l = self.col.db.list(sql, *args)
            if self.col.conf['sortBackwards']:
                l.reverse()
            return l

        except Exception as e:
            # invalid grouping
            print(f"On query «{query}», sql «{sql}» return empty because of {e}")
            return []

    def findCards(self, query, order=False, withNids=False, oneByNote=False):
        """Return a list of card ids for QUERY.

        order --
        * False means not ordering
        * True means using default order
        * one of the order key means to use this key
        * otherwise, order is already the sql value
        """
        def ifInvalid():
            raise Exception("invalidSearch")
        select = "select "
        if oneByNote:
            select += "min(card.id) "
        else:
            select += "card.id "
        if withNids:
            select += ", card.nid "
        groupBy = " group by card.nid " if oneByNote else ""
        return self._find(query, select, order, ifInvalid, withNids, groupBy)

    def findNotes(self, query):
        def ifInvalid():
            return []
        select = "select distinct(note.id) "
        return self._find(query, select, False, ifInvalid)

    def findNotesWithOneCard(self, query, order=False):
        """
        Pairs (cid, nid), with nid unique.
        """
        return self.findCards(query, order, True, True)
    # Tokenizing
    ######################################################################

    def _tokenize(self, query):
        inQuote = False
        tokens = []
        token = ""
        for char in query:
            # quoted text
            if char in ("'", '"'):
                if inQuote:
                    if char == inQuote:
                        inQuote = False
                    else:
                        token += char
                elif token:
                    # quotes are allowed to start directly after a :
                    if token[-1] == ":":
                        inQuote = char
                    else:
                        token += char
                else:
                    inQuote = char
            # separator (space and ideographic space)
            elif char in (" ", '\u3000'):
                if inQuote:
                    token += char
                elif token:
                    # space marks token finished
                    tokens.append(token)
                    token = ""
            # nesting
            elif char in ("(", ")"):
                if inQuote:
                    token += char
                else:
                    if char == ")" and token:
                        tokens.append(token)
                        token = ""
                    tokens.append(char)
            # negation
            elif char == "-":
                if token:
                    token += char
                elif not tokens or tokens[-1] != "-":
                    tokens.append("-")
            # normal character
            else:
                token += char
        # if we finished in a token, add it
        if token:
            tokens.append(token)
        return tokens

    # Query building
    ######################################################################

    def _where(self, tokens):
        """A sql condition to decide which card/notes are used and TODO.
        Or None, None in case of problems"""
        # state and query
        state = dict(isnot=False, isor=False, join=False, q="", bad=False)
        args = []
        def add(txt, wrap=True):
            # failed command?
            if not txt:
                # if it was to be negated then we can just ignore it
                if state['isnot']:
                    state['isnot'] = False
                    return
                else:
                    state['bad'] = True
                    return
            elif txt == "skip":
                return
            # do we need a conjunction?
            if state['join']:
                if state['isor']:
                    state['q'] += " or "
                    state['isor'] = False
                else:
                    state['q'] += " and "
            if state['isnot']:
                state['q'] += " not "
                state['isnot'] = False
            if wrap:
                txt = "(" + txt + ")"
            state['q'] += txt
            state['join'] = True
        for token in tokens:
            if state['bad']:
                return None, None
            # special tokens
            if token == "-":
                state['isnot'] = True
            elif token.lower() == "or":
                state['isor'] = True
            elif token == "(":
                add(token, wrap=False)
                state['join'] = False
            elif token == ")":
                state['q'] += ")"
            # commands
            elif ":" in token:
                cmd, val = token.split(":", 1)
                cmd = cmd.lower()
                if cmd in self.search:
                    add(self.search[cmd]((val, args)))
                else:
                    add(self._findField(cmd, val))
            # normal text search
            else:
                add(self._findText(token, args))
        if state['bad']:
            return None, None
        if state['q'] == "":
            state['q'] = "1"
        else:
            state['q'] = f"({state['q']})"
        return state['q'], args

    @staticmethod
    def _from(queries):
        """Return the from part of a statement, allowing to use the
        queries. Next part of the query must be a boolean statement."""
        # can we skip the note table?
        for query in queries:
            if "note." in query:
                return "from cards card, notes note where card.nid=note.id and "
        return "from cards card where "

    # Ordering
    ######################################################################

    def _order(self, order):
        """sql to order the result of the queries

        order --
        * False means not ordering
        * True means using default order
        * one of the order key means to use this key
        * otherwise, order is already the sql value
        """
        if order is False:
            return ""
        if isinstance(order, str):
            # custom order string provided
            return " order by " + order
        if order is True:
            # use deck default
            type = self.col.conf['sortType']
        else: # order is str, one of the key
            type = order
        sc = "DESC" if self.col.conf['sortBackwards'] else "ASC"
        sort = None
        return f" order by note.id, card.ord"

    # Commands
    ######################################################################

    def _findTag(self, args):
        """A sql query as in 'tag:val'. Add the tag val to args. Returns a
        query which, given a tag, search it.

        """
        (val, args) = args
        if val == "none":
            return 'note.tags = ""'
        val = val.replace("*", "%")
        if not val.startswith("%"):
            val = "% " + val
        if not val.endswith("%") or val.endswith('\\%'):
            val += " %"
        args.append(val)
        return "note.tags like ? escape '\\'"

    def _findCardState(self, args):
        """A sql query, as in 'is:foo'"""
        (val, args) = args
        if val in ("review", "new", "learn"):
            if val == "review":
                note = CARD_DUE
            elif val == "new":
                note = CARD_NEW
            else:
                return f"queue in ({QUEUE_LRN}, {QUEUE_DAY_LRN})"
            return "type = %d" % note
        elif val == "suspended":
            return f"card.queue = {QUEUE_SUSPENDED}"
        elif val == "buried":
            return f"card.queue in ({QUEUE_SCHED_BURIED}, {QUEUE_USER_BURIED})"
        elif val == "due":
            return f"""
(card.queue in ({QUEUE_REV},{QUEUE_DAY_LRN}) and card.due <= %d) or
(card.queue = {QUEUE_LRN} and card.due <= %d)""" % (
    self.col.sched.today, self.col.sched.dayCutoff)

    def _findFlag(self, args):
        """A sql query restricting cards to the one whose flag is `val`, as in
        'flag:val'

        """
        (val, args) = args
        if not val or len(val)!=1 or val not in "01234":
            return
        val = int(val)
        mask = 2**3 - 1
        return "(card.flags & %d) == %d" % (mask, val)

    def _findRated(self, args):
        """A sql query restricting cards as in 'rated:val', where val is of
        the form numberOfDay or rated:numberOfDay:ease.

        I.e. last review is at most `numberOfDay` days ago, and the button
        pressed was `ease`.

        """
        # days(:optional_ease)
        (vals, args) = args
        vals = vals.split(":")
        try:
            days = int(vals[0])
        except ValueError:
            return
        days = min(days, 31)
        # ease
        ease = ""
        if len(vals) > 1:
            if vals[1] not in ("1", "2", "3", "4"):
                return
            ease = "and ease=%s" % vals[1]
        cutoff = (self.col.sched.dayCutoff - 86400*days)*1000
        return ("card.id in (select cid from revlog where id>%d %s)" %
                (cutoff, ease))

    def _findAdded(self, args):
        """A sql query as in 'added:val', it restricts cards to ones which
        were added at most val days ago."""
        (val, args) = args
        try:
            days = int(val)
        except ValueError:
            return
        cutoff = (self.col.sched.dayCutoff - 86400*days)*1000
        return "card.id > %d" % cutoff

    def _findProp(self, args):
        # extract
        (val, args) = args
        match = re.match("(^.+?)(<=|>=|!=|=|<|>)(.+?$)", val)
        if not match:
            return
        prop, cmp, val = match.groups()
        prop = prop.lower() # pytype: disable=attribute-error
        # is val valid?
        try:
            if prop == "ease":
                val = float(val)
            else:
                val = int(val)
        except ValueError:
            return
        # is prop valid?
        if prop not in ("due", "ivl", "reps", "lapses", "ease"):
            return
        # query
        queries = []
        if prop == "due":
            val += self.col.sched.today
            # only valid for review/daily learning
            queries.append(f"(card.queue in ({QUEUE_REV},{QUEUE_DAY_LRN}))")
        elif prop == "ease":
            prop = "factor"
            val = int(val*1000)
        queries.append("(%s %s %s)" % (prop, cmp, val))
        return " and ".join(queries)

    def _findText(self, val, args):
        val = val.replace("*", "%")
        args.append("%"+val+"%")
        args.append("%"+val+"%")
        return "(note.sfld like ? escape '\\' or note.flds like ? escape '\\')"

    def _findNids(self, args):
        """A sql query restricting to notes whose id is in the list
        `val`. `val` should contains only numbers and commas. It
        corresponds to the query `nid:val`.

        """
        (val, args) = args
        if re.search("[^0-9,]", val):
            return
        return "note.id in (%s)" % val

    def _findCids(self, args):
        """A sql query restricting to cards whose id is in the list
        `val`. `val` should contains only numbers and commas. It
        corresponds to the query `cid:val`.

        """
        (val, args) = args
        if re.search("[^0-9,]", val):
            return
        return "card.id in (%s)" % val

    def _findMid(self, args):
        """A sql query restricting model (i.e. note type) to whose id is in
        the list `val`. `val` should contains only numbers and
        commas. It corresponds to the query `mid:val`.

        """
        (val, args) = args
        if re.search("[^0-9]", val):
            return
        return "note.mid = %s" % val

    def _findDid(self, args):
        (val, args) = args
        if re.search("[^0-9]", val):
            return
        return "card.did = %s" % val

    def _findModel(self, args):
        """A sql query restricting model (i.e. note type) to whose name is in
        the list `val`. `val` should contains only numbers and
        commas. It corresponds to the query `mid:val`.

        """
        (val, args) = args
        val = val.lower()
        ids = [model.getId()
               for model in self.col.models.all()
               if unicodedata.normalize("NFC", model.getName().lower()) == val
        ]
        return "note.mid in %s" % ids2str(ids)

    def _findDeck(self, args):
        # if searching for all decks, skip
        (val, args) = args
        if val == "*":
            return "skip"
        # deck types
        elif val == "filtered":
            return "card.odid"
        def dids(deck):
            if not deck:
                return None
            return deck.getDescendantsIds(includeSelf=True)
        # current deck?
        ids = None
        if val.lower() == "current":
            ids = dids(self.col.decks.current())
        elif "*" not in val:
            # single deck
            ids = dids(self.col.decks.byName(val))
        else:
            # wildcard
            ids = set()
            val = re.escape(val).replace(r"\*", ".*")
            for deck in self.col.decks.all():
                if re.match("(?i)"+val, unicodedata.normalize("NFC", deck.getName())):
                    ids.update(dids(deck))
        if not ids:
            return
        sids = ids2str(ids)
        return "card.did in %s or card.odid in %s" % (sids, sids)

    def _findTemplate(self, args):
        # were we given an ordinal number?
        (val, args) = args
        try:
            num = int(val) - 1
        except:
            num = None
        if num is not None:
            return "card.ord = %d" % num
        # search for template names
        lims = []
        for model in self.col.models.all():
            for template in model['tmpls']:
                if unicodedata.normalize("NFC", template.getName().lower()) == val.lower():
                    if model.isCloze():
                        # if the user has asked for a cloze card, we want
                        # to give all ordinals, so we just limit to the
                        # model instead
                        lims.append("(note.mid = %s)" % model.getId())
                    else:
                        lims.append("(note.mid = %s and card.ord = %s)" % (
                            model.getId(), template['ord']))
        return " or ".join(lims)

    def _findField(self, field, val):
        """A sql query restricting the notes to the ones having `val` in the field `field`.

        Same than "field:val". Field is assumed not to be one of the keyword of the browser.

        """
        field = field.lower()
        val = val.replace("*", "%")
        # find models that have that field
        mods = {}
        for model in self.col.models.all():
            for fieldType in model['flds']:
                if unicodedata.normalize("NFC", fieldType.getName().lower()) == field:
                    mods[str(model.getId())] = (model, fieldType['ord'])
        if not mods:
            # nothing has that field
            return
        # gather nids
        regex = re.escape(val).replace("_", ".").replace(re.escape("%"), ".*")
        nids = []
        for (id,mid,flds) in self.col.db.execute("""
select id, mid, flds from notes
where mid in %s and flds like ? escape '\\'""" % (
                         ids2str(list(mods.keys()))),
                         "%"+val+"%"):
            ord = mods[str(mid)][1]
            strg = nthField(flds, ord)
            try:
                if re.search("(?si)^"+regex+"$", strg):
                    nids.append(id)
            except sre_constants.error:
                return
        if not nids:
            return "0"
        return "note.id in %s" % ids2str(nids)

    def _findDupes(self, args):
        # caller must call stripHTMLMedia on passed val
        (val, args) = args
        try:
            mid, val = val.split(",", 1)
        except OSError:
            return
        csum = fieldChecksum(val)
        nids = [
            nid
            for nid, flds in self.col.db.execute("select id, flds from notes where mid=? and csum=?", mid, csum)
            if stripHTMLMedia(nthField(flds, 0)) == val]

        return "note.id in %s" % ids2str(nids)

# Find and replace
##########################################################################

def findReplace(col, nids, src, dst, regex=False, field=None, fold=True):
    "Find and replace fields in a note."
    mmap = {}
    if field:
        for model in col.models.all():
            for fieldType in model['flds']:
                if fieldType.getName().lower() == field.lower():
                    mmap[str(model.getId())] = fieldType['ord']
        if not mmap:
            return 0
    # find and gather replacements
    if not regex:
        src = re.escape(src)
        dst = dst.replace("\\", "\\\\")
    if fold:
        src = "(?i)"+src
    regex = re.compile(src)
    def repl(str):
        return re.sub(regex, dst, str)
    noteData = []
    snids = ids2str(nids)
    nids = []
    for nid, mid, flds in col.db.execute(
        "select id, mid, flds from notes where id in "+snids):
        origFlds = flds
        # does it match?
        sflds = splitFields(flds)
        if field:
            try:
                ord = mmap[str(mid)]
                sflds[ord] = repl(sflds[ord])
            except KeyError:
                # note doesn't have that field
                continue
        else:
            for fieldIndex in range(len(sflds)):
                sflds[fieldIndex] = repl(sflds[fieldIndex])
        flds = joinFields(sflds)
        if flds != origFlds:
            nids.append(nid)
            noteData.append(dict(nid=nid,flds=flds,usn=col.usn(),mod=intTime()))
    if not noteData:
        return 0
    # replace
    col.db.executemany(
        "update notes set flds=:flds,mod=:mod,usn=:usn where id=:nid", noteData)
    col.updateFieldCache(nids)
    col.genCards(nids)
    return len(noteData)

def fieldNames(col, downcase=True):
    fields = set()
    for model in col.models.all():
        for fieldType in model['flds']:
            name=fieldType.getName().lower() if downcase else fieldType.getName()
            if name not in fields: #slower w/o
                fields.add(name)
    return list(fields)

def fieldNamesForNotes(col, nids):
    """The list of field names of models of notes whose id belongs to
    nids."""
    fields = set()
    mids = col.db.list("select distinct mid from notes where id in %s" % ids2str(nids))
    for mid in mids:
        model = col.models.get(mid, orNone=False)
        for name in model.fieldNames():
            if name not in fields: #slower w/o
                fields.add(name)
    return sorted(fields, key=lambda field: field.lower())

# Find duplicates
##########################################################################
# returns array of ("dupestr", [nids])
def findDupes(col, fieldName, search=""):
    # limit search to notes with applicable field name
    if search:
        search = "("+search+") "
    search += "'%s:*'" % fieldName
    # go through notes
    vals = {}
    dupes = []
    fields = {}
    def ordForMid(mid):
        if mid not in fields:
            model = col.models.get(mid, orNone=False)
            for fieldIndex, fieldType in enumerate(model['flds']):
                if fieldType.getName().lower() == fieldName.lower():
                    fields[mid] = fieldIndex
                    break
        return fields[mid]
    for nid, mid, flds in col.db.all(
        "select id, mid, flds from notes where id in "+ids2str(
            col.findNotes(search))):
        ord = ordForMid(mid)
        if ord is None:
            continue
        val = nthField(flds, ord)
        val = stripHTMLMedia(val)
        # empty does not count as duplicate
        if not val:
            continue
        if val not in vals:
            vals[val] = []
        vals[val].append(nid)
        if len(vals[val]) == 2:
            dupes.append((val, vals[val]))
    return dupes
