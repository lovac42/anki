# Differences with anki.
This files list the difference between regular anki and this forked
version. It also lists the different options in the Preferences's extra page.

## Anki quicker (802285486)
Those modification makes anki quicker. Technical details are on the
add-on page.

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

## Usable card report (25425599)
Add more informations in the «empty card» report.

