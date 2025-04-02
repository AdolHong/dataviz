// 动态日期解析函数
const parseDynamicDate = (value: string) => {
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


def replace_parameters_in_sql(sql: str, params: Dict[str,str]) -> str:
    """替换SQL中的参数占位符"""
    if not sql or not param_values:
        return sql
    
   # 处理每个参数值并替换SQL中的占位符
    for param_name in params:
        param_value = params[param_name]

        # 替换SQL中的参数占位符 ${param_name}
        placeholder = f"${{{param_name}}}"
        sql = sql.replace(placeholder, str(param_value))
    
    # 处理日期格式参数
    import re
    date_patterns = re.finditer(r'\$\{[yMd-]+[+-]?\d*[d]?\}', sql)
    for match in date_patterns:
        pattern = match.group()
        sql = sql.replace(pattern, _parse_date_parameter(pattern))
    
    return sql