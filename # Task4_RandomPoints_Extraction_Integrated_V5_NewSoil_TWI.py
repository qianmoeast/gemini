# -*- coding: utf-8 -*-
# Task4_RandomPoints_Extraction_UpdatedPaths_v2.py
# 运行环境：ArcGIS Pro Python (arcpy)

import arcpy
from arcpy.sa import *
import os
import pandas as pd
import time

# ================= 1. 参数配置区域 =================

# 工作空间设置
WORK_DIR = r"E:\paper1"
arcpy.env.workspace = WORK_DIR
arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")

# --- 输入数据路径 (基于提供的目录结构更新) ---

# 1. LULC 数据 (使用 5resmple 文件夹)
LULC_DIR = r"E:\paper1\shuju\0LULC\5resmple"

# 2. 动态驱动因子 (Dynamic drivers)
# 气候数据
CLIMATE_DIR = r"E:\paper1\shuju\1raster_clip\1Dynamic drivers\climate"
# GDP 数据
GDP_DIR = r"E:\paper1\shuju\1raster_clip\1Dynamic drivers\GDP"
# 人口数据
POP_DIR = r"E:\paper1\shuju\1raster_clip\1Dynamic drivers\GlobPOP"
# 夜光遥感数据 (新增)
NTL_DIR = r"E:\paper1\shuju\1raster_clip\1Dynamic drivers\NTL"


# 3. 静态驱动因子 (Static driver)
STATIC_DIR = r"E:\paper1\shuju\1raster_clip\1Static driver"

# 地形相关
DEM_PATH = os.path.join(STATIC_DIR, "dem", "Extract_dem_250m.tif")
SLOPE_ASPECT_DIR = os.path.join(STATIC_DIR, "Slope Aspect")
SLOPE_PATH = os.path.join(SLOPE_ASPECT_DIR, "Slope.tif")
ASPECT_PATH = os.path.join(SLOPE_ASPECT_DIR, "Aspect.tif")
TWI_PATH = os.path.join(SLOPE_ASPECT_DIR, "TWI.sdat")

# 土壤数据 (China soil - 旧版)
SOIL_CHINA_DIR = os.path.join(STATIC_DIR, "China soil")

# 土壤数据 (HWSD2 - 新增)
SOIL_HWSD2_DIR = os.path.join(STATIC_DIR, "HWSD2")

# 冻土矢量数据路径
FROZEN_SHP_PATH = r"E:\paper1\shuju\Frozen_soil\Frozen_soil_Ran2012.shp"

# --- 输出路径 ---
OUTPUT_SHP_DIR = r"E:\paper1\shuju\shp"
OUTPUT_POINT_DIR = r"E:\paper1\excel\point\1"
OUTPUT_WET_DIR = r"E:\paper1\excel\wet\1"

if not os.path.exists(OUTPUT_SHP_DIR): os.makedirs(OUTPUT_SHP_DIR)
if not os.path.exists(OUTPUT_POINT_DIR): os.makedirs(OUTPUT_POINT_DIR)
if not os.path.exists(OUTPUT_WET_DIR): os.makedirs(OUTPUT_WET_DIR)

# 目标年份
TARGET_YEARS = [1990, 1995, 2000, 2005, 2010, 2015, 2020]

# 随机点设置
NUM_POINTS = 100000
MIN_DISTANCE = "1 Kilometers"
VALID_WET_CODES = [1, 2, 3, 4, 5]


# ================= 2. 辅助函数 =================

def find_file(directory, keywords, ext=".tif"):
    """模糊查找文件"""
    if not os.path.exists(directory): return None
    for f in os.listdir(directory):
        if f.endswith(ext) and all(k in f for k in keywords):
            return os.path.join(directory, f)
    return None


def get_year_suffix(year):
    """生成年份后缀，例如 1990 -> 90"""
    return str(year)[-2:]


# ================= 3. 核心流程 =================

