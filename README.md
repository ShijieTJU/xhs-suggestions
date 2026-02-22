# xhs-suggestions

小红书搜索候选词采集工具，使用 Python + Playwright 自动化控制浏览器，采集搜索框输入关键词时弹出的联想候选词。

## 功能

- 扫码登录一次，登录状态持久化，后续运行无需重复登录
- 支持批量关键词（文件 / 命令行参数两种方式）
- 结果同时保存为 JSON 和 CSV
- 逐字符模拟人工输入，降低被检测风险

## 环境要求

- Python 3.9+
- Playwright

## 安装

```bash
# 1. 创建并激活 conda 环境（推荐）
conda create -n xhs_spider python=3.9 -y
conda activate xhs_spider

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright Chromium 浏览器
playwright install chromium
```

## 使用方法

### 第一步：登录（只需执行一次）

```bash
python xhs_suggestions.py --login
```

浏览器自动打开小红书首页，扫码登录后脚本自动保存登录状态到 `auth_state.json` 并关闭浏览器。

### 第二步：采集候选词

```bash
# 从 keywords.txt 读取关键词（每行一个）
python xhs_suggestions.py

# 直接指定关键词
python xhs_suggestions.py -k 宠物冻干 猫粮测评 狗粮推荐

# 指定关键词文件
python xhs_suggestions.py -f my_keywords.txt

# 无头模式（不显示浏览器窗口）
python xhs_suggestions.py --headless -k 宠物冻干
```

### 登录状态失效时

重新运行 `--login` 即可，会覆盖旧的登录状态：

```bash
python xhs_suggestions.py --login
```

## 关键词文件格式

`keywords.txt` 每行一个关键词，`#` 开头为注释行：

```
# 宠物类
宠物冻干
猫粮测评
狗粮推荐
```

## 输出格式

结果保存在 `output/` 目录，文件名包含时间戳：

- `suggestions_20260222_195217.json`
- `suggestions_20260222_195217.csv`

CSV 格式：

| 关键词 | 候选词序号 | 候选词 |
|--------|-----------|--------|
| 宠物冻干 | 1 | 宠物冻干推荐 |
| 宠物冻干 | 2 | 宠物冻干自制 |

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--login` | 登录模式，保存登录状态后退出 | - |
| `--auth` | 登录状态文件路径 | `auth_state.json` |
| `-f, --file` | 关键词文件路径 | `keywords.txt` |
| `-k, --keywords` | 直接指定关键词列表 | - |
| `--headless` | 无头模式（需已有登录状态） | `False` |
| `-o, --output` | 输出目录 | `output/` |

## 注意事项

- `auth_state.json` 包含登录 Cookie，已加入 `.gitignore`，请勿上传
- 本工具仅供学习研究，请遵守小红书用户协议及相关法律法规

## License

MIT
