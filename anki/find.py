# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import re
import sre_constants
import unicodedata

from anki.consts import *
from anki.hooks import *
from anki.utils import (fieldChecksum, ids2str, intTime, joinFields,
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

    def find(self, query, ifInvalid, sqlBase, order="", groupBy="", tuples=False, rev=False):
        """
        Return the result of the query

        query -- a query as in browser
        ifInvalid -- method returning some value to return if the query is invalid
        sqlBase -- methods which, given preds and order, states in which table/joined table to select
        order -- if it's not empty, the string containing "order by"
        tuples -- whether the query should return tuple. By default it returns only a list of id.
        rev -- whether values should be returned in reversed order

        """
        if order is True:
            #used only for test
            order = self._order()
        if order:
            order = f" order by {order}"
        tokens = self._tokenize(query)
        preds, args = self._where(tokens)
        if preds is None:
            return ifInvalid()
        if preds:
            preds = "(" + preds + ")"
        else:
            preds = "1"
        sql = sqlBase(preds, order)
        sql += preds
        if groupBy:
            sql += " group by "+groupBy
        if order:
            sql += " " + order
        try:
            if tuples:
                l = self.col.db.all(sql, *args)
            else:
                l = self.col.db.list(sql, *args)
            if rev:
                l.reverse()
            return l
        except Exception as e:
            # invalid grouping
            print(f"On query «{query}», sql «{sql}» return empty because of {e}")
            return []

    def findCards(self, *args, withNids=False, oneByNote=False, **kwargs):
        """Return the set of card ids, of card satisfying predicate preds,
        where c is a card and n its note, ordered according to the sql
        `order`

        withNids -- whether the query should also returns note ids"""
        # can we skip the note table?
        def ifInvalid():
            raise Exception("invalidSearch")
        selectNote = ", c.nid" if withNids else ""
        groupBy = "c.nid" if oneByNote else ""
        selectCard = "min(c.id)" if oneByNote else "c.id"
        def sqlBase(preds, order):
            if "n." not in preds and "n." not in order:
                return f"select {selectCard}{selectNote} from cards c where "
            else:
                return f"select {selectCard}{selectNote} from cards c, notes n where c.nid=n.id and "
        # order
        return self.find(*args, ifInvalid=ifInvalid, sqlBase=sqlBase, tuples=withNids, groupBy=groupBy, **kwargs)

    def findNotes(self, *args, **kwargs):
        """Return a list of notes ids for QUERY."""
        def sqlBase(*args, **kwargs):
            return """
select distinct(n.id) from cards c, notes n where c.nid=n.id and """
        def ifInvalid():
            return []
        return self.find(*args, ifInvalid=ifInvalid, sqlBase=sqlBase, **kwargs)

    # Tokenizing
    ######################################################################

    def _tokenize(self, query):
        inQuote = False
        tokens = []
        token = ""
        for c in query:
            # quoted text
            if c in ("'", '"'):
                if inQuote:
                    if c == inQuote:
                        inQuote = False
                    else:
                        token += c
                elif token:
                    # quotes are allowed to start directly after a :
                    if token[-1] == ":":
                        inQuote = c
                    else:
                        token += c
                else:
                    inQuote = c
            # separator (space and ideographic space)
            elif c in (" ", '\u3000'):
                if inQuote:
                    token += c
                elif token:
                    # space marks token finished
                    tokens.append(token)
                    token = ""
            # nesting
            elif c in ("(", ")"):
                if inQuote:
                    token += c
                else:
                    if c == ")" and token:
                        tokens.append(token)
                        token = ""
                    tokens.append(c)
            # negation
            elif c == "-":
                if token:
                    token += c
                elif not tokens or tokens[-1] != "-":
                    tokens.append("-")
            # normal character
            else:
                token += c
        # if we finished in a token, add it
        if token:
            tokens.append(token)
        return tokens

    # Query building
    ######################################################################

    def _where(self, tokens):
        # state and query
        s = dict(isnot=False, isor=False, join=False, q="", bad=False)
        args = []
        def add(txt, wrap=True):
            # failed command?
            if not txt:
                # if it was to be negated then we can just ignore it
                if s['isnot']:
                    s['isnot'] = False
                    return
                else:
                    s['bad'] = True
                    return
            elif txt == "skip":
                return
            # do we need a conjunction?
            if s['join']:
                if s['isor']:
                    s['q'] += " or "
                    s['isor'] = False
                else:
                    s['q'] += " and "
            if s['isnot']:
                s['q'] += " not "
                s['isnot'] = False
            if wrap:
                txt = "(" + txt + ")"
            s['q'] += txt
            s['join'] = True
        for token in tokens:
            if s['bad']:
                return None, None
            # special tokens
            if token == "-":
                s['isnot'] = True
            elif token.lower() == "or":
                s['isor'] = True
            elif token == "(":
                add(token, wrap=False)
                s['join'] = False
            elif token == ")":
                s['q'] += ")"
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
        if s['bad']:
            return None, None
        return s['q'], args

    # Ordering
    ######################################################################

    def _order(self):
        # required only for tests
        type = self.col.conf['sortType']
        sort = None
        if type.startswith("note"):
            if type == "noteCrt":
                sort = "n.id, c.ord"
            elif type == "noteMod":
                sort = "n.mod, c.ord"
            elif type == "noteFld":
                sort = "n.sfld collate nocase, c.ord"
        elif type.startswith("card"):
            if type == "cardMod":
                sort = "c.mod"
            elif type == "cardReps":
                sort = "c.reps"
            elif type == "cardDue":
                sort = "c.type, c.due"
            elif type == "cardEase":
                sort = "c.type == 0, c.factor"
            elif type == "cardLapses":
                sort = "c.lapses"
            elif type == "cardIvl":
                sort = "c.ivl"
        if not sort:
            # deck has invalid sort order; revert to noteCrt
            sort = "n.id, c.ord"
        return sort

    # Commands
    ######################################################################

    def _findTag(self, args):
        """A sql query as in 'tag:val'. Add the tag val to args. Returns a
        query which, given a tag, search it.

        """
        (val, args) = args
        if val == "none":
            return 'n.tags = ""'
        val = val.replace("*", "%")
        if not val.startswith("%"):
            val = "% " + val
        if not val.endswith("%") or val.endswith('\\%'):
            val += " %"
        args.append(val)
        return "n.tags like ? escape '\\'"

    def _findCardState(self, args):
        """A sql query, as in 'is:foo'"""
        (val, args) = args
        if val in ("review", "new", "learn"):
            if val == "review":
                n = CARD_DUE
            elif val == "new":
                n = CARD_NEW
            else:
                return f"queue in ({QUEUE_LRN}, {QUEUE_DAY_LRN})"
            return "type = %d" % n
        elif val == "suspended":
            return f"c.queue = {QUEUE_SUSPENDED}"
        elif val == "buried":
            return f"c.queue in ({QUEUE_USER_BURIED}, {QUEUE_SCHED_BURIED})"
        elif val == "due":
            return f"""
(c.queue in ({QUEUE_REV},{QUEUE_DAY_LRN}) and c.due <= %d) or
(c.queue = {QUEUE_LRN} and c.due <= %d)""" % (
    self.col.sched.today, self.col.sched.dayCutoff)

    def _findFlag(self, args):
        """A sql query restricting cards to the one whose flag is `val`, as in
        'flag:val'

        """
        (val, args) = args
        if not val or val not in "01234":
            return
        val = int(val)
        mask = 2**3 - 1
        return "(c.flags & %d) == %d" % (mask, val)

    def _findRated(self, args):
        """A sql query restricting cards as in 'rated:val', where val is of
        the form numberOfDay or rated:numberOfDay:ease.

        I.e. last review is at most `numberOfDay` days ago, and the button
        pressed was `ease`.

        """
        # days(:optional_ease)
        (val, args) = args
        r = val.split(":")
        try:
            days = int(r[0])
        except ValueError:
            return
        days = min(days, 31)
        # ease
        ease = ""
        if len(r) > 1:
            if r[1] not in ("1", "2", "3", "4"):
                return
            ease = "and ease=%s" % r[1]
        cutoff = (self.col.sched.dayCutoff - 86400*days)*1000
        return ("c.id in (select cid from revlog where id>%d %s)" %
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
        return "c.id > %d" % cutoff

    def _findProp(self, args):
        # extract
        (val, args) = args
        match = re.match("(^.+?)(<=|>=|!=|=|<|>)(.+?$)", val)
        if not match:
            return
        prop, cmp, val = match.groups()
        prop = prop.lower()
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
        q = []
        if prop == "due":
            val += self.col.sched.today
            # only valid for review/daily learning
            q.append(f"(c.queue in ({QUEUE_REV},{QUEUE_DAY_LRN}))")
        elif prop == "ease":
            prop = "factor"
            val = int(val*1000)
        q.append("(%s %s %s)" % (prop, cmp, val))
        return " and ".join(q)

    def _findText(self, val, args):
        val = val.replace("*", "%")
        args.append("%"+val+"%")
        args.append("%"+val+"%")
        return "(n.sfld like ? escape '\\' or n.flds like ? escape '\\')"

    def _findNids(self, args):
        """A sql query restricting to notes whose id is in the list
        `val`. `val` should contains only numbers and commas. It
        corresponds to the query `nid:val`.

        """
        (val, args) = args
        if re.search("[^0-9,]", val):
            return
        return "n.id in (%s)" % val

    def _findCids(self, args):
        """A sql query restricting to cards whose id is in the list
        `val`. `val` should contains only numbers and commas. It
        corresponds to the query `cid:val`.

        """
        (val, args) = args
        if re.search("[^0-9,]", val):
            return
        return "c.id in (%s)" % val

    def _findMid(self, args):
        """A sql query restricting model (i.e. note type) to whose id is in
        the list `val`. `val` should contains only numbers and
        commas. It corresponds to the query `mid:val`.

        """
        (val, args) = args
        if re.search("[^0-9]", val):
            return
        return "n.mid = %s" % val

    def _findDid(self, args):
        (val, args) = args
        if re.search("[^0-9]", val):
            return
        return "c.did = %s" % val

    def _findModel(self, args):
        """A sql query restricting model (i.e. note type) to whose name is in
        the list `val`. `val` should contains only numbers and
        commas. It corresponds to the query `mid:val`.

        """
        (val, args) = args
        ids = []
        val = val.lower()
        for model in self.col.models.all():
            if unicodedata.normalize("NFC", model['name'].lower()) == val:
                ids.append(model['id'])
        return "n.mid in %s" % ids2str(ids)

    def _findDeck(self, args):
        # if searching for all decks, skip
        (val, args) = args
        if val == "*":
            return "skip"
        # deck types
        elif val == "filtered":
            return "c.odid"
        def dids(did):
            if not did:
                return None
            return self.col.decks.childDids(did, includeSelf=True)
        # current deck?
        ids = None
        if val.lower() == "current":
            ids = dids(self.col.decks.current()['id'])
        elif "*" not in val:
            # single deck
            ids = dids(self.col.decks.id(val, create=False))
        else:
            # wildcard
            ids = set()
            val = re.escape(val).replace(r"\*", ".*")
            for d in self.col.decks.all():
                if re.match("(?i)"+val, unicodedata.normalize("NFC", d['name'])):
                    ids.update(dids(d['id']))
        if not ids:
            return
        sids = ids2str(ids)
        return "c.did in %s or c.odid in %s" % (sids, sids)

    def _findTemplate(self, args):
        # were we given an ordinal number?
        (val, args) = args
        try:
            num = int(val) - 1
        except:
            num = None
        if num is not None:
            return "c.ord = %d" % num
        # search for template names
        lims = []
        for model in self.col.models.all():
            for template in model['tmpls']:
                if unicodedata.normalize("NFC", template['name'].lower()) == val.lower():
                    if model['type'] == MODEL_CLOZE:
                        # if the user has asked for a cloze card, we want
                        # to give all ordinals, so we just limit to the
                        # model instead
                        lims.append("(n.mid = %s)" % model['id'])
                    else:
                        lims.append("(n.mid = %s and c.ord = %s)" % (
                            model['id'], template['ord']))
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
                if unicodedata.normalize("NFC", fieldType['name'].lower()) == field:
                    mods[str(model['id'])] = (model, fieldType['ord'])
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
            flds = splitFields(flds)
            ord = mods[str(mid)][1]
            strg = flds[ord]
            try:
                if re.search("(?si)^"+regex+"$", strg):
                    nids.append(id)
            except sre_constants.error:
                return
        if not nids:
            return "0"
        return "n.id in %s" % ids2str(nids)

    def _findDupes(self, args):
        # caller must call stripHTMLMedia on passed val
        (val, args) = args
        try:
            mid, val = val.split(",", 1)
        except OSError:
            return
        csum = fieldChecksum(val)
        nids = []
        for nid, flds in self.col.db.execute(
                "select id, flds from notes where mid=? and csum=?",
                mid, csum):
            if stripHTMLMedia(splitFields(flds)[0]) == val:
                nids.append(nid)
        return "n.id in %s" % ids2str(nids)

# Find and replace
##########################################################################

def findReplace(col, nids, src, dst, regex=False, field=None, fold=True):
    "Find and replace fields in a note."
    mmap = {}
    if field:
        for model in col.models.all():
            for fieldType in model['flds']:
                if fieldType['name'].lower() == field.lower():
                    mmap[str(model['id'])] = fieldType['ord']
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
    d = []
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
            d.append(dict(nid=nid,flds=flds,u=col.usn(),mod=intTime()))
    if not d:
        return 0
    # replace
    col.db.executemany(
        "update notes set flds=:flds,mod=:mod,usn=:u where id=:nid", d)
    col.updateFieldCache(nids)
    col.genCards(nids)
    return len(d)

def fieldNames(col, downcase=True):
    fields = set()
    for model in col.models.all():
        for fieldType in model['flds']:
            name=fieldType['name'].lower() if downcase else fieldType['name']
            if name not in fields: #slower w/o
                fields.add(name)
    return list(fields)

def fieldNamesForNotes(col, nids):
    fields = set()
    mids = col.db.list("select distinct mid from notes where id in %s" % ids2str(nids))
    for mid in mids:
        model = col.models.get(mid)
        for name in col.models.fieldNames(model):
            if name not in fields: #slower w/o
                fields.add(name)
    return sorted(fields, key=lambda x: x.lower())

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
            model = col.models.get(mid)
            for fieldIndex, fieldType in enumerate(model['flds']):
                if fieldType['name'].lower() == fieldName.lower():
                    fields[mid] = fieldIndex
                    break
        return fields[mid]
    for nid, mid, flds in col.db.all(
        "select id, mid, flds from notes where id in "+ids2str(
            col.findNotes(search))):
        flds = splitFields(flds)
        ord = ordForMid(mid)
        if ord is None:
            continue
        val = flds[ord]
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
