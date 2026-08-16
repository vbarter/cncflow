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
    # 3轴《CNC加工设备库0815》
    {"id": "VMC850E", "type": "3轴立式加工中心", "axes": 3, "travel_x": 850, "travel_y": 505, "travel_z": 505, "max_rpm": 12000, "power_kw": 7.5, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 70, "magazine": 24, "table": "1000x520", "taper": "BT40", "ref_price": 28}},
    {"id": "VMC1160", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1100, "travel_y": 600, "travel_z": 600, "max_rpm": 10000, "power_kw": 11, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 120, "magazine": 32, "table": "1250x600", "taper": "BT40", "ref_price": 35}},
    {"id": "VMC1370", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1300, "travel_y": 700, "travel_z": 700, "max_rpm": 8000, "power_kw": 15, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 180, "magazine": 36, "table": "1400x700", "taper": "BT40", "ref_price": 42}},
    {"id": "VMC1580", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1500, "travel_y": 800, "travel_z": 800, "max_rpm": 8000, "power_kw": 18.5, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 220, "magazine": 40, "table": "1600x800", "taper": "BT50", "ref_price": 55}},
    {"id": "VMC1813", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1800, "travel_y": 1300, "travel_z": 900, "max_rpm": 6000, "power_kw": 22, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 350, "magazine": 50, "table": "2000x1300", "taper": "BT50", "ref_price": 85}},
    # 4轴
    {"id": "VMC850E+HRV160A", "type": "4轴立式加工中心", "axes": 4, "travel_x": 850, "travel_y": 500, "travel_z": 505, "max_rpm": 12000, "power_kw": 7.5, "hourly_rate": 150, "setup_fee": 300, "enabled": 1, "extra": {"xyz": "850x500x505", "axis4": "160液压转台", "magazine": 24, "ref_price": 38}},
    {"id": "VMC1160+HRV210A", "type": "4轴立式加工中心", "axes": 4, "travel_x": 1100, "travel_y": 600, "travel_z": 600, "max_rpm": 10000, "power_kw": 11, "hourly_rate": 150, "setup_fee": 300, "enabled": 1, "extra": {"xyz": "1100x600x600", "axis4": "210液压转台", "magazine": 32, "ref_price": 48}},
    {"id": "TV855S", "type": "4轴立式加工中心", "axes": 4, "travel_x": 850, "travel_y": 505, "travel_z": 560, "max_rpm": 24000, "power_kw": 5.5, "hourly_rate": 150, "setup_fee": 300, "enabled": 1, "extra": {"xyz": "850x505x560", "axis4": "数控A轴转台", "magazine": 21, "ref_price": 52}},
    # 5轴
    {"id": "U600", "type": "5轴联动加工中心", "axes": 5, "travel_x": 600, "travel_y": 550, "travel_z": 450, "max_rpm": 24000, "power_kw": 11, "hourly_rate": 280, "setup_fee": 500, "enabled": 1, "extra": {"xyz": "600x550x450", "ab_range": "-120~+110/C360", "rtcp": "支持", "magazine": 30, "ref_price": 120}},
    {"id": "MU-S600", "type": "5轴联动加工中心", "axes": 5, "travel_x": 600, "travel_y": 560, "travel_z": 500, "max_rpm": 24000, "power_kw": 13.5, "hourly_rate": 280, "setup_fee": 500, "enabled": 1, "extra": {"xyz": "600x560x500", "ab_range": "+-110/C360", "rtcp": "支持", "magazine": 40, "ref_price": 145}},
    {"id": "DMU65", "type": "5轴联动加工中心", "axes": 5, "travel_x": 650, "travel_y": 520, "travel_z": 560, "max_rpm": 18000, "power_kw": 15, "hourly_rate": 280, "setup_fee": 500, "enabled": 1, "extra": {"xyz": "650x520x560", "ab_range": "+-110/C360", "rtcp": "支持", "magazine": 30, "ref_price": 168}},
    # 卧加
    {"id": "HWC500", "type": "卧式加工中心", "axes": 4, "travel_x": 560, "travel_y": 560, "travel_z": 560, "max_rpm": 10000, "power_kw": 11, "hourly_rate": 180, "setup_fee": 400, "enabled": 1, "extra": {"xyz": "560x560x560", "table": "500x500", "b_axis": "1度x360", "magazine": 40, "pallet": "单", "ref_price": 75}},
    {"id": "HWC630", "type": "卧式加工中心", "axes": 4, "travel_x": 750, "travel_y": 750, "travel_z": 720, "max_rpm": 8000, "power_kw": 18.5, "hourly_rate": 180, "setup_fee": 400, "enabled": 1, "extra": {"xyz": "750x750x720", "table": "630x630", "b_axis": "1度x360", "magazine": 60, "pallet": "双", "ref_price": 95}},
    {"id": "HWC800", "type": "卧式加工中心", "axes": 4, "travel_x": 1000, "travel_y": 800, "travel_z": 850, "max_rpm": 6000, "power_kw": 22, "hourly_rate": 180, "setup_fee": 400, "enabled": 1, "extra": {"xyz": "1000x800x850", "table": "800x800", "b_axis": "1度x360", "magazine": 80, "pallet": "双", "ref_price": 135}},
    # 龙门
    {"id": "GMC2012", "type": "龙门加工中心", "axes": 3, "travel_x": 2000, "travel_y": 1200, "travel_z": 800, "max_rpm": 6000, "power_kw": 22, "hourly_rate": 220, "setup_fee": 600, "enabled": 1, "extra": {"xyz": "2000x1200x800", "magazine": 30, "ref_price": 120}},
    {"id": "GMC3018", "type": "龙门加工中心", "axes": 3, "travel_x": 3000, "travel_y": 1800, "travel_z": 1200, "max_rpm": 4000, "power_kw": 30, "hourly_rate": 220, "setup_fee": 600, "enabled": 1, "extra": {"xyz": "3000x1800x1200", "magazine": 40, "ref_price": 185}},
    {"id": "GMC4022", "type": "龙门加工中心", "axes": 3, "travel_x": 4000, "travel_y": 2200, "travel_z": 1500, "max_rpm": 4000, "power_kw": 37, "hourly_rate": 220, "setup_fee": 600, "enabled": 1, "extra": {"xyz": "4000x2200x1500", "magazine": 50, "ref_price": 260}},
    # EDM
    {"id": "GF-C30", "type": "电火花成型机EDM", "axes": 3, "travel_x": 600, "travel_y": 400, "travel_z": 350, "hourly_rate": 180, "setup_fee": 250, "enabled": 1, "extra": {"xyz": "600x400x350", "electrode_kg": 200, "table": "800x400", "best_ra": 0.1, "ref_price": 25}},
    {"id": "Sodick-ALN40S", "type": "电火花成型机EDM", "axes": 3, "travel_x": 400, "travel_y": 250, "travel_z": 250, "hourly_rate": 180, "setup_fee": 250, "enabled": 1, "extra": {"xyz": "400x250x250", "electrode_kg": 50, "table": "450x250", "best_ra": 0.05, "ref_price": 18}},
    {"id": "EDS40S", "type": "电火花成型机EDM", "axes": 3, "travel_x": 400, "travel_y": 300, "travel_z": 280, "hourly_rate": 180, "setup_fee": 250, "enabled": 1, "extra": {"xyz": "400x300x280", "electrode_kg": 30, "table": "420x300", "best_ra": 0.2, "ref_price": 8}},
    # 车削
    {"id": "CK6150", "type": "车削中心CNC车", "axes": 2, "max_rpm": 4000, "power_kw": 7.5, "hourly_rate": 100, "setup_fee": 150, "enabled": 1, "extra": {"swing_d": 520, "turn_len": 1000, "turret": 12, "c_axis": "有", "ref_price": 18}},
    {"id": "CK6180", "type": "车削中心CNC车", "axes": 2, "max_rpm": 3000, "power_kw": 15, "hourly_rate": 100, "setup_fee": 150, "enabled": 1, "extra": {"swing_d": 800, "turn_len": 1500, "turret": 8, "c_axis": "有", "ref_price": 28}},
    {"id": "CTX1250", "type": "车削中心CNC车", "axes": 2, "max_rpm": 5000, "power_kw": 20, "hourly_rate": 100, "setup_fee": 150, "enabled": 1, "extra": {"swing_d": 660, "turn_len": 1250, "turret": 12, "c_axis": "有Y轴", "ref_price": 55}},
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

