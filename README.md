# Solar Cell IV CSV Processor

用于处理仪器导出的太阳能电池 IV 测试 CSV（特殊横向多区块格式）的 Python 脚本。  
脚本会自动解析参数汇总、提取 IV 曲线、做分组统计与异常值剔除，并输出图表与结果表。

## 功能

- 通过文件选择框选择 CSV（支持连续处理多个文件）
- 自动解析特殊格式 CSV：
  - 上半部分：多条 IV 曲线横向并排
  - 中间分隔：`==========`（支持尾随逗号）
  - 下半部分：参数汇总表
- 从 `Name` 自动提取 `Condition`（点号 `.` 前部分）
- 按 `Condition` 对以下参数绘制箱型图（叠加散点）：
  - `Voc (V)`
  - `Efficiency (%)`（PCE）
  - `Jsc (mA/cm^2)`
  - `Fill Factor (%)`（FF）
  - `Rs (ohm)`
  - `Rsh (ohm)`
- 异常值剔除（IQR，按每个 Condition + 每个参数）
- 导出每个 Condition 的最佳 PCE 记录，并绘制最佳 IV 对比图
- 支持自定义最佳 IV 图的 `V/J` 坐标范围

## 环境要求

- macOS / Linux / Windows
- Python 3.9+
- 依赖：`pandas`, `numpy`, `matplotlib`, `seaborn`
- `tkinter`（用于文件选择弹窗，通常随 Python 自带）

## 安装

在项目目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

### 1) 交互选择文件（推荐）

```bash
cd /Users/xiwang/Desktop/project1
source .venv/bin/activate
python iv_processor.py
```

运行后会弹出文件选择框；每处理完一个文件，会弹窗询问是否继续选择下一个 CSV。

### 2) 只处理一个文件后退出

```bash
python iv_processor.py --single
```

### 3) 直接指定输入文件

```bash
python iv_processor.py --input "/absolute/path/to/your.csv"
```

## IV 图坐标范围设置

### 方式 A：命令行直接指定

```bash
python iv_processor.py --input "/absolute/path/to/your.csv" --vmin -0.2 --vmax 1.2 --jmin -25 --jmax 120
```

### 方式 B：运行时交互输入

```bash
python iv_processor.py --ask-limits
```

或：

```bash
python iv_processor.py --input "/absolute/path/to/your.csv" --ask-limits
```

不设置时默认自动范围。

## 输出结果

对于输入文件 `xxx.csv`，输出会保存到同目录下的文件夹 `xxx/` 中，例如：

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

## 输入格式说明（关键）

脚本面向仪器导出的特殊 CSV，要求：

1. 上半部分是横向并排的 IV 数据块  
2. 中间存在分隔行（如 `==========` 或 `==========,,,,`）  
3. 下半部分有参数表头（包含 `Name`, `Isc (mA)`, `Voc (V)`, `Efficiency (%)` 等列）

## 异常值规则

- 采用 IQR 方法：
  - `lower = Q1 - 1.5 * IQR`
  - `upper = Q3 + 1.5 * IQR`
- 超出范围视为异常值并剔除（用于清洗后统计和绘图）
- 原始表始终保留
- 样本太少或 IQR 不稳定时，会跳过该组剔除

## 常见问题

### 1) 报错找不到 `==========`

说明输入 CSV 可能不是该仪器特殊格式，或文件结构与预期差异较大。

### 2) 有 `Duplicate IV block` 警告

表示文件里出现同名曲线多次，程序默认保留第一次出现的曲线用于 IV 对比图。

### 3) tkinter 弹窗无法打开

可改用命令行 `--input` 方式指定 CSV 路径。

## 项目文件

- 主脚本：`iv_processor.py`
- 依赖清单：`requirements.txt`

## License

MIT (可按需修改)
