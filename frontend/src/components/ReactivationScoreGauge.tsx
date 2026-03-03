'use client';

interface ScoreBreakdown {
  historical: number;
  responsiveness: number;
  market: number;
  time_decay: number;
  recoverability: number;
  demographics: number;
}

interface ReactivationScoreGaugeProps {
  score: number;
  breakdown?: ScoreBreakdown;
  size?: 'sm' | 'md' | 'lg';
  showBreakdown?: boolean;
}

function getScoreColor(score: number): string {
  if (score >= 70) return '#10b981'; // emerald
  if (score >= 40) return '#f59e0b'; // amber
  if (score >= 20) return '#f97316'; // orange
  return '#ef4444'; // red
}

function getScoreLabel(score: number): string {
  if (score >= 70) return 'High Potential';
  if (score >= 40) return 'Moderate';
  if (score >= 20) return 'Low';
  return 'Very Low';
}

const BREAKDOWN_LABELS: Record<string, { label: string; max: number }> = {
  historical: { label: 'Historical', max: 25 },
  responsiveness: { label: 'Responsiveness', max: 25 },
  market: { label: 'Market', max: 15 },
  time_decay: { label: 'Time Decay', max: 15 },
  recoverability: { label: 'Recoverability', max: 10 },
  demographics: { label: 'Demographics', max: 10 },
};

export default function ReactivationScoreGauge({
  score,
  breakdown,
  size = 'md',
  showBreakdown = true,
}: ReactivationScoreGaugeProps) {
  const color = getScoreColor(score);
  const label = getScoreLabel(score);
  const circumference = 2 * Math.PI * 45;
  const dashOffset = circumference - (score / 100) * circumference;

  const sizeMap = { sm: 80, md: 120, lg: 160 };
  const svgSize = sizeMap[size];
  const fontSize = size === 'sm' ? 'text-lg' : size === 'md' ? 'text-2xl' : 'text-3xl';
  const labelSize = size === 'sm' ? 'text-[9px]' : 'text-[11px]';

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Circular gauge */}
      <div className="relative" style={{ width: svgSize, height: svgSize }}>
        <svg
          width={svgSize}
          height={svgSize}
          viewBox="0 0 100 100"
          className="transform -rotate-90"
        >
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="8"
          />
          {/* Score arc */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`${fontSize} font-bold text-white`}>
            {Math.round(score)}
          </span>
          <span className={`${labelSize} font-medium`} style={{ color }}>
            {label}
          </span>
        </div>
      </div>

      {/* Breakdown bars */}
      {showBreakdown && breakdown && (
        <div className="w-full space-y-2">
          {Object.entries(BREAKDOWN_LABELS).map(([key, config]) => {
            const value = (breakdown as any)[key] ?? 0;
            const pct = (value / config.max) * 100;
            return (
              <div key={key} className="flex items-center gap-2">
                <span className="text-[10px] text-gray-400 w-24 text-right">
                  {config.label}
                </span>
                <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${pct}%`,
                      backgroundColor: getScoreColor((value / config.max) * 100),
                    }}
                  />
                </div>
                <span className="text-[10px] text-gray-500 w-10">
                  {value.toFixed(1)}/{config.max}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
