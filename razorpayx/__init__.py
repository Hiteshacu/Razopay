"""Payout advice authenticity for RazorpayX.

A vendor handed a NEFT or RTGS payout advice cannot tell whether it is real.
The money has legitimately not arrived yet — those rails settle in batches —
so checking their own bank proves nothing, and a soundbox announces UPI
credits, not these. This package closes that window: RazorpayX signs the
advice when it issues it, and the vendor verifies the image they were sent.
"""

from .advice import PayoutAdvice, render, sample_advice

__all__ = ["PayoutAdvice", "render", "sample_advice"]
