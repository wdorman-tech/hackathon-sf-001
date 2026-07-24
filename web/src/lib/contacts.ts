// Single source of truth for the two live personas — shared between the
// landing page's "Try it live" section and the standalone printable card.
// sms: links use the iOS `&body=` form (not Android's `?body=`) since Closer
// is an iMessage-first product — see DESIGN.md's QR decision.
//
// Both numbers, the listing link, and the opener text are real values pulled
// from the actual demo fixture (closer/tests/fixtures/deal_camry.json) after
// the Sync 1 merge — not invented. Marcus is a real seller agent with his own
// Linq number (~/seller-agent, per CLAUDE.md), not a "pretend to be the
// seller" prompt — texting him puts *you* in the buyer's seat against a real
// AI seller, same as Closer does against a real AI buyer.

export const BUYER_CONTACT = {
  role: "Play the buyer",
  name: "Closer AI",
  phoneDisplay: "(205) 261-1117",
  phoneE164: "+12052611117",
  blurb:
    "Text a listing and get coached in real time — the exact number to send, and when the seller's bluffing.",
  opener:
    "Hi Closer — check out this listing, what should I offer? https://www.facebook.com/marketplace/item/1102938471",
  qrSrc: "/qr-buyer.svg",
}

export const SELLER_CONTACT = {
  role: "Meet the seller",
  name: "Marcus",
  phoneDisplay: "(205) 490-9563",
  phoneE164: "+12054909563",
  blurb:
    "A real seller agent, not a script — he's selling a 2008 Camry LE and he will bluff you. Text him and see for yourself.",
  opener: "Hey, I saw your 2008 Camry LE listed at $6,400 — still available?",
  qrSrc: "/qr-seller.svg",
}

function smsHref(phoneE164: string, body: string) {
  return `sms:${phoneE164}&body=${encodeURIComponent(body)}`
}

export const BUYER_SMS_HREF = smsHref(BUYER_CONTACT.phoneE164, BUYER_CONTACT.opener)
export const SELLER_SMS_HREF = smsHref(SELLER_CONTACT.phoneE164, SELLER_CONTACT.opener)
