from anki.lang import _

class Column:
    def topRow(self):
        pass

class DeckName(Column):
    def topRow(self):
        return f"""
    <th colspan=5 align=left>{_("Deck")}
    </th>"""

    def deckRow(self, deck):
        collapse = f"""
      <a class=collapse href=# onclick='return pycmd(\"collapse:{deck.getId()}\")'>{"+" if deck['collapsed'] else "-"}</a>""" if not deck.isLeaf() else """
      <span class=collapse></span>"""
        return f"""

    <td class=decktd colspan=5>{"&nbsp;"*6*deck.depth()}{collapse}
       <a class="deck {"filtered" if deck.isDyn() else ""}" href=# onclick="return pycmd('open:{deck.getId()}')">{deck.getBaseName()}
       </a>
    </td>"""

class Number:
    def __init__(self, name, key, color):
        self.name = name
        self.key = key
        self.color = color

    def topRow(self):
        return f"""
    <th class=count>{_(self.name)}
    </th>"""

    def deckRow(self, deck):
        cnt = deck.count['due'][self.key]
        if not cnt:
            colour = "#e0e0e0"
        if cnt >= 1000:
            cnt = "1000+"
        return f"""
    <td align=right>
      <font color='{self.color}'>
         {cnt}
      </font>
    </td>"""

class Gear(Column):
    def topRow(self):
        return """
    <th class=optscol>
    </th>"""

    def deckRow(self, deck):
        return f"""
    <td align=center class=opts>
      <a onclick='return pycmd(\"opts:{deck.getId()}\");'>
        <img src='/_anki/imgs/gears.svg' class=gears>
      </a>
    </td>
  </tr>"""
