import anki.deck
from anki.consts import *


class Deck(anki.deck.Deck):
    ## Deck Browser
    @staticmethod
    def _options():
        """html cell, to show gear opening options"""
        return f"""
      <td align=center class=opts>
        <a onclick='return pycmd("opts:{self.getId()}");'>
          <img src='/_anki/imgs/gears.svg' class=gears>
        </a>
      </td>"""

    def _renderDeckTree(self, depth=0):
        """Html used to show the deck tree.

        keyword arguments
        depth -- the number of ancestors, excluding itself
        decks -- A list of decks, to render, with the same parent. See top of this file for detail"""
        if self.isLeaf():
            return ""
        buf = "".join(child._deckRow(depth) for child in self.getChildren())
        return buf

    def _deckRow(self, depth):
        """The HTML for a single deck (and its descendant)

        Keyword arguments:
        depth -- indentation argument (number of ancestors)
        """
        name = self.getBaseName()
        did = self.getId()
        rev = self.count['due']['rev']
        lrn = self.count['due']['lrn']
        new = self.count['due']['new']
        if self.isDefault() and not self.getParent().isLeaf() and self.isLeaf():
            # if the default deck is empty, hide it
            if not self.manager.col.db.scalar("select 1 from cards where did = 1 limit 1"):
                return ""
        prefix = "-"
        if self['collapsed']:
            prefix = "+"
        due = rev + lrn
        def indent():
            return "&nbsp;"*6*depth
        if did == self.manager.col.conf['curDeck']:
            klass = 'deck current'
        else:
            klass = 'deck'
        buf = """
  <tr class='%s' id='%d'>""" % (klass, did)
        # deck link
        if not self.isLeaf():
            collapse = """
      <a class=collapse href=# onclick='return pycmd(\"collapse:%d\")'>%s</a>""" % (did, prefix)
        else:
            collapse = """
      <span class=collapse></span>"""
        if self.isDyn():
            extraclass = "filtered"
        else:
            extraclass = ""
        buf += """

    <td class=decktd colspan=5>%s%s
       <a class="deck %s" href=# onclick="return pycmd('open:%d')">%s
       </a>
    </td>"""% (
            indent(), collapse, extraclass, did, name)
        # due counts
        def nonzeroColour(cnt, colour):
            if not cnt:
                colour = "#e0e0e0"
            if cnt >= 1000:
                cnt = "1000+"
            return """
      <font color='%s'>
         %s
      </font>""" % (colour, cnt)
        buf += """
    <td align=right>%s
    </td>
    <td align=right>%s
    </td>""" % (
            nonzeroColour(due, colDue),
            nonzeroColour(new, colNew))
        # options
        buf += ("""
    <td align=center class=opts>
      <a onclick='return pycmd(\"opts:%d\");'>
        <img src='/_anki/imgs/gears.svg' class=gears>
      </a>
    </td>
  </tr>""" % did)
        # children
        if not self['collapsed']:
            buf += self._renderDeckTree(depth+1)
        return buf
