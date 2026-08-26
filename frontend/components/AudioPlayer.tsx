"use client";

import { useRef, useState } from "react";

export default function AudioPlayer({ url }: { url: string }) {
  const [open, setOpen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  function toggle() {
    if (!open) {
      setOpen(true);
      return;
    }
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) audio.play();
    else audio.pause();
  }

  return (
    <div>
      <button className="secondary" style={{ padding: "2px 8px", fontSize: 11 }} onClick={toggle}>
        {playing ? "⏸ Pause" : "▶ Play"}
      </button>
      {open && (
        <div style={{ marginTop: 6 }}>
          <audio
            ref={audioRef}
            controls
            autoPlay
            src={url}
            style={{ width: "100%", maxWidth: 320, height: 32 }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        </div>
      )}
    </div>
  );
}
