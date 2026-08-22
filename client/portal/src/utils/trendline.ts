import dayjs from 'dayjs';

/**
 * Calculates a linear regression trend line for ECharts markLine.
 * @param timestamps Array of ISO string timestamps
 * @param values Array of numerical values (same length as timestamps, can contain nulls)
 * @returns An array representing the start and end coordinates for an ECharts markLine, or undefined if insufficient data.
 */
export function calculateTrendLine(
  timestamps: string[],
  values: (number | null | undefined)[],
): {
  markLineData: Array<[{ coord: [string, number] }, { coord: [string, number] }]>;
  slopePerHour: number;
  amplitude: number;
} | undefined {
  const validPoints: Array<[number, number]> = [];
  
  for (let i = 0; i < timestamps.length; i++) {
    const val = values[i];
    if (val !== null && val !== undefined) {
      validPoints.push([dayjs(timestamps[i]).valueOf(), val]);
    }
  }

  if (validPoints.length < 2) return undefined;

  const minX = validPoints[0][0];
  const maxX = validPoints[validPoints.length - 1][0];

  const n = validPoints.length;
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumXX = 0;

  for (let i = 0; i < n; i++) {
    const x = validPoints[i][0] - minX;
    const y = validPoints[i][1];
    sumX += x;
    sumY += y;
    sumXY += x * y;
    sumXX += x * x;
  }

  const denominator = n * sumXX - sumX * sumX;
  if (denominator === 0) return undefined;

  const slope = (n * sumXY - sumX * sumY) / denominator;
  const intercept = (sumY - slope * sumX) / n;

  const startY = slope * 0 + intercept;
  const endY = slope * (maxX - minX) + intercept;

  const startTimestamp = timestamps[0];
  const endTimestamp = timestamps[timestamps.length - 1];

  const slopePerHour = slope * 3600000;
  
  const allY = validPoints.map(p => p[1]);
  const amplitude = Math.max(...allY) - Math.min(...allY);

  return {
    markLineData: [
      [
        { coord: [startTimestamp, startY] },
        { coord: [endTimestamp, endY] },
      ],
    ],
    slopePerHour,
    amplitude,
  };
}
