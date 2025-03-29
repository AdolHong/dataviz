import { format, parse, addDays } from 'date-fns';

// 日期验证函数
export const isValidDate = (dateString: string, format: string): boolean => {
  // 首先检查格式
  const formatRegex = {
    'YYYY-MM-DD': /^\d{4}-\d{2}-\d{2}$/,
    YYYYMMDD: /^\d{4}\d{2}\d{2}$/,
  };

  if (!formatRegex[format as keyof typeof formatRegex]?.test(dateString)) {
    return false;
  }

  // 解析日期
  let year: number, month: number, day: number;

  if (format === 'YYYY-MM-DD') {
    [year, month, day] = dateString.split('-').map(Number);
  } else if (format === 'YYYYMMDD') {
    year = Number(dateString.slice(0, 4));
    month = Number(dateString.slice(4, 6));
    day = Number(dateString.slice(6, 8));
  } else {
    return false;
  }

  // 检查月份和日期的有效性
  if (month < 1 || month > 12) return false;

  // 每月的天数
  const daysInMonth = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

  // 闰年处理
  if (year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)) {
    daysInMonth[1] = 29;
  }

  // 检查日期是否在当月有效
  return day >= 1 && day <= daysInMonth[month - 1];
};

export const parseDynamicDate = (dateString: string): string | null => {
  // 移除首尾空格
  dateString = dateString.trim();

  // 动态日期匹配正则
  const dynamicDateRegex = /^(\$\{)?(yyyy-MM-dd|yyyyMMdd)([+-]\d+[dwmy])?\}?$/;
  const match = dateString.match(dynamicDateRegex);

  if (!match) return null;

  const [, , baseFormat, offsetStr] = match;
  let baseDate = new Date();

  // 解析基准日期
  try {
    baseDate = parse(
      format(baseDate, baseFormat === 'yyyy-MM-dd' ? 'yyyy-MM-dd' : 'yyyyMMdd'),
      baseFormat,
      new Date()
    );
  } catch {
    return null;
  }

  // 处理偏移量
  if (offsetStr) {
    const offsetMatch = offsetStr.match(/([+-])(\d+)([dwmy])/);
    if (offsetMatch) {
      const [, sign, amount, unit] = offsetMatch;
      const offsetAmount = sign === '+' ? parseInt(amount) : -parseInt(amount);

      switch (unit) {
        case 'd':
          baseDate = addDays(baseDate, offsetAmount);
          break;
        case 'w':
          baseDate = addDays(baseDate, offsetAmount * 7);
          break;
        case 'm':
          baseDate = new Date(
            baseDate.getFullYear(),
            baseDate.getMonth() + offsetAmount,
            baseDate.getDate()
          );
          break;
        case 'y':
          baseDate = new Date(
            baseDate.getFullYear() + offsetAmount,
            baseDate.getMonth(),
            baseDate.getDate()
          );
          break;
      }
    }
  }

  return format(
    baseDate,
    baseFormat === 'yyyy-MM-dd' ? 'yyyy-MM-dd' : 'yyyyMMdd'
  );
};

export const isValidDynamicDate = (dateString: string): boolean => {
  return parseDynamicDate(dateString) !== null;
};

export const formatDynamicDate = (
  dateString: string,
  outputFormat: string = 'yyyy-MM-dd'
): string => {
  const parsedDate = parseDynamicDate(dateString);
  return parsedDate ? format(parsedDate, outputFormat) : '';
};
