import { useMemo, useRef, useState, useEffect } from 'react';
import { Tooltip } from 'antd';

// 颜色等级定义
// level 0: 租户创建之前的日期（无数据）- 浅灰
// level 6: 租户已使用但无故障 - 浅绿
// level 1-5: 故障数量递增 - 红色系（由浅入深）
const LEVEL_COLORS: Record<number, string> = {
  0: '#ebedf0', // 无数据（租户创建之前）- 浅灰
  1: '#f8c0c9', // 1-2 台 - 极浅红
  2: '#f999a2', // 3-5 台 - 浅红
  3: '#ef7070', // 6-10 台 - 中红
  4: '#e53935', // >10 台 - 深红s
  5: '#b71c1c', // 20+ 台 - 更深红
  6: '#8aefa1', // 正常运行（租户已使用但无故障）- 极浅绿
};

const LEVEL_LABELS: Record<number, string> = {
  0: '无数据',
  1: '1-2 台',
  2: '3-5 台',
  3: '6-10 台',
  4: '10+ 台',
  5: '20+ 台',
  6: '正常运行',
};

// 月份故障颜色（根据故障数量深浅不同）
const MONTH_FAULT_COLORS = [
  '#316d33', // 0 台 - 绿色（无故障）
  '#ff9800', // 1-2 台 - 橙色
  '#f44336', // 3-5 台 - 红色
  '#d32f2f', // 6-10 台 - 深红
  '#b71c1c', // >10 台 - 深暗红
];

// 星期标签（LeetCode 风格：周日~周六，只显示部分）
// 索引 0=周日, 1=周一, 2=周二, 3=周三, 4=周四, 5=周五, 6=周六
const WEEKDAY_LABELS = ['', 'Mon', '', 'Wed', '', 'Fri', ''];

// 月份缩写
const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

interface CalendarDay {
  date: string; // "2026-05-25"
  count: number;
  level: number; // 0-4
}

interface CalendarMonth {
  month: number; // 1-12
  days: CalendarDay[];
}

interface CalendarData {
  year: number;
  months: CalendarMonth[];
  start_at?: string; // Tenant's start date, e.g. "2026-01-15"
}

interface CalendarHeatmapProps {
  data?: CalendarData;
  loading?: boolean;
}

/**
 * 年历热力图组件
 * LeetCode / GitHub 风格：
 * - 横向排列：X 轴 = 周（列），从左到右
 * - Y 轴 = 星期：7 行（周一~周日）
 * - 月份标签居中在列范围上方，显示 May(3) 格式
 * - 星期标签在左侧
 * - 月份之间有间隔
 * - 当前月前推 12 个月
 * - 自适应宽度，无滚动条
 */
