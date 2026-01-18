import pandas as pd
import numpy as np
import xgboost as xgb
import shap
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.patches as mpatches
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score
import glob
import os
import re
import gc
import sys
import time

# [cite_start]尝试导入 geoshapley [cite: 5]
try:
    import geoshapley
    from geoshapley import GeoShapleyExplainer
except ImportError:
    print("提示: 未检测到 geoshapley，请先安装: pip install geoshapley")

# 绘图设置
plt.style.use('seaborn-v0_8-whitegrid')
fonts = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['font.sans-serif'] = fonts
plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# 0. 用户配置区 (User Configuration)
# ==========================================
INPUT_DIR = r"E:\paper1\excel\point\2"
OUTPUT_DIR = r"E:\paper1\result\final_plots_styled"
WETLAND_CODES = [1, 2, 3, 4, 5]

# --- 【核心控制开关】 ---
CONFIG = {
    "USE_FULL_DATA": False,
    "SHAP_SAMPLE_SIZE": 200,
    "GEOSHAP_SAMPLE_SIZE": 100,
    # 背景数据保持 50 以防内存溢出
    "GEOSHAP_BG_SIZE": 5,
    "EXCLUDE_GEO_IN_IMPORTANCE": True
}

os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"结果将保存至: {OUTPUT_DIR}")
print(f"当前配置: {CONFIG}")

# ==========================================
# 1. 获取文件列表
# ==========================================
file_pattern = os.path.join(INPUT_DIR, "point_*.csv")
all_files = glob.glob(file_pattern)

if not all_files:
    raise FileNotFoundError(f"在 {INPUT_DIR} 未找到 point_*.csv 文件。")

print(f"共发现 {len(all_files)} 个年份的数据文件，准备开始分析...")

