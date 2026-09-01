select province_code, province_name, city_code, city_name, revenue, orders from (values
  ('GD', '广东', 'SZ', '深圳', 128, 76),
  ('GD', '广东', 'GZ', '广州', 112, 69),
  ('HN', '湖南', 'CS', '长沙', 91, 58),
  ('FJ', '福建', 'XM', '厦门', 97, 61),
  ('ZJ', '浙江', 'HZ', '杭州', 135, 82)
) as metrics(province_code, province_name, city_code, city_name, revenue, orders)
where {{ dataviz_filter:province_scope }}
  and {{ dataviz_filter:city_scope }}
order by revenue desc
