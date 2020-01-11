# Differences with anki.
This files list the difference between regular anki and this forked
version. It also lists the different options in the Preferences's extra page.

## Add card: change note only if you ask for it (424778276)
Yeah, this description seems ridiculous. But actually, anki does not
respect this.

## Anki quicker (802285486)
Those modification makes anki quicker. Technical details are on the
add-on page.

## Edit new model without full sync (1988880085)

As long as you didn't sync your collection, you can add/remove/edit
field and card type to your new note types without having to do a full sync.

## Explain errors
You obtain more detailled error message if a sync fail, and if you try
do do a «Check database».

It transform the very long method `fixIntegrity` into plenty of small
function. It would helps to do add-ons for this forked version of anki.

In the preferences, the button «Note with no card: create card 1
instead of deleting the note» chage the behavior of anki when he finds
a note which has no more card. This allow to lose the content of the
note, and let you correct the note instead to generate cards.

## Usable card report (25425599)
Add more informations in the «empty card» report.

