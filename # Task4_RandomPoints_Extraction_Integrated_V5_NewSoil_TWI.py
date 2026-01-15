# -*- coding: utf-8 -*-
# Task4_RandomPoints_Extraction_Integrated_V6_Fix000860.py
# 运行环境：ArcGIS Pro Python (arcpy)

import arcpy
from arcpy.sa import *
import os
import pandas as pd

# ================= 1. 参数配置区域 =================

# 工作空间设置
WORK_DIR = r"E:\paper1"
arcpy.env.workspace = WORK_DIR
arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")

# --- 输入数据路径 ---
LULC_DIR = r"E:\paper1\shuju\LULC\5resmple"
CLIMATE_DIR = r"Z:\datasat\0000A\zhujx\raster\qixiangshuju\qihou2"

# 地形相关
DEM_PATH = r"E:\paper1\shuju\dem\Extract_dem_250m.tif"
SLOPE_ASPECT_DIR = r"E:\paper1\shuju\Slope Aspect"
TWI_PATH = r"E:\paper1\shuju\Slope Aspect\TWI.sdat"

# 土壤数据
SOIL_DIR = r"E:\paper1\shuju\China soil\tiff"

# 社会经济
GDP_DIR = r"E:\paper1\shuju\GDP\2res"
POP_DIR = r"E:\paper1\shuju\GlobPOP\2res"

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
    print(">>> 开始执行集成提取任务 (V6: 硬盘临时文件版)...")

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

    # --- 步骤 2: 构建提取列表 ---
    extract_list = []
    
    # A. 静态变量
    print("  准备静态变量 (地形, TWI, 土壤)...")
    if os.path.exists(DEM_PATH): extract_list.append([DEM_PATH, "DEM"])
    
    slope = find_file(SLOPE_ASPECT_DIR, ["slope"], ".tif")
    if slope: extract_list.append([slope, "Slope"])
    
    aspect = find_file(SLOPE_ASPECT_DIR, ["aspect"], ".tif")
    if aspect: extract_list.append([aspect, "Aspect"])
    
    if os.path.exists(TWI_PATH):
        extract_list.append([TWI_PATH, "TWI"])
    else:
        print(f"  [警告] 缺失 TWI 数据: {TWI_PATH}")

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

    # B. 动态年份变量
    print("  准备动态年份变量...")
    
    for year in TARGET_YEARS:
        ys = get_year_suffix(year)
        
        # 1. LULC
        p = os.path.join(LULC_DIR, f"{year}.tif")
        if os.path.exists(p): extract_list.append([p, f"LULC_{ys}"])
        else: print(f"  [警告] 缺失 LULC {year}")
        
        # 2. Climate
        for var in ["pre", "tmp", "tmx", "tmn", "pet"]:
            p = find_file(os.path.join(CLIMATE_DIR, var), [str(year)])
            if not p: p = find_file(CLIMATE_DIR, [var, str(year)])
            if p: extract_list.append([p, f"{var}_{ys}"])
            
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

    # --- 步骤 3: 执行提取 (关键修改：使用硬盘临时文件) ---
    print(f"  正在将 {len(extract_list)} 个变量提取到 Shapefile...")
    
    # 【修改点】: 使用硬盘上的真实文件，而不是内存
    working_shp = os.path.join(OUTPUT_SHP_DIR, "Temp_Process_Points.shp")
    
    # 清理旧的临时文件
    if arcpy.Exists(working_shp):
        try:
            arcpy.management.Delete(working_shp)
        except:
            print("  [警告] 无法删除旧的临时文件，请确保它未在ArcGIS中打开。")
            return

    print(f"  复制主点文件到临时文件: {working_shp} ...")
    arcpy.management.CopyFeatures(master_shp, working_shp)
    
    # 再次检查文件是否存在
    if not arcpy.Exists(working_shp):
        print("[错误] 临时文件创建失败，请检查磁盘空间或权限。")
        return

    try:
        # 核心提取步骤
        arcpy.sa.ExtractMultiValuesToPoints(working_shp, extract_list, "NONE")
        print("  提取完成！正在处理属性表...")
    except Exception as e:
        print(f"  [提取失败] 错误详情: {e}")
        # 如果是 000860，通常是输入路径问题，现在用了绝对路径应该能解决
        return

    # --- 步骤 4: 转换为 DataFrame 并执行全局清洗 ---
    
    # 读取字段
    fields = [f.name for f in arcpy.ListFields(working_shp) if f.type not in ['Geometry', 'OID']]
    
    print("  正在读取数据到内存 (Pandas)...")
    data_rows = []
    with arcpy.da.SearchCursor(working_shp, ["OID@", "SHAPE@X", "SHAPE@Y"] + fields) as cursor:
        for row in cursor:
            data_rows.append(row)
            
    master_df = pd.DataFrame(data_rows, columns=["PointID", "Lon", "Lat"] + fields)
    
    print(f"\n>>> 正在执行全局数据清洗 (确保所有年份点位一致)...")
    initial_count = len(master_df)
    
    # 删除含有任何空值的行
    master_df.dropna(inplace=True)
    
    final_count = len(master_df)
    print(f"    初始点数: {initial_count}")
    print(f"    清洗后点数: {final_count}")
    print(f"    剔除无效点: {initial_count - final_count}")
    
    if final_count == 0:
        print("[错误] 所有点都被剔除了！这通常意味着某个图层完全没有覆盖研究区，或者全是NoData。")
        # 建议打印每一列的空值情况以便排查
        # print(master_df.isnull().sum())
        return

    # --- 步骤 5: 逐年拆分并导出 ---
    
    # 识别静态字段
    static_cols = ["PointID", "Lon", "Lat"]
    for col in fields:
        is_dynamic = False
        for yr in TARGET_YEARS:
            if col.endswith(f"_{get_year_suffix(yr)}"):
                is_dynamic = True
                break
        if not is_dynamic:
            static_cols.append(col)
            
    for year in TARGET_YEARS:
        ys = get_year_suffix(year)
        print(f"\n>>> 导出年份 {year} ...")
        
        current_cols = static_cols.copy()
        rename_dict = {}
        
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
        
        # 提取并重命名
        df_year = master_df[current_cols + year_dynamic_cols].copy()
        df_year.rename(columns=rename_dict, inplace=True)
        df_year["Year"] = year
        
        # [1] point_YYYY.csv
        p_out = os.path.join(OUTPUT_CSV_DIR, f"point_{year}.csv")
        df_year.to_csv(p_out, index=False, encoding='utf-8-sig')
        print(f"  [1] point_{year}.csv (共 {len(df_year)} 行)")
        
        # [2] wet_YYYY.csv
        if "LULC" in df_year.columns:
            df_wet = df_year[df_year["LULC"].isin(VALID_WET_CODES)]
            w_out = os.path.join(OUTPUT_CSV_DIR, f"wet_{year}.csv")
            df_wet.to_csv(w_out, index=False, encoding='utf-8-sig')
            print(f"  [2] wet_{year}.csv   (共 {len(df_wet)} 行)")

    # 任务完成后删除临时文件
    try:
        if arcpy.Exists(working_shp): arcpy.management.Delete(working_shp)
    except:
        pass
    print("\n所有任务完成！")

if __name__ == "__main__":
    main()
