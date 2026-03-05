/**
 * ScreenPreview — 160×90 thumbnail of captured screen.
 * Updated automatically when `frame` prop changes (1 FPS from hook).
 */

export default function ScreenPreview({ frame }) {
  if (!frame) {
    return (
      <div className="w-[160px] h-[90px] rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] 
                      flex items-center justify-center">
        <span className="text-[#444] text-[10px]">No screen selected</span>
      </div>
    );
  }

  const src = frame.startsWith("data:") ? frame : `data:image/jpeg;base64,${frame}`;

  return (
    <div className="relative w-[160px] h-[90px] rounded-lg overflow-hidden border border-[#2a2a2a]">
      <img
        src={src}
        alt="Screen preview"
        className="w-full h-full object-cover"
        draggable={false}
      />
      {/* Live indicator dot */}
      <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#ea4335] 
                       shadow-[0_0_4px_#ea4335]" />
    </div>
  );
}
