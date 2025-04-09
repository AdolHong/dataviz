import type { Parameter } from '@/types/models/parameter';
import dayjs from 'dayjs';
import { toast } from 'sonner';

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

const regReplace = (result: string, placeholder: string, value: string) => {
  return result.replace(
    new RegExp(escapeRegExp(placeholder), 'g'),
    String(value)
  );
};

/**
 * 替换SQL中的参数占位符
 * @param sql SQL查询语句
 * @param params 参数对象
 * @returns 替换参数后的SQL语句
 */
export function replaceParametersInCode(
  code: string,
  params: Record<string, any>,
  parameters: Parameter[]
): string {
  if (!code || !params) {
    return code;
  }

  let result = code;

  // 处理每个参数值并替换SQL中的占位符
  for (const paramName in params) {
    if (Object.prototype.hasOwnProperty.call(params, paramName)) {
      let paramValue = params[paramName];
      const paramSetting = parameters.find(
        (p) => p.name === paramName
      ) as Parameter;

      if (paramSetting.config.type !== 'date_range_picker') {
        // 多选参数 需要预处理
        if (
          Array.isArray(paramValue) &&
          (paramSetting.config.type === 'multi_select' ||
            paramSetting.config.type === 'multi_input')
        ) {
          const sep = paramSetting.config.sep;
          const wrapper = paramSetting.config.wrapper;
          paramValue = paramValue
            .map((value) => wrapper + value + wrapper)
            .join(sep);
        }

        result = regReplace(result, `\${${paramName}}`, paramValue);
      } else {
        // 日期范围参数 需要预处理
        if (!Array.isArray(paramValue) || paramValue.length !== 2) {
          toast.error(`[${paramName}] 请选择日期范围`);
          throw new Error(`[${paramName}] 请选择日期范围`);
        }
        const [startDate, endDate] = paramValue;

        result = regReplace(result, `\${${paramName}:start}`, startDate);
        result = regReplace(result, `\${${paramName}:end}`, endDate);
      }
    }
  }

  // 使用更可靠的方法处理所有日期格式
  // 先找出所有匹配的日期模式
  const datePattern = /\$\{(yyyy-MM-dd|yyyyMMdd)(?:[+-]\d+[dMy])?\}/g;
  const matches = result.match(datePattern) || [];

  // 对每个匹配项进行替换
  for (const match of [...new Set(matches)]) {
    const parsedDate = parseDynamicDate(match);
    result = result.replace(new RegExp(escapeRegExp(match), 'g'), parsedDate);
  }

  console.info('result', result);
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
