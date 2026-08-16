"""工时费率表缺省（工厂可改）。"""

RATE_TABLE = [
    {"equipment_type": "3轴立式加工中心", "hourly_rate": 120, "setup_fee": 200, "programming_fee_new": 300},
    {"equipment_type": "4轴立式加工中心", "hourly_rate": 150, "setup_fee": 300, "programming_fee_new": 500},
    {"equipment_type": "5轴联动加工中心", "hourly_rate": 280, "setup_fee": 500, "programming_fee_new": 800},
    {"equipment_type": "卧式加工中心", "hourly_rate": 180, "setup_fee": 400, "programming_fee_new": 300},
    {"equipment_type": "龙门加工中心", "hourly_rate": 220, "setup_fee": 600, "programming_fee_new": 300},
    {"equipment_type": "精密坐标镗床", "hourly_rate": 350, "setup_fee": 250, "programming_fee_new": 300},
    {"equipment_type": "电火花成型机EDM", "hourly_rate": 180, "setup_fee": 250, "programming_fee_new": 500},
    {"equipment_type": "电火花线切割WEDM", "hourly_rate": 60, "setup_fee": 250, "programming_fee_new": 300},
    {"equipment_type": "车削中心CNC车", "hourly_rate": 100, "setup_fee": 150, "programming_fee_new": 300},
    {"equipment_type": "车铣复合中心", "hourly_rate": 200, "setup_fee": 400, "programming_fee_new": 800},
    {"equipment_type": "外圆磨床", "hourly_rate": 160, "setup_fee": 250, "programming_fee_new": 300},
    {"equipment_type": "平面磨床", "hourly_rate": 140, "setup_fee": 250, "programming_fee_new": 300},
]

MACHINE_SEEDS = [
    {"id": "VM-3AX", "type": "3轴立式加工中心", "axes": 3, "travel_x": 850, "travel_y": 500, "travel_z": 500, "max_rpm": 12000, "power_kw": 11, "tool_change_s": 3.5, "fixture_mode": "虎钳", "hourly_rate": 120, "setup_fee": 200, "enabled": 1},
    {"id": "VM-4AX", "type": "4轴立式加工中心", "axes": 4, "travel_x": 800, "travel_y": 500, "travel_z": 500, "max_rpm": 10000, "power_kw": 11, "tool_change_s": 3.5, "fixture_mode": "第四轴转台", "hourly_rate": 150, "setup_fee": 300, "enabled": 1},
    {"id": "VM-5AX", "type": "5轴联动加工中心", "axes": 5, "travel_x": 650, "travel_y": 550, "travel_z": 500, "max_rpm": 12000, "power_kw": 15, "tool_change_s": 3.2, "fixture_mode": "五轴摇篮", "hourly_rate": 280, "setup_fee": 500, "enabled": 1},
    {"id": "HMC-1", "type": "卧式加工中心", "axes": 4, "travel_x": 800, "travel_y": 700, "travel_z": 700, "max_rpm": 8000, "power_kw": 18, "tool_change_s": 4.0, "fixture_mode": "卧式托盘", "hourly_rate": 180, "setup_fee": 400, "enabled": 1},
]

MATERIAL_PRICES = [
    {"material_code": "AL6061-T6", "family": "铝合金", "price_per_kg": 28, "scrap_price_per_kg": 8, "density_g_cm3": 2.70},
    {"material_code": "AL7075", "family": "铝合金", "price_per_kg": 45, "scrap_price_per_kg": 12, "density_g_cm3": 2.80},
    {"material_code": "SUS304", "family": "不锈钢", "price_per_kg": 32, "scrap_price_per_kg": 8, "density_g_cm3": 7.93},
    {"material_code": "铝合金", "family": "铝合金", "price_per_kg": 25, "scrap_price_per_kg": 6, "density_g_cm3": 2.70},
    {"material_code": "不锈钢", "family": "不锈钢", "price_per_kg": 30, "scrap_price_per_kg": 8, "density_g_cm3": 7.93},
    {"material_code": "钢", "family": "普通碳钢", "price_per_kg": 8, "scrap_price_per_kg": 2, "density_g_cm3": 7.85},
    {"material_code": "POM", "family": "工程塑料", "price_per_kg": 18, "scrap_price_per_kg": 2, "density_g_cm3": 1.41},
]

