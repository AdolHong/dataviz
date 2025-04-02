import dayjs from 'dayjs';

// 动态日期解析函数
export const parseDynamicDate = (value: string) => {
  if (!value || typeof value !== 'string') {
    return value;
  }

  // 匹配三种格式：
  // 1. ${yyyyMMdd} - 当前日期，无偏移
  // 2. ${yyyy-MM-dd+Nd} - 当前日期加N天
  // 3. ${yyyy-MM-dd-Nd} - 当前日期减N天
  const dateMatch = value.match(
    /\$\{(yyyy-MM-dd|yyyyMMdd)(?:([+-])(\d+)([dMy]))?\}/
  );

  if (dateMatch) {
    const format = dateMatch[1];
    const operation = dateMatch[2] || ''; // '+', '-' 或空字符串
    const amount = dateMatch[3] ? parseInt(dateMatch[3]) : 0;
    const unit = dateMatch[4] || 'd'; // 如果没有指定单位，默认为天

    let date = dayjs();

    // 根据操作符处理日期
    if (operation === '+') {
      // 加上相应的时间
      if (unit === 'd') {
        date = date.add(amount, 'day');
      } else if (unit === 'M') {
        date = date.add(amount, 'month');
      } else if (unit === 'y') {
        date = date.add(amount, 'year');
      }
    } else if (operation === '-') {
      // 减去相应的时间
      if (unit === 'd') {
        date = date.subtract(amount, 'day');
      } else if (unit === 'M') {
        date = date.subtract(amount, 'month');
      } else if (unit === 'y') {
        date = date.subtract(amount, 'year');
      }
    }

    // 根据格式返回日期
    if (format === 'yyyy-MM-dd') {
      return date.format('YYYY-MM-DD');
    } else if (format === 'yyyyMMdd') {
      return date.format('YYYYMMDD');
    }
  }

  return value;
};

/**
 * 替换SQL中的参数占位符
 * @param sql SQL查询语句
 * @param params 参数对象
 * @returns 替换参数后的SQL语句
 */
export function replaceParametersInCode(
  code: string,
  params: Record<string, any>
): string {
  if (!code || !params) {
    return code;
  }

  let result = code;

  // 处理每个参数值并替换SQL中的占位符
  for (const paramName in params) {
    if (Object.prototype.hasOwnProperty.call(params, paramName)) {
      const paramValue = params[paramName];

      // 替换SQL中的参数占位符 ${param_name}
      const placeholder = `\${${paramName}}`;
      result = result.replace(
        new RegExp(escapeRegExp(placeholder), 'g'),
        String(paramValue)
      );
    }
  }

  // 处理日期格式参数
  const dateRegex = /\$\{([yMd-]+[+-]?\d*[d]?)\}/g;
  let match;

  while ((match = dateRegex.exec(result)) !== null) {
    const pattern = match[0];
    const dateFormat = match[1];
    result = result.replace(pattern, parseDateParameter(dateFormat));
  }

  return result;
}

/**
 * 转义正则表达式中的特殊字符
 * @param string 需要转义的字符串
 * @returns 转义后的字符串
 */
function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * 解析日期参数
 * @param pattern 日期格式模式
 * @returns 格式化后的日期字符串
 */
function parseDateParameter(pattern: string): string {
  // 提取日期格式和偏移量
  const formatMatch = pattern.match(/([yMd-]+)([+-]\d+[d])?/);
  if (!formatMatch) return pattern;

  const format = formatMatch[1];
  const offset = formatMatch[2] || '';

  // 创建日期对象
  let date = new Date();

  // 处理日期偏移
  if (offset) {
    const offsetMatch = offset.match(/([+-])(\d+)([d])?/);
    if (offsetMatch) {
      const sign = offsetMatch[1] === '+' ? 1 : -1;
      const value = parseInt(offsetMatch[2], 10);
      const unit = offsetMatch[3] || 'd'; // 默认为天

      if (unit === 'd') {
        date.setDate(date.getDate() + sign * value);
      }
    }
  }

  // 格式化日期
  return formatDate(date, format);
}

/**
 * 格式化日期
 * @param date 日期对象
 * @param format 格式字符串
 * @returns 格式化后的日期字符串
 */
function formatDate(date: Date, format: string): string {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();

  // 替换年份
  let result = format.replace(/yyyy/g, year.toString());
  result = result.replace(/yy/g, year.toString().slice(-2));

  // 替换月份
  result = result.replace(/MM/g, month.toString().padStart(2, '0'));
  result = result.replace(/M/g, month.toString());

  // 替换日
  result = result.replace(/dd/g, day.toString().padStart(2, '0'));
  result = result.replace(/d/g, day.toString());

  return result;
}
