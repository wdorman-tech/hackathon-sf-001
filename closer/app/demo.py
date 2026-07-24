"""Demo seeding — start the story mid-negotiation so a crash never costs the demo.

With DEMO_MODE=true the app pre-seeds one deal already past research (mock
valuation loaded, state NEGOTIATING) on startup. You can also POST /demo/seed to
mint a fresh one on demand. Either way you get a deal_id to drive with /simulate
or open on the dashboard at /?deal=<id>.
"""

from __future__ import annotations

from app import research
from app import store as store_mod
from app.auth import DEV_USER_ID
from app.state import Deal, DealState


def seed_demo(user_id: str = DEV_USER_ID) -> Deal:
    """Create a NEGOTIATING deal for the demo car (2019 Mazda CX-5), research done."""
    store = store_mod.get_store()
    payload = research._normalize(dict(research.MOCK_PAYLOAD),
                                  "https://example.com/2019-mazda-cx-5", 16000,
                                  list(research.MOCK_PAYLOAD["steps"]))
    val = research.to_valuation(payload)
    deal = Deal(
        user_id=user_id,
        title="2019 Mazda CX-5 Touring AWD",
        listing_link="https://example.com/2019-mazda-cx-5",
        phone=None,
        state=DealState.NEGOTIATING,
        asking=val["asking"], V=val["V"], R=val["R"],
        research=payload, research_steps=payload.get("steps", []),
    )
    store.save_deal(deal)
    return deal
