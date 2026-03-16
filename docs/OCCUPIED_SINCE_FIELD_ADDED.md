# `occupied_since` 字段已添加到 Property JSON

## 更新摘要

已成功将 `occupied_since` 字段添加到 Property Quote JSON 配置中。

## 字段详情

- **字段名称**: `occupied_since`
- **位置**: 
  - `primary_dwelling_information.dwelling_information.occupied_since`
  - `secondary_dwelling_information.dwelling_information.occupied_since` (如果存在 secondary dwelling)
- **类型**: String (date)
- **格式**: `MM/DD/YYYY` (例如: "03/15/2018")
- **必填**: 是（所有 dwelling types: Homeowners, Tenants, Condominiums, Rented Dwelling）
- **描述**: 被保险人首次入住/开始居住在当前物业地址的日期

## 更新的文件

### 1. `config/caa_property_fields_config.json`

- ✅ 在 `primary_dwelling_information.dwelling_information` 中添加了 `occupied_since` 字段定义
- ✅ 在 `secondary_dwelling_information.dwelling_information` 中添加了 `occupied_since` 字段定义
- ✅ 更新了 `validation_checklist`，添加了 `occupied_since` 的验证项
- ✅ 更新了 `common_errors_to_avoid`，添加了关于 `occupied_since` 的错误提示

### 2. `utils/json_generator.py`

- ✅ 在 `_build_property_format_requirements` 方法中添加了 `occupied_since` 格式要求说明
- ✅ 更新了验证清单，添加了 `occupied_since` 的检查项
- ✅ 更新了常见错误列表，添加了关于 `occupied_since` 的错误提示

## 字段提取逻辑

AI 应该从 PDF 中查找以下关键词来提取 `occupied_since` 信息：

- "Date moved in"
- "Occupied since"
- "Residence date"
- "Date of occupancy"
- "When did you move in"
- "How long have you lived here"

## 重要注意事项

1. **日期格式**: 必须是 `MM/DD/YYYY` 格式（不是 `YYYY-MM-DD`）
2. **必填字段**: 所有 dwelling types 都需要此字段
3. **保费计算**: 此字段直接影响保费计算，必须准确提取
4. **不要猜测**: 如果 PDF 中找不到此信息，不要使用默认值或猜测
5. **Secondary Dwelling**: 如果存在 secondary dwelling，也需要添加此字段

## 示例 JSON

```json
{
  "primary_dwelling_information": {
    "dwelling_type": "Homeowners",
    "dwelling_information": {
      "occupied_since": "03/15/2018",
      "year_dwelling_built": "1995",
      ...
    },
    ...
  },
  "secondary_dwelling_information": {
    "dwelling_type": "Tenants",
    "dwelling_information": {
      "occupied_since": "01/10/2020",
      ...
    },
    ...
  }
}
```

## 验证检查清单

生成 JSON 后，请检查：

- [ ] `primary_dwelling_information.dwelling_information.occupied_since` 存在且格式为 MM/DD/YYYY
- [ ] 如果存在 secondary dwelling，`secondary_dwelling_information.dwelling_information.occupied_since` 也存在且格式为 MM/DD/YYYY
- [ ] 日期不在未来
- [ ] 日期合理（不早于 1900 年）

## 常见错误

1. ❌ 遗漏 `occupied_since` 字段
2. ❌ 使用 `YYYY-MM-DD` 格式（应该是 `MM/DD/YYYY`）
3. ❌ 使用默认值或猜测日期
4. ❌ 忘记为 secondary dwelling 添加此字段
