# Linq — iMessage / RCS / SMS integration

Linq is the messaging layer we use to send and receive iMessage (with RCS + SMS
fallback) from code. CLI + REST API over real Apple infrastructure.

**For Closer, Linq is not a channel — it is the entire product surface.** There is
no dashboard and no website; every capability ships as a message. So the
affordances below are load-bearing features, not decoration:

| Affordance | What Closer does with it |
|---|---|
| `sender_handle.handle` on inbound | **The auth system.** `user_id = "phone:+1205…"`. No signup, no login. |
| `webhooks listen --forward-to` | Inbound over an outbound connection — **no tunnel, no public URL, no inbound port** |
| `chats typing` | Bracket research (~30s) and every LLM turn, so waiting reads as thinking |
| `messages react` (outbound) | Meaning, not a read receipt: ❗ bluff spotted, ❤️ deal closed. No blanket 👍 on every inbound — the typing indicator already says "we got it" |
| tapbacks (inbound) | A two-tap negotiation loop: 👍 "sent it", 👎 "different number", ❓ "explain the math" |
| `messages send --effect` | `confetti` on close, `fireworks` on a new best, `slam` on a walk. Three per demo, no more. |
| `attachments upload` | The deal card as a real chart — the seller's floor collapsing turn by turn |
| `contacts add` share link / QR | **The signup flow.** Scan, tap send, you're a user. Also clears inbound-first. |

Plan and exact build order: `update_1.md` §5 ("Linq, pushed to the max").

Two limits that shape the design: a Shared Line caps at **20 contacts** (so, 20
concurrent users), and it is **inbound-first** — which is not a limitation here,
it is how accounts get created.

## TWO ACCOUNTS — read this first

There are two separate Linq accounts on this machine, one per agent, so the two
can text **each other**. A single account cannot message itself, and each shared
line caps at 20 contacts, so two lines also doubles the demo headroom.

| | **Closer** (this repo) | Marcus (the seller) |
|---|---|---|
| Role | buyer / negotiator | seller |
| Linq Number | **+12052611117** | +12054909563 |
| CLI profile | `closer` | `seller` |
| Login email | wdorman26@gmail.com | wdorman26+seller@gmail.com |
| Repo | `~/hackathon-sf-001/closer` | `~/seller-agent` |
| Port | 8000 | 8787 |

`~/.linq/config.json` stores ONE *active* profile shared by every process on the
machine. `linq profile use seller` in any terminal would silently repoint
anything relying on the default at the seller's number — no error, wrong line.
Two defences are in place:

- `closer/.env` sets `LINQ_API_KEY` and `LINQ_FROM_NUMBER` **explicitly**, so
  this app never reads the shared file and cannot drift.
- **Every `linq` CLI command for this account needs `--profile closer`.**
  Without it the CLI uses whatever is active, which is how a demo contact ends
  up on the seller's line instead of ours.

```bash
linq profile list                    # shows which is active; we ignore it
linq doctor --profile closer
linq contacts add +1555... --profile closer
linq webhooks listen --profile closer --forward-to http://localhost:8000/webhook
```

**Attachments are bound to the account that uploaded them** — another account's
`attachment_id` returns 404. Media uploaded under `closer` cannot be sent from
the seller's line, and vice versa.

## Account (this app)

| Field | Value |
|---|---|
| Linq Number | `+12052611117` |
| CLI profile | `closer` |
| Tier | Free |
| Line type | Shared Line |
| Login email | wdorman26@gmail.com |
| CLI version | `@linqapp/cli` 2.5.0 (requires Node 22+) |

**Shared Line limits:** max 20 contacts, and inbound-first — a contact must text
`+12052611117` before we can send to them. Paid lines (dedicated number, no
sandbox restrictions) are available via the dashboard.

## Credentials

The API key is **not** in this repo and must never be committed. It is shown
once at signup and Linq does not store the raw value, so it cannot be retrieved
from the server.

Where it lives:

- `~/.linq/config.json` — written by the CLI. Reprint with `linq tokens show`,
  or `linq tokens show --copy` to put it on the clipboard.
- A password manager entry (1Password / Bitwarden / Keychain).

To use it from code, export it rather than hardcoding:

```bash
export LINQ_API_KEY="$(linq tokens show | tr -d '[:space:]')"
```

Lost it? Mint a replacement with `linq tokens create --name "<label>"`, or
rotate in place with `linq tokens regenerate <id>` (immediately revokes the old
secret). Prefer one token per environment (`prod`, `staging`, `ci`) so a single
revoke doesn't take everything down.

## Setup from scratch

```bash
npm install -g @linqapp/cli@latest      # needs Node 22+
linq login --token <linq-api-token>     # existing account
linq whoami                             # confirm identity + Linq Number
linq doctor                             # config + connectivity check
```

New account instead of login:

```bash
linq signup --email <email>                                  # sends 6-digit OTP
linq signup --email <email> --code <otp> --name "<name>"     # completes signup
```

## Core flows

Add a contact, then send. Remember inbound-first on a Shared Line: the contact
texts `+12052611117` first, then we can send.

```bash
linq contacts add +1XXXXXXXXXX
linq contacts list
linq chats create --to +1XXXXXXXXXX --message "Hello" --json   # returns chat.id
linq messages send <chat-id> --message "follow-up" --json
```

`linq contacts add` also prints a `shareLink` of the form
`https://linqapp.com/s/text/+12052611117?from=+1XXXXXXXXXX&msg=...` — on mobile
it opens Messages with a pre-filled draft, on desktop it renders a QR code. Use
it to get someone past the inbound-first gate without them typing the number.

### iMessage-native affordances

