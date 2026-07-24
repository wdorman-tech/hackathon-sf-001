import type { TrackId } from "../data";
import { TRACKS_BY_ID } from "../data";
import { slotVar } from "../lib/colors";

export function TrackChip({ trackId }: { trackId: TrackId }) {
  const track = TRACKS_BY_ID[trackId];
  return (
    <span className="track-chip" style={{ ["--slot" as string]: slotVar(track.colorSlot) }}>
      <span className="swatch" aria-hidden="true" />
      {track.code}
    </span>
  );
}