# ==========================================
# 2. 逐年循环分析
# ==========================================
for filepath in all_files:
    gc.collect()

    filename = os.path.basename(filepath)
    match = re.search(r'\d{4}', filename)
    year = match.group(0) if match else "UnknownYear"

    print(f"\n{'=' * 50}")
    print(f"正在处理年份: {year}")
    print(f"{'=' * 50}")

    # [cite_start]记录每个年份处理的开始时间 [cite: 5]
    start_time = time.time()
    formatted_start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
    print(f"开始时间: {formatted_start_time}")

    try:
        # --- 2.1 数据准备 ---
        data = pd.read_csv(filepath)
        data = data[data['LULC'] != -9999].copy()
        data = data.dropna(subset=['LULC', 'Lat', 'Lon'])

        # 构建目标 (0/1)
        data['Is_Wetland'] = data['LULC'].isin(WETLAND_CODES).astype(int)
        y = data['Is_Wetland']

        if y.sum() == 0 or (len(y) - y.sum()) == 0:
            print(f"[{year}] 样本单一，跳过。")
            continue

        # 特征筛选
        ignore_cols = [
            'PointID', 'CID', 'grid_code', 'Join_Count', 'TARGET_FID',
            'MERGE1_', 'MERGE1_ID', 'CHINAPERM', 'REGION', 'AREA', 'PERIMETER',
            'LULC', 'Is_Wetland', 'geom', 'soil_type', 'Year'
        ]
        feature_names = [c for c in data.columns if c not in ignore_cols and c not in ['Lat', 'Lon']]

        X = data[feature_names].copy()
        X = X.fillna(X.mean())

        # 标准化
        scaler = StandardScaler()
        X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=feature_names)
        df_features = X_scaled.copy()

        # 拼接坐标
        df_features['LAT'] = data['Lat'].values
        df_features['LON'] = data['Lon'].values

        # =============================================================================
        # 3. 训练 XGBoost 模型 (修改为回归模型)
        # =============================================================================
        print("\n--- 步骤 2: 正在训练 XGBoost 模型 ---")

        # 划分数据集 (根据提供的代码片段修改)
        X_train, X_test, y_train, y_test = train_test_split(
            df_features, y,
            test_size=0.2,
            random_state=42
        )

        # [cite_start]初始化 XGBoost 回归器 [cite: 5]
        model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            objective='reg:squarederror',
            random_state=42,
            n_jobs=-1  # 保持多核并行以加快速度
        )

        # 训练模型
        model.fit(X_train, y_train)
        print("模型训练完成。")

        # 评估 (回归模型使用 R2 score，不能用 Accuracy)
        score = model.score(X_test, y_test)
        print(f"[{year}] 模型 R2 Score: {score:.4f}")

        # =============================================================================
        # 4. 特征重要性分析
        # =============================================================================
        print(f"[{year}] 绘制特征重要性图...")

        importances = model.feature_importances_
        current_feat_names = X_train.columns.tolist()
        df_importance = pd.DataFrame({'feature': current_feat_names, 'importance': importances})

        if CONFIG["EXCLUDE_GEO_IN_IMPORTANCE"]:
            df_importance = df_importance[~df_importance['feature'].isin(['LAT', 'LON'])]

        df_importance = df_importance.sort_values(by='importance', ascending=True)

        fig, ax = plt.subplots(figsize=(12, 10))
        df_plot_imp = df_importance.tail(25)

        bars = ax.barh(df_plot_imp['feature'], df_plot_imp['importance'], color='#d62828')
        ax.set_title(f'Feature importance values ({year})', fontsize=18, pad=20)
        ax.set_ylabel('Variable', fontsize=16)
        ax.tick_params(axis='both', labelsize=12)

        for bar in bars:
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height() / 2, f' {width:.3f}', va='center', fontsize=10)
        ax.set_xlim(right=ax.get_xlim()[1] * 1.15)

        # Donut Chart
        donut_features = df_importance['feature'].tail(5).tolist()[::-1]
        df_donut = df_importance[df_importance['feature'].isin(donut_features)].copy()

        if not df_donut.empty and df_donut['importance'].sum() > 0:
            df_donut['feature'] = pd.Categorical(df_donut['feature'], categories=donut_features, ordered=True)
            df_donut = df_donut.sort_values('feature')
            total_val = df_donut['importance'].sum()
            percents = df_donut['importance'] / total_val * 100

            ax_inset = fig.add_axes([0.45, 0.15, 0.3, 0.3])
            colors = matplotlib.colormaps.get('tab10').colors
            wedges, _ = ax_inset.pie(percents, colors=colors[:len(df_donut)], startangle=90,
                                     wedgeprops=dict(width=0.45, edgecolor='w'))

            ratio = df_donut['importance'].sum() / df_importance['importance'].sum()
            ax_inset.text(0, 0, f'Total importance\nof top 5\n{ratio:.2%}', ha='center', va='center', fontsize=9)

            for i, p in enumerate(wedges):
                ang = (p.theta2 - p.theta1) / 2. + p.theta1
                y = np.sin(np.deg2rad(ang))
                x = np.cos(np.deg2rad(ang))
                if percents.iloc[i] > 0:
                    ax_inset.annotate(f'{percents.iloc[i]:.1f}%', xy=(x, y), xytext=(1.2 * x, 1.2 * y),
                                      ha='center', fontsize=10, weight='bold')
            ax_inset.legend(wedges, df_donut['feature'], loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)

        save_path = os.path.join(OUTPUT_DIR, f"Feature_Importance_{year}.jpg")
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"已保存: {save_path}")

        # =============================================================================
        # 5. SHAP 分析
        # =============================================================================
        print(f"[{year}] SHAP 分析...")
        explainer = shap.TreeExplainer(model)

        if CONFIG["USE_FULL_DATA"]:
            X_shap = df_features
            print(f"  使用全量数据 ({len(X_shap)} 行)...")
        else:
            sample_n = min(CONFIG["SHAP_SAMPLE_SIZE"], len(df_features))
            X_shap = df_features.sample(sample_n, random_state=42)
            print(f"  使用抽样数据 ({len(X_shap)} 行)...")

        shap_values = explainer(X_shap)

        cols = X_shap.columns
        non_geo_cols = [c for c in cols if c not in ['LAT', 'LON']]

        plt.figure(figsize=(10, 8))
        shap.summary_plot(shap_values[:, non_geo_cols], X_shap[non_geo_cols],
                          plot_type="dot", cmap="RdYlBu", show=False)
        plt.title(f"SHAP Feature Importance Summary ({year})", fontsize=16)
        plt.savefig(os.path.join(OUTPUT_DIR, f"SHAP_Summary_{year}.jpg"), dpi=300, bbox_inches='tight')
        plt.close()
        print(f"已保存: SHAP_Summary_{year}.jpg")

        # =============================================================================
        # 6. GeoShapley 分析
        # =============================================================================
        print(f"[{year}] GeoShapley 分析 (全量模式，可能较慢，请耐心等待)...")

        bg_size = CONFIG["GEOSHAP_BG_SIZE"]
        bg_data = X_train.sample(min(bg_size, len(X_train)), random_state=42)

        geoshap_explainer = GeoShapleyExplainer(model.predict, bg_data)

        try:
            if CONFIG["USE_FULL_DATA"]:
                data_to_explain = df_features
                print(f"  正在解释全量数据 ({len(data_to_explain)} 行)...")
            else:
                sample_n = min(CONFIG["GEOSHAP_SAMPLE_SIZE"], len(df_features))
                data_to_explain = df_features.sample(sample_n, random_state=42)
                print(f"  正在解释抽样数据 ({len(data_to_explain)} 行)...")

            # CPU模式，多核并行
            geoshapley_results = geoshap_explainer.explain(data_to_explain, n_jobs=-1)

            # --- 发散条形图 ---
            print(f"[{year}] 绘制 GeoShapley Diverging Bar...")
            non_spatial_feats = [f for f in current_feat_names if f not in ['LAT', 'LON']]

            mean_primary = pd.Series(geoshapley_results.primary.mean(axis=0), index=non_spatial_feats)
            mean_interaction = pd.Series(geoshapley_results.geo_intera.mean(axis=0),
                                         index=[f'{f} x GEO' for f in non_spatial_feats])
            mean_spatial = pd.Series(geoshapley_results.geo.mean(), index=['GEO'])

            df_plot = pd.concat([mean_primary, mean_interaction, mean_spatial]).reset_index()
            df_plot.columns = ['Variable', 'Value']

            df_plot['AbsValue'] = df_plot['Value'].abs()
            df_plot_top = df_plot.sort_values('AbsValue', ascending=False).head(15).sort_values('Value', ascending=True)
            df_plot_top['Color'] = ['#e69f00' if x >= 0 else '#0072b2' for x in df_plot_top['Value']]

            fig3, ax3 = plt.subplots(figsize=(10, 8))
            ax3.barh(df_plot_top['Variable'], df_plot_top['Value'], color=df_plot_top['Color'])

            for _, row in df_plot_top.iterrows():
                val = row['Value']
                offset = max(df_plot_top['AbsValue']) * 0.02 * (1 if val > 0 else -1)
                ax3.text(val + offset, row['Variable'], f'{val:.3f}', ha='left' if val > 0 else 'right', va='center',
                         fontsize=9)

            ax3.axvline(0, color='black', lw=0.8)
            ax3.set_title(f'Geoshapley values for XGB ({year})', fontsize=16)
            ax3.set_xlim(-df_plot_top['AbsValue'].max() * 1.3, df_plot_top['AbsValue'].max() * 1.3)
            plt.savefig(os.path.join(OUTPUT_DIR, f"GeoShapley_DivergingBar_{year}.jpg"), dpi=300, bbox_inches='tight')
            plt.close()

            # Beeswarm
            print(f"[{year}] 绘制 GeoShapley Beeswarm...")
            plt.figure(figsize=(10, 8))
            geoshapley_results.summary_plot(include_interaction=True, cmap='RdYlBu')
            plt.title(f"GeoShapley Value Summary Plot ({year})", fontsize=16)
            plt.savefig(os.path.join(OUTPUT_DIR, f"GeoShapley_Beeswarm_{year}.jpg"), dpi=300, bbox_inches='tight')
            plt.close()

        except Exception as e:
            print(f"[{year}] GeoShapley 计算失败: {e}")
            import traceback

            traceback.print_exc()

        # [cite_start]打印耗时 [cite: 5]
        elapsed_seconds = time.time() - start_time
        elapsed_minutes = elapsed_seconds / 60
        elapsed_hours = elapsed_seconds / 3600
        print(f"[{year}] 处理完成，耗时: {elapsed_seconds:.2f} 秒 ({elapsed_minutes:.2f} 分钟)")

    except Exception as e:
        print(f"处理年份 {year} 时出错: {e}")
        continue

print(f"\n{'=' * 50}")
print(f"所有任务完成！")
