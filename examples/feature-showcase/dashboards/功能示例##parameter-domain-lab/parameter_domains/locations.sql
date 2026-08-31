select * from (values
  ('GD', '广东', 1, 'SZ', '深圳', 1),
  ('GD', '广东', 1, 'GZ', '广州', 2),
  ('HN', '湖南', 2, 'CS', '长沙', 1),
  ('FJ', '福建', 3, 'XM', '厦门', 1),
  ('ZJ', '浙江', 4, 'HZ', '杭州', 1)
) as locations(
  province_code, province_name, province_order,
  city_code, city_name, city_order
)
