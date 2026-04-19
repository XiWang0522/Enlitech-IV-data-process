# Solar Cell IV CSV Processor

一个可直接运行的 Python 工具，用来处理太阳能电池仪器导出的特殊 IV CSV。

## 主要能力

- 解析特殊 CSV（上半区横向 IV 曲线 + 中间分隔 + 下半区参数汇总）
- 自动提取 `Condition`（`Name` 中 `.` 前的部分）
- IQR 异常值剔除（按 `Condition x 参数`）
- 生成 6 个参数箱线图（叠加散点）
- 输出每个 `Condition` 的最佳 PCE 记录
- 绘制最佳 PCE 的 IV 对比图
- 交互式流程：
  - 选择 CSV 文件
  - 弹出输入窗口设置 `V/J` 轴范围（可留空自动）
  - 处理完成后可继续选择下一份 CSV

## 环境要求

- Python 3.9+
- `tkinter`（通常随 Python 自带）
- 依赖见 `requirements.txt`

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

### 交互模式（推荐）

```bash
cd /Users/xiwang/Desktop/project1
source .venv/bin/activate
python iv_processor.py
```

流程：
1. 文件选择框选 CSV
2. 弹出窗口输入 `vmin/vmax/jmin/jmax`（留空=自动）
3. 自动处理并导出
4. 询问是否继续选择下一份 CSV

### 只处理一次并退出

```bash
python iv_processor.py --single
```

### 命令行指定输入文件

```bash
python iv_processor.py --input "/absolute/path/to/your.csv"
```

### 命令行固定 IV 坐标范围

```bash
python iv_processor.py --input "/absolute/path/to/your.csv" --vmin -0.2 --vmax 1.2 --jmin -25 --jmax 120
```

## 输出目录

输入 `xxx.csv` 时，输出到同目录 `xxx/` 文件夹中：

- `summary_raw.csv`
- `summary_cleaned.csv`
- `outlier_report.csv`
- `best_pce_by_condition.csv`
- `boxplot_Voc.png`
- `boxplot_PCE.png`
- `boxplot_Jsc.png`
- `boxplot_FF.png`
- `boxplot_Rs.png`
- `boxplot_Rsh.png`
- `best_pce_iv_comparison.png`

## 兼容格式说明

支持分隔行：
- `==========`
- `==========,,,,`（后面带逗号也可）

## 仓库文件

- `iv_processor.py` 主程序
- `requirements.txt` 依赖列表
- `README.md` 使用说明