def main():
    # 记录开始时间
    t_start = time.time()
    start_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t_start))
    print(f"=======================================================")
    print(f"任务开始时间: {start_str}")
    print(f"=======================================================\n")

    print(">>> 开始执行集成提取任务 (更新路径 v2)...")

    # --- 步骤 1: 生成或加载随机点 ---
    master_shp = os.path.join(OUTPUT_SHP_DIR, "Master_Sample_Points.shp")

    if not arcpy.Exists(master_shp):
        print("  正在生成随机点模板 (基于2020年LULC)...")
        lulc_2020 = os.path.join(LULC_DIR, "2020.tif")
        if not os.path.exists(lulc_2020):
            print(f"  [错误] 找不到2020年LULC数据 ({lulc_2020})")
            return

        temp_poly = os.path.join(OUTPUT_SHP_DIR, "Temp_Valid_Area.shp")
        ras = Raster(lulc_2020)
        valid_area = Con(ras > 0, 1)
        arcpy.conversion.RasterToPolygon(valid_area, temp_poly, "SIMPLIFY", "VALUE")

        print(f"  正在创建 {NUM_POINTS} 个随机点...")
        arcpy.management.CreateRandomPoints(
            out_path=OUTPUT_SHP_DIR,
            out_name="Master_Sample_Points.shp",
            constraining_feature_class=temp_poly,
            number_of_points_or_field=NUM_POINTS,
            minimum_allowed_distance=MIN_DISTANCE
        )
        arcpy.management.Delete(temp_poly)
        print(f"  随机点已生成: {master_shp}")
    else:
        print(f"  使用现有的主点文件: {master_shp}")

    # --- 步骤 2: 冻土数据矢量相交 ---
    print("\n>>> 处理矢量数据交互 (冻土)...")
    if not arcpy.Exists(FROZEN_SHP_PATH):
        print(f"[错误] 找不到冻土矢量文件: {FROZEN_SHP_PATH}")
        return

    joined_shp = os.path.join(OUTPUT_SHP_DIR, "Temp_Frozen_Joined.shp")
    if arcpy.Exists(joined_shp): arcpy.management.Delete(joined_shp)

    print("  正在执行空间连接 (Spatial Join)...")
    try:
        arcpy.analysis.SpatialJoin(
            target_features=master_shp,
            join_features=FROZEN_SHP_PATH,
            out_feature_class=joined_shp,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="INTERSECT"
        )
        print(f"  空间连接完成: {joined_shp}")
    except Exception as e:
        print(f"  [空间连接失败] {e}")
        return

    # --- 步骤 3: 准备工作文件 ---
    working_shp = os.path.join(OUTPUT_SHP_DIR, "Temp_Process_Points.shp")
    if arcpy.Exists(working_shp): arcpy.management.Delete(working_shp)

    arcpy.management.CopyFeatures(joined_shp, working_shp)
    arcpy.management.Delete(joined_shp)

    # --- 步骤 4: 构建提取列表 ---
    extract_list = []

    # A. 静态变量 (Static Variables)
    print("\n>>> 准备静态变量...")

    # 1. 地形
    if os.path.exists(DEM_PATH):
        extract_list.append([DEM_PATH, "DEM"])
    else:
        print(f"  [警告] 缺失 DEM: {DEM_PATH}")

    if os.path.exists(SLOPE_PATH):
        extract_list.append([SLOPE_PATH, "Slope"])
    else:
        print(f"  [警告] 缺失 Slope: {SLOPE_PATH}")

    if os.path.exists(ASPECT_PATH):
        extract_list.append([ASPECT_PATH, "Aspect"])
    else:
        print(f"  [警告] 缺失 Aspect: {ASPECT_PATH}")

    if os.path.exists(TWI_PATH):
        extract_list.append([TWI_PATH, "TWI"])
    else:
        print(f"  [警告] 缺失 TWI: {TWI_PATH}")

    # 2. 土壤 (China soil - 旧版)
    # 根据目录树，主要保留 _250m.tif 结尾的文件
    soil_china_mapping = {
        "clay1_250m.tif": "clay1",
        "clay2_250m.tif": "clay2",
        "geomor_reclass_250m.tif": "geom",
        "sand1_250m.tif": "sand1",
        "sand2_250m.tif": "sand2",
        "soil_type_reclass_gang_250m.tif": "soil_type"
    }
    if os.path.exists(SOIL_CHINA_DIR):
        for filename, col_name in soil_china_mapping.items():
            file_path = os.path.join(SOIL_CHINA_DIR, filename)
            if os.path.exists(file_path):
                extract_list.append([file_path, col_name])
            else:
                print(f"  [警告] 缺失 China soil 文件: {filename}")
    else:
        print(f"  [警告] China soil 文件夹不存在: {SOIL_CHINA_DIR}")

    # 3. 土壤 (HWSD2 - 新增)
    # 根据目录树，添加 HWSD2 下的所有 .tif 文件
    # 字段名简化：TP_Final_D1_BULK.tif -> D1_BULK
    if os.path.exists(SOIL_HWSD2_DIR):
        for f in os.listdir(SOIL_HWSD2_DIR):
            if f.endswith(".tif") and "TP_Final" in f:
                file_path = os.path.join(SOIL_HWSD2_DIR, f)
                # 提取简化列名：TP_Final_D1_BULK -> D1_BULK
                # 假设文件名格式固定为 TP_Final_XX_YY.tif
                parts = f.replace(".tif", "").split("_")
                if len(parts) >= 4:
                    col_name = "_".join(parts[2:]).lower() # e.g., d1_bulk
                else:
                    col_name = f.replace(".tif", "")[-10:] # 备用缩写
                
                extract_list.append([file_path, col_name])
    else:
        print(f"  [警告] HWSD2 文件夹不存在: {SOIL_HWSD2_DIR}")

    # B. 动态年份变量 (Dynamic Variables)
    print("\n>>> 准备动态年份变量...")

    for year in TARGET_YEARS:
        ys = get_year_suffix(year)

        # 1. LULC
        p = os.path.join(LULC_DIR, f"{year}.tif")
        if os.path.exists(p):
            extract_list.append([p, f"LULC_{ys}"])
        else:
            print(f"  [警告] 缺失 LULC {year}")

        # 2. Climate
        for var in ["pet", "pre", "tmp", "tmx", "tmn"]:
            var_dir = os.path.join(CLIMATE_DIR, var)
            p = find_file(var_dir, [str(year)])
            if not p: p = find_file(CLIMATE_DIR, [var, str(year)])
            
            if p:
                extract_list.append([p, f"{var}_{ys}"])
            else:
                print(f"  [警告] 缺失气候数据 {var} {year}")

        # 3. GDP
        p = find_file(GDP_DIR, ["Total", str(year)])
        if p: extract_list.append([p, f"GDPT_{ys}"])
        
        p = find_file(GDP_DIR, ["PerCapita", str(year)])
        if p: extract_list.append([p, f"GDPP_{ys}"])

        # 4. POP
        p = find_file(POP_DIR, ["Count", str(year)])
        if p: extract_list.append([p, f"POPC_{ys}"])
        
        p = find_file(POP_DIR, ["Density", str(year)])
        if p: extract_list.append([p, f"POPD_{ys}"])
        
        # 5. NTL (新增)
        p = find_file(NTL_DIR, ["NTL", str(year)])
        if p: extract_list.append([p, f"NTL_{ys}"])
        else: print(f"  [警告] 缺失夜光遥感数据 NTL {year}")

    # --- 步骤 5: 执行提取 ---
    print(f"  正在将 {len(extract_list)} 个栅格变量提取到 Shapefile...")
    try:
        arcpy.sa.ExtractMultiValuesToPoints(working_shp, extract_list, "NONE")
        print("  栅格提取完成！")
    except Exception as e:
        print(f"  [提取失败] 错误详情: {e}")
        return

    # --- 步骤 6: 转换为 DataFrame 并清洗 ---
    print("\n>>> 正在处理属性表与导出...")
    fields = [f.name for f in arcpy.ListFields(working_shp) if f.type not in ['Geometry', 'OID']]

    data_rows = []
    with arcpy.da.SearchCursor(working_shp, ["OID@", "SHAPE@X", "SHAPE@Y"] + fields) as cursor:
        for row in cursor:
            data_rows.append(row)

    master_df = pd.DataFrame(data_rows, columns=["PointID", "Lon", "Lat"] + fields)

    print(f"  初始点数: {len(master_df)}")
    master_df.dropna(inplace=True)
    print(f"  清洗后点数: {len(master_df)}")

    if len(master_df) == 0:
        print("[错误] 所有点都被剔除了！")
        return

    # --- 步骤 7: 逐年拆分并导出 ---
    static_cols = ["PointID", "Lon", "Lat"]
    frozen_col = "CLASS_ID"
    if frozen_col in fields: static_cols.append(frozen_col)

    # 自动识别其他静态列（如土壤、地形）
    for col in fields:
        is_dynamic = False
        for yr in TARGET_YEARS:
            if col.endswith(f"_{get_year_suffix(yr)}"):
                is_dynamic = True
                break
        if not is_dynamic and col not in static_cols:
            static_cols.append(col)

    for year in TARGET_YEARS:
        ys = get_year_suffix(year)
        print(f"\n>>> 导出年份 {year} ...")

        current_cols = static_cols.copy()
        rename_dict = {}

        if frozen_col in master_df.columns: rename_dict[frozen_col] = "Frozen"

        year_dynamic_cols = []
        for col in fields:
            if col.endswith(f"_{ys}"):
                year_dynamic_cols.append(col)
                # 动态变量重命名
                base_name = col[:-3]
                if base_name == "GDPT": new_name = "GDP_T"
                elif base_name == "GDPP": new_name = "GDP_P"
                elif base_name == "POPC": new_name = "POP_C"
                elif base_name == "POPD": new_name = "POP_D"
                # NTL 不需要特殊重命名，保持 NTL_90 即可，或者去掉年份
                # 这里如果只想要 NTL，可以: elif base_name == "NTL": new_name = "NTL"
                else: new_name = base_name
                rename_dict[col] = new_name

        df_year = master_df[current_cols + year_dynamic_cols].copy()
        df_year.rename(columns=rename_dict, inplace=True)
        df_year["Year"] = year

        # 导出 point csv
        p_out = os.path.join(OUTPUT_POINT_DIR, f"point_{year}.csv")
        df_year.to_csv(p_out, index=False, encoding='utf-8-sig')
        print(f"  [1] point_{year}.csv 已保存")

        # 导出 wet csv
        if "LULC" in df_year.columns:
            df_wet = df_year[df_year["LULC"].isin(VALID_WET_CODES)]
            w_out = os.path.join(OUTPUT_WET_DIR, f"wet_{year}.csv")
            df_wet.to_csv(w_out, index=False, encoding='utf-8-sig')
            print(f"  [2] wet_{year}.csv   已保存")

    # 清理临时文件
    try:
        if arcpy.Exists(working_shp): arcpy.management.Delete(working_shp)
    except:
        pass

    # 计算耗时
    t_end = time.time()
    end_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t_end))
    total_seconds = t_end - t_start
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)

    print(f"\n=======================================================")
    print(f"任务结束时间: {end_str}")
    print(f"总耗时: {hours} h : {minutes} m")
    print(f"=======================================================")


if __name__ == "__main__":
    main()
