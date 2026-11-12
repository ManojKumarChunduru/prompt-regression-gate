"""prompt-regression-gate: a PR gate for Prompt Builder template changes.

The package exists because a review score on thirty summaries cannot say whether a prompt change
is better or noise, and cannot see a claim the case does not support. Everything on the default
path is standard library; the api, openai and gemini extras are imported inside the functions
that need them and never by this package's import.
"""

__version__ = "0.1.0"
