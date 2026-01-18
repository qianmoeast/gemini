# -*- coding: utf-8 -*-
# Task4_RandomPoints_Extraction_UpdatedPaths_TimeTrack.py
# 运行环境：ArcGIS Pro Python (arcpy)

import arcpy
from arcpy.sa import *
import os
import pandas as pd
import time  # 【新增】导入时间模块

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

# 3. 静态驱动因子 (Static driver)
STATIC_DIR = r"E:\paper1\shuju\1raster_clip\1Static driver"

# 地形相关 (DEM, Slope, Aspect, TWI)
DEM_PATH = os.path.join(STATIC_DIR, "dem", "Extract_dem_250m.tif")
SLOPE_ASPECT_DIR = os.path.join(STATIC_DIR, "Slope Aspect")
SLOPE_PATH = os.path.join(SLOPE_ASPECT_DIR, "Slope.tif")
ASPECT_PATH = os.path.join(SLOPE_ASPECT_DIR, "Aspect.tif")
TWI_PATH = os.path.join(SLOPE_ASPECT_DIR, "TWI.sdat")

# 土壤数据 (China soil)
SOIL_DIR = os.path.join(STATIC_DIR, "China soil")

# 冻土矢量数据路径
FROZEN_SHP_PATH = r"E:\paper1\shuju\Frozen_soil\Frozen_soil_Ran2012.shp"

# --- 输出路径 ---
OUTPUT_SHP_DIR = r"E:\paper1\shuju\shp"
OUTPUT_CSV_DIR = r"E:\paper1\excel"

if not os.path.exists(OUTPUT_SHP_DIR): os.makedirs(OUTPUT_SHP_DIR)
if not os.path.exists(OUTPUT_CSV_DIR): os.makedirs(OUTPUT_CSV_DIR)

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
    # 【新增】记录开始时间
    t_start = time.time()
    start_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t_start))
    print(f"=======================================================")
    print(f"任务开始时间: {start_str}")
    print(f"=======================================================\n")
    
    print(">>> 开始执行集成提取任务 (更新路径版)...")

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
        # 只要有值的区域都可布点 (LULC > 0)
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

    # --- 步骤 2: 冻土数据矢量相交 (Spatial Join) ---
    print("\n>>> 处理矢量数据交互 (冻土)...")
    if not arcpy.Exists(FROZEN_SHP_PATH):
        print(f"[错误] 找不到冻土矢量文件: {FROZEN_SHP_PATH}")
        return

    # 定义一个中间文件，用于存储包含冻土属性的点
    joined_shp = os.path.join(OUTPUT_SHP_DIR, "Temp_Frozen_Joined.shp")

    # 如果已存在先删除，防止字段冲突
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

    # --- 步骤 3: 准备作为栅格提取输入的工作文件 ---
    working_shp = os.path.join(OUTPUT_SHP_DIR, "Temp_Process_Points.shp")
    if arcpy.Exists(working_shp): arcpy.management.Delete(working_shp)

    arcpy.management.CopyFeatures(joined_shp, working_shp)
    arcpy.management.Delete(joined_shp)

    # --- 步骤 4: 构建栅格提取列表 ---
    extract_list = []

    # A. 静态变量 (地形 + TWI + 土壤)
    print("\n>>> 准备栅格变量...")

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

    # 2. 土壤 (China soil)
    soil_mapping = {
        "clay1.tif": "clay1", "clay2.tif": "clay2",
        "geomor.tif": "geom", "soil_type.tif": "soil_type",
        "sand1.tif": "sand1", "sand2.tif": "sand2"
    }
    if os.path.exists(SOIL_DIR):
        for filename, col_name in soil_mapping.items():
            file_path = os.path.join(SOIL_DIR, filename)
            if os.path.exists(file_path):
                extract_list.append([file_path, col_name])
            else:
                print(f"  [警告] 缺失土壤文件: {filename}")
    else:
        print(f"  [警告] 土壤文件夹不存在: {SOIL_DIR}")

    # B. 动态年份变量 (LULC, Climate, GDP, POP)
    print("\n>>> 准备动态年份变量...")

    for year in TARGET_YEARS:
        ys = get_year_suffix(year)

        # 1. LULC (来自 5resmple)
        p = os.path.join(LULC_DIR, f"{year}.tif")
        if os.path.exists(p):
            extract_list.append([p, f"LULC_{ys}"])
        else:
            print(f"  [警告] 缺失 LULC {year}")

        # 2. Climate
        clim_vars = ["pet", "pre", "tmp", "tmx", "tmn"]
        for var in clim_vars:
            var_dir = os.path.join(CLIMATE_DIR, var)
            p = find_file(var_dir, [str(year)])
            if p:
                extract_list.append([p, f"{var}_{ys}"])
            else:
                p = find_file(CLIMATE_DIR, [var, str(year)])
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

    # --- 步骤 5: 执行栅格提取 ---
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

    if "CLASS_ID" not in fields:
        print("[警告] 在属性表中未找到 'CLASS_ID' 字段。")

    data_rows = []
    with arcpy.da.SearchCursor(working_shp, ["OID@", "SHAPE@X", "SHAPE@Y"] + fields) as cursor:
        for row in cursor:
            data_rows.append(row)

    master_df = pd.DataFrame(data_rows, columns=["PointID", "Lon", "Lat"] + fields)

    # 全局清洗
    print(f"  初始点数: {len(master_df)}")
    master_df.dropna(inplace=True)
    print(f"  清洗后点数: {len(master_df)}")

    if len(master_df) == 0:
        print("[错误] 所有点都被剔除了！")
        return

    # --- 步骤 7: 逐年拆分并导出 ---

    # 识别静态字段
    static_cols = ["PointID", "Lon", "Lat"]
    frozen_col = "CLASS_ID"
    if frozen_col in fields:
        static_cols.append(frozen_col)

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

        if frozen_col in master_df.columns:
            rename_dict[frozen_col] = "Frozen"

        year_dynamic_cols = []
        for col in fields:
            if col.endswith(f"_{ys}"):
                year_dynamic_cols.append(col)
                base_name = col[:-3]
                if base_name == "GDPT": new_name = "GDP_T"
                elif base_name == "GDPP": new_name = "GDP_P"
                elif base_name == "POPC": new_name = "POP_C"
                elif base_name == "POPD": new_name = "POP_D"
                else: new_name = base_name
                rename_dict[col] = new_name

        df_year = master_df[current_cols + year_dynamic_cols].copy()
        df_year.rename(columns=rename_dict, inplace=True)
        df_year["Year"] = year

        p_out = os.path.join(OUTPUT_CSV_DIR, f"point_{year}.csv")
        df_year.to_csv(p_out, index=False, encoding='utf-8-sig')
        print(f"  [1] point_{year}.csv (共 {len(df_year)} 行)")

        if "LULC" in df_year.columns:
            df_wet = df_year[df_year["LULC"].isin(VALID_WET_CODES)]
            w_out = os.path.join(OUTPUT_CSV_DIR, f"wet_{year}.csv")
            df_wet.to_csv(w_out, index=False, encoding='utf-8-sig')
            print(f"  [2] wet_{year}.csv   (共 {len(df_wet)} 行)")

    try:
        if arcpy.Exists(working_shp): arcpy.management.Delete(working_shp)
    except:
        pass
    
    # 【新增】计算并打印耗时
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
