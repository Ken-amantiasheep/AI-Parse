# JSON 格式验证和修复工具使用说明

## 概述

`json_format_validator.py` 是一个用于验证和修复 Property Quote JSON 格式问题的工具。它可以自动检测并修复常见的格式错误。

## 功能

该工具可以自动修复以下格式问题：

1. **地址格式**：确保 street name 和 street type 之间有空格
2. **省份格式**：将完整省份名称转换为2字母缩写
3. **电话格式**：去除括号，使用连字符格式
4. **prev_insurance.end_date**：将字符串格式转换为对象格式
5. **coverages_information**：将对象格式转换为数组格式
6. **claims**：将 null 转换为空数组
7. **名字格式**：确保至少两个单词，最后一个单词至少2个字符

## 使用方法

### 命令行使用

```bash
# 修复 JSON 文件（覆盖原文件）
python utils/json_format_validator.py input.json

# 修复 JSON 文件（保存到新文件）
python utils/json_format_validator.py input.json output.json
```

### Python 代码中使用

```python
from utils.json_format_validator import PropertyJSONFormatValidator, validate_and_fix_json_file

# 方法1：直接使用验证器类
validator = PropertyJSONFormatValidator()
fixed_data, issues, fixes = validator.validate_and_fix(data)

# 方法2：使用文件处理函数
fixed_data, issues, fixes = validate_and_fix_json_file("input.json", "output.json")

# 查看结果
print(f"发现 {len(issues)} 个问题")
for issue in issues:
    print(f"  - {issue}")

print(f"应用了 {len(fixes)} 个修复")
for fix in fixes:
    print(f"  ✓ {fix}")
```

## 修复示例

### 示例 1：地址格式修复

**修复前**：
```json
{
  "application_info": {
    "address": {
      "address": "6 BlueberryDr."
    }
  }
}
```

**修复后**：
```json
{
  "application_info": {
    "address": {
      "address": "6 Blueberry Dr."
    }
  }
}
```

### 示例 2：省份格式修复

**修复前**：
```json
{
  "application_info": {
    "address": {
      "province": "Ontario"
    }
  }
}
```

**修复后**：
```json
{
  "application_info": {
    "address": {
      "province": "ON"
    }
  }
}
```

### 示例 3：prev_insurance.end_date 格式修复

**修复前**：
```json
{
  "application_info": {
    "prev_insurance": {
      "end_date": "2026-03-09"
    }
  }
}
```

**修复后**：
```json
{
  "application_info": {
    "prev_insurance": {
      "end_date": {
        "month": "03",
        "day": "09",
        "year": "2026"
      }
    }
  }
}
```

### 示例 4：coverages_information 格式修复

**修复前**：
```json
{
  "coverages_information": {
    "Residence": {...},
    "Contents": {...}
  }
}
```

**修复后**：
```json
{
  "coverages_information": [
    {"Residence": {...}},
    {"Contents": {...}}
  ]
}
```

## 输出说明

工具运行后会显示：

1. **Issues Found**：发现的所有格式问题
2. **Fixes Applied**：应用的修复操作

示例输出：
```
============================================================
Issues Found: 3
============================================================
  - application_info.address.address: Missing space before street type ('6 BlueberryDr.' -> '6 Blueberry Dr.')
  - application_info.address.province: Full name used ('Ontario' -> 'ON')
  - application_info.prev_insurance.end_date: String format ('2026-03-09' -> object format)

============================================================
Fixes Applied: 3
============================================================
  ✓ Fixed address format: added space before 'Dr'
  ✓ Fixed province format: converted 'Ontario' to 'ON'
  ✓ Fixed prev_insurance.end_date: converted string to object format

Fixed JSON saved to: output.json
```

## 注意事项

1. **备份原文件**：建议在修复前备份原始 JSON 文件
2. **验证结果**：修复后请检查 JSON 文件，确保修复正确
3. **手动检查**：某些复杂情况可能需要手动检查和处理

## 集成到现有代码

可以在 `json_generator.py` 的 `_normalize_property_structure` 方法中集成此验证器：

```python
from utils.json_format_validator import PropertyJSONFormatValidator

def _normalize_property_structure(self, data: Dict) -> Dict:
    """Normalize property JSON structure"""
    # ... existing code ...
    
    # Add format validation and fixing
    validator = PropertyJSONFormatValidator()
    data, issues, fixes = validator.validate_and_fix(data)
    
    if issues:
        print(f"[INFO] Found {len(issues)} format issues, applied {len(fixes)} fixes")
    
    return data
```
