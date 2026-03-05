/**
 * VoiceIndicator — CSS-only animated waveform / microphone icon.
 * IDLE: static mic icon
 * LISTENING: animated bars (recording)
 * SPEAKING: animated bars (playback)
 *
 * No external animation library — pure Tailwind + CSS keyframes.
 */

const BAR_DELAYS = ["0ms", "80ms", "160ms", "240ms", "320ms"];
const BAR_HEIGHTS_LISTEN = ["h-3", "h-6", "h-8", "h-6", "h-3"];
const BAR_HEIGHTS_SPEAK  = ["h-4", "h-7", "h-9", "h-7", "h-4"];

export default function VoiceIndicator({ state }) {
  if (state === "IDLE") {
    return (
      <div className="flex items-center justify-center w-12 h-12 rounded-full 
                      bg-[#1a1a1a] border border-[#2a2a2a]">
        <svg
          className="w-5 h-5 text-[#555]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 1a3 3 0 00-3 3v7a3 3 0 006 0V4a3 3 0 00-3-3z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M19 10a7 7 0 01-14 0M12 21v-4M8 21h8"
          />
        </svg>
      </div>
    );
  }

  const isListening = state === "LISTENING";
  const color = isListening ? "#4285f4" : "#34a853";
  const barHeights = isListening ? BAR_HEIGHTS_LISTEN : BAR_HEIGHTS_SPEAK;

  return (
    <div className="flex items-end justify-center gap-[3px] h-10">
      {BAR_DELAYS.map((delay, i) => (
        <div
          key={i}
          className={`w-[3px] rounded-full ${barHeights[i]}`}
          style={{
            backgroundColor: color,
            animation: `flowlens-wave 0.7s ease-in-out infinite alternate`,
            animationDelay: delay,
          }}
        />
      ))}

      <style>{`
        @keyframes flowlens-wave {
          0%   { transform: scaleY(0.4); opacity: 0.6; }
          100% { transform: scaleY(1.0); opacity: 1.0; }
        }
      `}</style>
    </div>
  );
}
