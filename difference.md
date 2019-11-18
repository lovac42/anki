# Differences with anki.
This files list the difference between regular anki and this forked
version. It also lists the different options in the Preferences's extra page.

## Explain errors
You obtain more detailled error message if a sync fail, and if you try
do do a «Check database».

It transform the very long method `fixIntegrity` into plenty of small
function. It would helps to do add-ons for this forked version of anki.

In the preferences, the button «Note with no card: create card 1
instead of deleting the note» chage the behavior of anki when he finds
a note which has no more card. This allow to lose the content of the
note, and let you correct the note instead to generate cards.

## Limit the total number of cards seen today
In the preferences, you can check "Limit the total number of cards
seen by day in a deck". If you do so, in the deck's option's
configuration window, in the "general" tab, you can decide the maximal
number of cards you see in the deck. This put a limit on the sum of
both reviewed cards and new cards. So, the days where you have a lot
of cards to review, you'll have few or no new cards, and you'll have
more cards if you did have little to review.

A fourth number will thus be shown in the deck overview windows.

