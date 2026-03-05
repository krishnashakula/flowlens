/**
 * StatusBar — Connection status + latency display
 * Shows: connection dot, latency from last turn, current state label
 */

const STATE_LABELS = {
  IDLE: "Ready",
  LISTENING: "Listening",
  PROCESSING: "Processing",
  SPEAKING: "Speaking",
};

const STATE_COLORS = {
  IDLE: "text-[#555]",
  LISTENING: "text-[#4285f4]",
  PROCESSING: "text-[#fbbc04]",
  SPEAKING: "text-[#34a853]",
};

export default function StatusBar({ isConnected, latency, state }) {
  return (
    <div className="flex items-center gap-2">
      {latency && (
        <span className="text-[#555] text-[10px] font-mono tabular-nums">
          {latency}s
        </span>
      )}
      <span className={`text-[10px] font-medium ${STATE_COLORS[state] || STATE_COLORS.IDLE}`}>
        {STATE_LABELS[state] || "Ready"}
      </span>
      <span
        className={`w-2 h-2 rounded-full ${
          isConnected ? "bg-[#34a853]" : "bg-[#ea4335]"
        }`}
        title={isConnected ? "Connected" : "Disconnected"}
      />
    </div>
  );
}
