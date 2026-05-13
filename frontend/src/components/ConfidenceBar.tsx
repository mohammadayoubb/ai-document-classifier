interface ConfidenceBarProps {
  confidence: number; // 0.0 – 1.0
}

function barColor(confidence: number): string {
  if (confidence >= 0.7) return "bg-green-500";
  if (confidence >= 0.5) return "bg-yellow-400";
  return "bg-red-500";
}

function textColor(confidence: number): string {
  if (confidence >= 0.7) return "text-green-700";
  if (confidence >= 0.5) return "text-yellow-700";
  return "text-red-700";
}

export default function ConfidenceBar({ confidence }: ConfidenceBarProps) {
  const pct = Math.round(confidence * 100);

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all ${barColor(confidence)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-sm font-semibold w-12 text-right ${textColor(confidence)}`}>
        {pct}%
      </span>
    </div>
  );
}
