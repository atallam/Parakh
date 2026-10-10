"""F17: calibration, scorecards and the decision journal (plan 04 §2, plan 06 §6).

The modules here answer one question: is the score worth trusting? They read prices, the stored
snapshots, the alert log and the watchlist, and write reports; none of them changes a score, a weight
or a verdict (AG-03, D13). A weight change is a config edit you make after reading the report.
"""
