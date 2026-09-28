"""Legal intake triage: the front door of a law firm's practice areas.

A demand arrives by e-mail (the area's mailbox, a forward from a lawyer, or the e-mail a
form sends for WhatsApp, phone and meeting requests). Deterministic filters drop the noise,
the conversation is deduplicated, a language model prepares a decision package, and a
person decides on a card. The approval, not the model, creates the task on the board, the
row in the registry and the reply to the client.
"""

__version__ = "0.1.0"
