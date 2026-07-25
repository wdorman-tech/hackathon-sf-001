// Single source of truth for Closer's live persona — shared between the
// landing page's "Try it live" section and the standalone printable card.
// sms: links use the iOS `&body=` form (not Android's `?body=`) since Closer
// is an iMessage-first product — see DESIGN.md's QR decision.
//
// The number, listing link, and opener text are real values pulled from the
// actual demo fixture (closer/tests/fixtures/deal_camry.json), not invented.

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

function smsHref(phoneE164: string, body: string) {
  return `sms:${phoneE164}&body=${encodeURIComponent(body)}`
}

export const BUYER_SMS_HREF = smsHref(BUYER_CONTACT.phoneE164, BUYER_CONTACT.opener)