```bash
linq messages send <chat-id> --message "🎉" --effect confetti --json
linq messages react <message-id> --type love --json      # add --operation remove to undo
linq chats typing <chat-id>                              # start indicator
linq chats typing <chat-id> --stop                       # stop it
```

Effects: `confetti`, `fireworks`, `lasers`, `sparkles`, `celebration`, `hearts`,
`love`, `balloons`, `happy_birthday`, `echo`, `spotlight`, `slam`, `loud`,
`gentle`, `invisible`.

Reactions: `love`, `like`, `dislike`, `laugh`, `emphasize`, `question`,
`custom` (with `--emoji 🔥`).

Typing indicators only surface in conversations with recent activity — if one
doesn't appear, send a fresh message to wake the chat and retry.

### Attachments — a two-step presigned upload, not a file post

`linq attachments upload` does **not** take a path. It takes the file's
metadata, returns a presigned S3 `PUT` URL, and you upload the bytes yourself.
The `download_url` it hands back is what `--attachment-url` wants:

```bash
SZ=$(stat -f%z card.png)
RESP=$(linq attachments upload --profile closer \
         --filename card.png --content-type image/png --size "$SZ" --json)
UP=$(echo "$RESP" | jq -r .upload_url)      # presigned, expires in 15 min
DL=$(echo "$RESP" | jq -r .download_url)    # cdn.linqapp.com, permanent

curl -X PUT "$UP" -H "Content-Type: image/png" -H "Content-Length: $SZ" \
     --data-binary @card.png                # must echo both required_headers

linq messages send <chat-id> --profile closer --message "your card" \
     --attachment-url "$DL" --json
```

`required_headers` in the response is not advisory — S3 signs over
`content-length` and `content-type`, so omitting either fails the signature.
The sent message comes back with two parts: a `text` part and a `media` part
carrying `filename`, `mime_type`, `size_bytes`, and the CDN `url`.

### Phase 0 probe results — verified 2026-07-24, closer profile

Every affordance this project leans on, exercised against the live API. All
green; no CLI-subprocess fallback needed for any of them.

| Probe | Result |
|---|---|
| `webhooks events` | ✅ 21 event types. `reaction.added` / `reaction.removed` and `chat.typing_indicator.started` / `.stopped` are both subscribable |
| `messages send --effect confetti` | ✅ echoes `effect: {name: "confetti", type: "screen"}` |
| `messages react <id> --type like` | ✅ `{"status": "accepted"}`. Works on our own outbound messages too |
| `chats typing <id>` | ✅ `{"success": true, "action": "typing.start"}` |
| `attachments upload` → PUT → send | ✅ full round-trip, `PUT` returns 200, message carries the media part |
| listener → backend forward | ✅ `message.received` → `POST /webhooks/linq` → `200 OK` in 6ms |
| inbound text → agent reply | ✅ 1 second, phone to phone |

**Two Linq Shared lines cannot bootstrap a conversation with each other.**
Cross-adding contacts is not enough — the inbound-first gate is unconditional,
and both directions report `Can't message this contact yet` until a real handset
texts in. This matters for the Closer ↔ Marcus demo: the chat between
`+12052611117` and `+12054909563` has to be opened once from a physical phone
(or via the `contacts add` share link), after which both agents can text freely.
Do that during setup, not on stage.

### Receiving — webhooks

```bash
linq webhooks listen                                            # live JSON stream, no tunnel needed
linq webhooks listen --forward-to http://localhost:3000/webhook # stream + POST to a local server
linq webhooks create --url https://our-server.com/webhook --all-events
linq webhooks events                                            # list event types
```

`listen` creates a temporary subscription that auto-cleans on Ctrl+C. Production
subscriptions sign every delivery with an HMAC in the `x-webhook-signature`
header plus a timestamp — verify both server-side.

Key event: `message.received`, fired within ~1s of an inbound text.

## REST API

Same surface the CLI sits on, documented at https://apidocs.linqapp.com.

```bash
curl https://api.linqapp.com/api/partner/v3/phone_numbers \
  -H "Authorization: Bearer $LINQ_API_KEY"
```

SDKs: `npm install @linqapp/sdk` (TypeScript); Python and Go via the docs site.

## Design constraint — build conversationally

iMessage is peer-to-peer. Two-way exchanges where an agent listens and replies
are the supported pattern. One-way blasts, cold outreach, and notification-only
flows with no expected reply risk getting the Linq Number flagged or shut down
by Apple. Design anything we ship as a conversation.

## Command reference

| Command | Purpose |
|---|---|
| `linq signup [--email --code --name]` | Create account + provision a Linq Number |
| `linq login --token <token>` | Authenticate an existing account |
| `linq logout` | Clear local credentials (does not revoke the key) |
| `linq whoami` | Identity, Linq Number, account type |
| `linq doctor` | Health-check config + connectivity (non-zero exit on failure) |
| `linq tokens list / show / create / regenerate / rename / delete` | Manage API tokens |
| `linq phonenumbers [set]` | List / choose default Linq Number |
| `linq contacts add / list / remove` | Manage contacts |
| `linq chats create / list / get / typing` | Chats |
| `linq messages send / list / get / react / thread / delete` | Messages |
| `linq webhooks listen / create / list / get / update / delete / events` | Webhooks |
| `linq attachments upload --filename --content-type --size` | Presigned `PUT` URL + permanent `download_url`; you upload the bytes |
| `linq profile list / use / create / show / get / set` | Multi-account profiles |

Phone numbers are E.164 (`+14155551234`). Chat, message, webhook, and token IDs
are UUIDs. `linq <command> --help` for full flags.

## Links

- Dashboard: https://dashboard.linqapp.com
- API docs: https://apidocs.linqapp.com
- CLI source: https://github.com/linq-team/linq-cli
- Example apps: https://linqapp.com/s/example-apps
- Support: contact@linqapp.com
