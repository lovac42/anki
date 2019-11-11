# Differences with anki.
This files list the difference between regular anki and this forked
version. It also lists the different options in the Preferences's extra page.

## Add/remove deck prefix (683170394)
In the browser, you can select cards, and then do `Decks > Add
prefix`, to add the same prefix to the deck name of all of those
cards. This ensure that they all belong to a same deck, while keeping
the same deck hierarchy. `Decks > Remove prefix` allows to remove this
common prefix and thus cancel the action `Add prefix`.

## Added today (861864770)
Add an option in the add card window to open the browser with notes
created today.


## Advanced browser (874215009)
This add-on adds many features. In particular, for devs, it adds a
class for browser's column, in order to add more columns easily

This add-on adds many features to the browser.

### Improvment for dev
To add a column, you only need to add one more object of type BrowserColumn.
This add-on adds many features. In particular, for devs, it adds a
class for browser's column, in order to add more columns easily

### Sorting everything
You can sort any columns. Including decks, cards, notes, tags.

### Improvment for dev
To add a column, you only need to add one more object of type BrowserColumn.

## Allow to keep first field empty (46741504)

## Allowing complex card template (1713990897)
All version of anki bugs if you have a complex card template. For example,
if your template is enclosed in {{^field}} and {{/field}}. This option
allow complex card template. The only problem is that official anki
and smartphone apps won't be able to display those cards, and may want
to remove them if you press «check cards».

## Anki quicker (802285486)
Those modification makes anki quicker. Technical details are on the
add-on page.

## Batch Edit (291119185)
Allow to make the same edit to multiple cards. Either changing a
field, or adding text after/before it.

In preferences, you can decide whether you add a new line between the
old text and the added one.

## Copy note (1566928056)
If you select notes in the browser, and do `Notes>Copy Notes` or
`Ctrl+Alt+C`, a copy of the notes are created.

You have two options in the preferences:
* "Preserve date of creation": keeps the «Created» value in the
  browser. It is particularly interesting if you review cards
  according to their creation date.
* "Preserve easyness, interval, due date, ...": this create a copy of
  each card, as close as possible to the original card. If you uncheck
  this, instead, your new cards will be fresh, and you'll start review
  from 0.

## Correcting due (127334978)
Anki precomputes the order of the new cards to see. While in theory,
this is all nice, in practice it bugs in some strange case. Those
cases may occur in particular if you download a shared deck having
this bug. If you want details, it is explained here
https://github.com/Arthur-Milchior/anki/blob/master/documentation/due.md

## Explain errors
You obtain more detailled error message if a sync fail, and if you try
do do a «Check database».

It transform the very long method `fixIntegrity` into plenty of small
function. It would helps to do add-ons for this forked version of anki.

## Export notes selected in the Browser (1983204951)
Selects some cards in the browser. Then `Cards>Export cards` allow you
to export the cards. This is similar to exporting a deck, except that
you have more fine control. You can essentially export anything that
you can query in the browser or that you can select.

Note that, if you export a deck, or a selection of cards, and that you
export cards, you are also exporting the notes of those
cards. However, some cards may be missing. When importing those cards,
the missing cards will be generated, and will be totally new. You may
lose data this way.  In the preference "Export siblings of exported
cards" allow you to avoid losing data, by exporting the siblings of
exported cards. The problem being, of course, that you may export
cards in decks you did not select. Thus, importing those cards may
potentially create more decks than expected.

## Refresh browser (1347728560, 832679841)
Add the short-cut CTRL-F5 in browser to update the search

## Usable card report (25425599)
Add more informations in the «empty card» report.
### Minutes in the browser
Allow the columns in browser to show hours and minutes. It may helps
to see more precisely when cards in learning are due, and see in which
order cards and notes where added/edited.

## When changing note type, preserve names (513858554)
If you change a note's type, and the old and the new note have
fields/cards with the same name, then those fields/cards are mapped by
default such that they keep the same name.

In preferences, you can unbox "When changing note type, preserve names
if possible." to recover anki's default behavior, i.e. sending first
element to first one, second to second, etc..