const CalendarHeatmap = ({ data, loading }: CalendarHeatmapProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [cellSize, setCellSize] = useState(13);
  const cellGap = 3;
  const labelWidth = 36;

  // 计算统计数据
  const stats = useMemo(() => {
    if (!data || !data.months) return { faultDays: 0, totalDays: 0, maxCount: 0 };

    let faultDays = 0;
    let totalDays = 0;
    let maxCount = 0;

    for (const month of data.months) {
      for (const day of month.days) {
        totalDays++;
        if (day.count > 0) faultDays++;
        if (day.count > maxCount) maxCount = day.count;
      }
    }

    return { faultDays, totalDays, maxCount };
  }, [data]);

  // 生成过去 12 个月的所有日期（当前月前推 12 个月，包含当前月）
  const allMonths = useMemo(() => {
    const today = new Date();
    const result: { year: number; month: number; days: CalendarDay[] }[] = [];

    for (let i = 11; i >= 0; i--) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      const y = d.getFullYear();
      const m = d.getMonth(); // 0-based
      const monthIndex = m + 1; // 1-based

      const daysInMonth = new Date(y, m + 1, 0).getDate();

      const days: CalendarDay[] = [];
      for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${y}-${String(monthIndex).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        days.push({
          date: dateStr,
          count: 0,
          level: 0,
        });
      }

      result.push({ year: y, month: monthIndex, days });
    }

    return result;
  }, []);

  // 将后端数据合并到生成的月份中，并根据 start_at 调整 level
  const mergedMonths = useMemo(() => {
    if (!data || !data.months) return allMonths;

    const startAt = data.start_at;
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    const lookup = new Map<string, { count: number; level: number }>();
    for (const month of data.months) {
      for (const day of month.days) {
        lookup.set(day.date, { count: day.count, level: day.level });
      }
    }

    return allMonths.map(month => ({
      ...month,
      days: month.days.map(day => {
        const found = lookup.get(day.date);
        let count = 0;
        let level = 0;
        if (found) {
          count = found.count;
          level = found.level;
        }

        // 根据 start_at 调整颜色级别
        if (startAt) {
          if (day.date < startAt || day.date > todayStr) {
            // 租户开始使用之前的日期 或 未来日期：使用灰色（无数据）
            level = 0;
          } else if (count === 0) {
            // 租户已使用但无故障：使用浅绿色
            level = 6;
          }
          // 有故障的情况：保持后端返回的 level（1-5）
        }

        return { ...day, count, level };
      }),
    }));
  }, [data, allMonths]);

  // 构建网格数据，同时记录每个月的列范围
  const gridData = useMemo(() => {
    if (mergedMonths.length === 0) {
      return { columns: [] as (CalendarDay | null)[][], monthColRanges: [] as { start: number; end: number; totalFaults: number }[] };
    }

    const allColumns: (CalendarDay | null)[][] = [];
    const monthColRanges: { start: number; end: number; totalFaults: number }[] = [];

    for (let mi = 0; mi < mergedMonths.length; mi++) {
      const month = mergedMonths[mi];
      const firstDay = new Date(month.year, month.month - 1, 1);
      // getDay(): 0=周日, 1=周一, ..., 6=周六
      // LeetCode 风格：周日=第0行，周一=第1行...
      const startDayOfWeek = firstDay.getDay();

      const monthColumns: (CalendarDay | null)[][] = [];
      let currentCol: (CalendarDay | null)[] = [];

      for (let i = 0; i < startDayOfWeek; i++) {
        currentCol.push(null);
      }

      for (const day of month.days) {
        currentCol.push(day);
        if (currentCol.length === 7) {
          monthColumns.push(currentCol);
          currentCol = [];
        }
      }

      if (currentCol.length > 0) {
        while (currentCol.length < 7) {
          currentCol.push(null);
        }
        monthColumns.push(currentCol);
      }

      const startCol = allColumns.length;
      for (const col of monthColumns) {
        allColumns.push(col);
      }
      const endCol = allColumns.length - 1;

      // 月份标签表示“发生过异常的天数”，而不是每日异常设备数之和。
      const totalFaults = month.days.filter((day) => day.count > 0).length;
      monthColRanges.push({ start: startCol, end: endCol, totalFaults });

      if (mi < mergedMonths.length - 1) {
        const emptyCol: (CalendarDay | null)[] = [];
        for (let i = 0; i < 7; i++) {
          emptyCol.push(null);
        }
        allColumns.push(emptyCol);
      }
    }

    return { columns: allColumns, monthColRanges };
  }, [mergedMonths]);

  // 计算月份标签（居中显示，带故障数量）
  const monthLabels = useMemo(() => {
    return gridData.monthColRanges.map((range, i) => {
      const month = mergedMonths[i]?.month;
      const name = month ? MONTH_ABBR[month - 1] : '';
      const centerCol = (range.start + range.end) / 2;
      return {
        centerCol,
        name,
        totalFaults: range.totalFaults,
      };
    });
  }, [gridData.monthColRanges, mergedMonths]);

  // 自适应格子大小：根据容器宽度计算
  useEffect(() => {
    const updateSize = () => {
      if (!containerRef.current) return;
      const numCols = gridData.columns.length;
      if (numCols === 0) return;

      const availableWidth = containerRef.current.clientWidth - labelWidth - 8;
      const totalGap = (numCols - 1) * cellGap;
      const calculatedSize = Math.max(8, Math.min(16, Math.floor((availableWidth - totalGap) / numCols)));
      setCellSize(calculatedSize);
    };

    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, [gridData.columns.length]);

  if (loading) {
    return (
      <div style={{ padding: '24px 0', textAlign: 'center', color: '#999' }}>
        加载中...
      </div>
    );
  }

  if (!data || gridData.columns.length === 0) {
    return (
      <div style={{ padding: '24px 0', textAlign: 'center', color: '#999' }}>
        暂无数据
      </div>
    );
  }

  const numCols = gridData.columns.length;

  // 获取月份故障颜色
  const getMonthColor = (totalFaults: number): string => {
    if (totalFaults <= 0) return MONTH_FAULT_COLORS[0];
    if (totalFaults <= 2) return MONTH_FAULT_COLORS[1];
    if (totalFaults <= 5) return MONTH_FAULT_COLORS[2];
    if (totalFaults <= 10) return MONTH_FAULT_COLORS[3];
    return MONTH_FAULT_COLORS[4];
  };

  return (
    <div ref={containerRef} style={{ width: '100%', padding: '8px 0', marginTop: 10 }}>
      {/* 统计摘要 + 图例 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 13, color: '#333', fontWeight: 500 }}>
           过去 <strong style={{ color: '#1890ff' }}>12</strong> 个月，有 <strong style={{ color: '#ff4d4f' }}>{stats.faultDays}</strong> 个监控日检出异常，共 <strong style={{ color: '#1890ff' }}>{stats.totalDays}</strong> 个监控日
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <span style={{ fontSize: 11, color: '#999', marginRight: 4 }}>Less</span>
          {[1, 2, 3, 4, 5].map((level) => (
            <div
              key={level}
              style={{
                width: cellSize - 2,
                height: cellSize - 2,
                borderRadius: 2,
                backgroundColor: LEVEL_COLORS[level],
              }}
              title={LEVEL_LABELS[level]}
            />
          ))}
          <span style={{ fontSize: 11, color: '#999', marginLeft: 4 }}>More</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, width: '100%' }}>
        {/* 左侧星期标签 */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: cellGap,
            paddingTop: 26,
            minWidth: labelWidth,
            flexShrink: 1,
          }}
        >
          {WEEKDAY_LABELS.map((label, i) => (
            <div
              key={i}
              style={{
                height: cellSize,
                lineHeight: `${cellSize}px`,
                fontSize: Math.max(8, Math.min(10, cellSize - 2)),
                color: '#999',
                textAlign: 'right',
                paddingRight: 2,
              }}
            >
              {label}
            </div>
          ))}
        </div>

        {/* 右侧日历网格 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* 月份标签行（顶部，居中显示） */}
          <div
            style={{
              position: 'relative',
              height: 22,
              marginBottom: 4,
            }}
          >
            {monthLabels.map((label, i) => {
              // 居中：计算该月列范围的中心位置
              const left = label.centerCol * (cellSize + cellGap);
              const monthFaultColor = getMonthColor(label.totalFaults);

              return (
                <div
                  key={i}
                  style={{
                    position: 'absolute',
                    left,
                    transform: 'translateX(-50%)',
                    fontSize: Math.max(9, Math.min(11, cellSize)),
                    color: label.totalFaults > 0 ? monthFaultColor : '#666',
                    // color: '#666',
                    whiteSpace: 'nowrap',
                    fontWeight: label.totalFaults > 0 ? 600 : 500,
                  }}
                >
                  {label.totalFaults > 0
                    ? `${label.name}(${label.totalFaults})`
                    : label.name}
                </div>
              );
            })}
          </div>

          {/* 网格：N 列 × 7 行 */}
          <div style={{ display: 'flex', gap: cellGap }}>
            {Array.from({ length: numCols }, (_, colIndex) => (
              <div
                key={colIndex}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: cellGap,
                }}
              >
                {Array.from({ length: 7 }, (_, rowIndex) => {
                  const day = gridData.columns[colIndex]?.[rowIndex];

                  if (!day) {
                    return (
                      <div
                        key={rowIndex}
                        style={{
                          width: cellSize,
                          height: cellSize,
                          borderRadius: 3,
                        }}
                      />
                    );
                  }

                  const color = LEVEL_COLORS[day.level] || LEVEL_COLORS[0];
                  const dateObj = new Date(day.date);
                  const dateStr = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}-${String(dateObj.getDate()).padStart(2, '0')}`;

                  // start_at 之前或未来日期：不显示提示信息
                  const startAt = data?.start_at;
                  const today = new Date();
                  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
                  const isNoData = startAt && (day.date < startAt || day.date > todayStr);

                  const cell = (
                    <div
                      style={{
                        width: cellSize,
                        height: cellSize,
                        borderRadius: 3,
                        backgroundColor: color,
                        cursor: isNoData ? 'default' : 'pointer',
                        transition: 'all 0.1s ease',
                      }}
                      onMouseEnter={(e) => {
                        if (isNoData) return;
                        e.currentTarget.style.transform = 'scale(1.2)';
                        e.currentTarget.style.boxShadow = '0 0 4px rgba(0,0,0,0.2)';
                      }}
                      onMouseLeave={(e) => {
                        if (isNoData) return;
                        e.currentTarget.style.transform = 'scale(1)';
                        e.currentTarget.style.boxShadow = 'none';
                      }}
                    />
                  );

                  if (isNoData) {
                    return <div key={rowIndex}>{cell}</div>;
                  }

                  return (
                    <Tooltip
                      key={rowIndex}
                      title={
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontWeight: 500, marginBottom: 2 }}>
                            {dateStr}
                          </div>
                          <div>
                            {day.count > 0
                              ? `${day.count} 台设备故障`
                              : '无故障'}
                          </div>
                        </div>
                      }
                      overlayStyle={{ fontSize: 12 }}
                    >
                      {cell}
                    </Tooltip>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

    </div>
  );
};

export default CalendarHeatmap;
