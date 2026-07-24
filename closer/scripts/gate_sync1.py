"""Sync 1 gate — update_1.md §6 acceptance steps 1-7, 12 and 13.

    python -m scripts.gate_sync1 /tmp/gatestore run       # steps 1-7, 12
    python -m scripts.gate_sync1 /tmp/gatestore restart   # step 13, new process


Drives the real inbound path (`_process_inbound`), on a real FileStore, with a
phone number as the only identity. Step 13 runs in a second process against the
same store directory, which is the only honest way to prove a restart.
"""
import os
import pathlib
import sys

STORE_PATH = sys.argv[1]
PHASE = sys.argv[2] if len(sys.argv) > 2 else "run"      # "run" | "restart"

os.environ["CLOSER_STORE_PATH"] = STORE_PATH
os.environ["RESEARCH_MODE"] = "mock"
os.environ["RUNWARE_API_KEY"] = ""
os.environ["LINQ_API_KEY"] = ""
os.environ["CLOSER_DISABLE_DOTENV"] = "1"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import linq, main  # noqa: E402

PHONE = "+12055550143"
OTHER = "+12055550199"
CAMRY = "https://www.facebook.com/marketplace/item/1102938471"
CIVIC = "https://www.cars.com/vehicledetail/9f2c1a/"

FAILED = []


def text(body, sender=PHONE):
    inb = linq.InboundMessage(chat_id="chat-1", sender=sender, text=body)
    return main._process_inbound(inb)


def wait_for_research(seconds=60.0):
    """Research runs on a background thread, exactly as it does on the live
    path. A human waits ~30s watching a typing indicator; the gate polls."""
    import time as _t
    user = main._resolve_user(PHONE)
    deadline = _t.time() + seconds
    while _t.time() < deadline:
        pending = [d for d in main.STORE.list_deals(user)
                   if d.state.value == "AWAITING_RESEARCH"]
        if not pending:
            return True
        _t.sleep(0.5)
    return False


def step(n, label, reply, *checks):
    ok = all(c[1] for c in checks)
    bad = [c[0] for c in checks if not c[1]]
    print(f"\n{'PASS' if ok else 'FAIL'}  step {n} — {label}")
    print("      " + reply.replace("\n", "\n      ")[:600])
    if not ok:
        FAILED.append(f"step {n}: {', '.join(bad)}")


if PHASE == "run":
    r = text("hey")
    step(1, "new phone gets onboarding", r,
         ("names itself", "I'm Closer" in r),
         ("asks for a link", "link" in r.lower()))

    r = text(f"just found this {CAMRY}")
    step(2, "listing link starts research", r,
         ("acknowledges", "🔎" in r),
         ("research finished", wait_for_research()))

    r = text("He says 6,400 is what it's worth — plenty of life left in it.")
    step(3, "relay gets a coach reply", r, ("non-empty", len(r) > 20))
    r = text("He says three other people are coming to see it Saturday, so he's not moving.")
    step(3.1, "bluff relay", r, ("non-empty", len(r) > 20))

    r = text("card")
    step(4, "card shows the deal", r,
         ("titled", "🚗" in r or "🔎" in r),
         ("has a floor read", "floor" in r.lower()))

    r = text(f"and this one {CIVIC}")
    step(5, "second link parks the first", r,
         ("parked", "parked" in r.lower()),
         ("names the parked deal", "parked, not lost" in r),
         ("research finished", wait_for_research()))

    r = text("deals")
    step(6, "numbered list, focus marked", r,
         ("numbered", "1." in r and "2." in r),
         ("focus marker on the new deal", "▶ 2." in r))

    r = text("1")
    step(7, "bare integer switches back", r,
         ("switched", "↩️" in r),
         ("card returned to the first deal", "turn 2 of a live deal" in r),
         ("no disambiguation prompt", "Which one?" not in r))

    r = text("deals", sender=OTHER)
    step(12, "a second phone sees none of it", r,
         ("isolated", "No deals yet" in r))

if PHASE == "restart":
    r = text("deals")
    step(13, "restart loses nothing", r,
         ("both deals survive", "1." in r and "2." in r))
    r = text("stats")
    step("13b", "stats card survives too", r, ("rendered", len(r) > 20))

print("\n" + ("ALL GREEN" if not FAILED else "FAILURES: " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
