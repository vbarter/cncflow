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
    {"id": "VM-3AX", "type": "3轴立式加工中心", "axes": 3, "max_rpm": 12000, "hourly_rate": 120, "setup_fee": 200, "enabled": 1},
    {"id": "VM-4AX", "type": "4轴立式加工中心", "axes": 4, "max_rpm": 10000, "hourly_rate": 150, "setup_fee": 300, "enabled": 1},
    {"id": "VM-5AX", "type": "5轴联动加工中心", "axes": 5, "max_rpm": 12000, "hourly_rate": 280, "setup_fee": 500, "enabled": 1},
    {"id": "HMC-1", "type": "卧式加工中心", "axes": 4, "max_rpm": 8000, "hourly_rate": 180, "setup_fee": 400, "enabled": 1},
]

MATERIAL_PRICES = [
    {"material_code": "AL6061-T6", "price_per_kg": 28, "scrap_price_per_kg": 8},
    {"material_code": "AL7075", "price_per_kg": 45, "scrap_price_per_kg": 12},
    {"material_code": "SUS304", "price_per_kg": 32, "scrap_price_per_kg": 8},
    {"material_code": "铝合金", "price_per_kg": 25, "scrap_price_per_kg": 6},
    {"material_code": "不锈钢", "price_per_kg": 30, "scrap_price_per_kg": 8},
    {"material_code": "钢", "price_per_kg": 8, "scrap_price_per_kg": 2},
    {"material_code": "POM", "price_per_kg": 18, "scrap_price_per_kg": 2},
]

