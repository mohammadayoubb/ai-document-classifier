import type { BatchStatus } from "../types";

const BADGE: Record<BatchStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800 border border-yellow-200",
  running: "bg-blue-100 text-blue-800 border border-blue-200",
  completed: "bg-green-100 text-green-800 border border-green-200",
  failed: "bg-red-100 text-red-800 border border-red-200",
};

interface StatusBadgeProps {
  status: BatchStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full capitalize ${BADGE[status]}`}
    >
      {status}
    </span>
  );
}
