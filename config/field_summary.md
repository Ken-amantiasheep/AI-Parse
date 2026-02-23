# Intact Insurance JSON 输出格式 - 字段清单

## 字段统计
- **主要部分（Sections）**: 11个
- **总字段数**: 约70个字段
- **字段类型分布**:
  - `free_text`: 自由文本输入
  - `date`: 日期输入
  - `dropdown`: 下拉菜单
  - `radio`: 单选按钮（Yes/No）
  - `number`: 数字输入
  - `array`: 数组（多选）

---

## 1. applicant_information（申请人信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `last_name` | string | free_text | ✅ | 申请人姓氏 |
| `first_name` | string | free_text | ✅ | 申请人名字 |
| `gender` | string | dropdown | ❌ | 性别（Female, Male, X） |
| `date_of_birth` | string | date | ✅ | 出生日期（YYYY-MM-DD） |
| `language` | string | dropdown | ✅ | 首选语言（English, French） |
| `marital_status` | string | dropdown | ❌ | 婚姻状况（Divorced, Married, Single, Widow） |

---

## 2. address（地址信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `postal_code` | string | free_text | ❌ | 邮政编码（加拿大格式） |
| `full_address` | string | free_text | ✅ | 完整地址（如：164 Hawthorn Ave, Stouffville, ON） |

---

## 3. broker_information（经纪人信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `broker_number` | string | free_text | ✅ | 5位数字经纪人编号 |
| `edi_client_code` | string | free_text | ❌ | EDI客户端代码 |

---

## 4. term（期限信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `policy_effective_date` | string | date | ✅ | 保单生效日期（DD-MM-YYYY） |

---

## 5. risk（风险信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `risk_type` | string | dropdown | ❌ | 风险类型/车辆类型（ATV, ANT, CLA, MCY, MHO, PPV, SNO, PPT） |
| `serial_number` | string | free_text | ❌ | 17位序列号 |
| `condition_when_purchased_or_leased` | string | dropdown | ✅ | 购买或租赁时的状况（New, Used, Demo Less than 5,000 KM, Demo More than or Equal to 5,000 KM） |
| `date_of_purchase_or_lease` | string | date | ❌ | 购买或租赁日期（YYYY-MM-DD） |
| `winter_tires` | string | radio | ❌ | 是否有冬季轮胎（Yes, No） |
| `unrepaired_damage` | string | radio | ✅ | 是否有未修复的损坏（Yes, No） |
| `vehicle_rebuilt` | string | radio | ✅ | 车辆是否重建（Yes, No） |
| `vehicle_photos_received` | string | radio | ❌ | 是否收到车辆照片（Yes, No） |
| `vehicle_modified_or_accessories` | string | radio | ✅ | 车辆是否改装或有配件（Yes, No） |

---

## 6. interest（利息/融资信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `has_loan` | string | radio | ❌ | 是否有贷款（Yes, No） |
| `type_of_interest` | string | dropdown | ✅ | 利息类型（Lessor, Lienholder） |
| `client_selection_type` | string | radio | ✅ | 客户选择类型（Create a new party, Select from corporate list） |
| `company_name` | string | dropdown | ✅ | 公司名称（从企业列表中选择，共34个选项） |

---

## 7. driver（驾驶员信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `student` | string | radio | ❌ | 是否为学生（Yes, No） |
| `driver_training_certificate` | string | radio | ✅ | 是否有驾驶员培训证书（Yes, No） |
| `licence_number` | string | free_text | ❌ | 驾照号码 |
| `licence_class` | string | dropdown | ✅ | 驾照类别（A, B, C, D, E, F, G, G1, G2, M, M1, M2） |
| `g_class_date_licensed` | string | date | ✅ | G类驾照日期（DD-MM-YYYY） |
| `g2_class_date_licensed` | string | date | ✅ | G2类驾照日期（DD-MM-YYYY） |
| `g1_class_date_licensed` | string | date | ✅ | G1类驾照日期（DD-MM-YYYY） |
| `request_date_time` | string | date | ✅ | 请求日期/时间（DD-MM-YYYY） |
| `insurance_history_report_status` | string | dropdown | ✅ | 保险历史报告状态（Not Found, Not Ordered, Received, Ordered - Pending） |
| `insurance_history_report_request_date` | string | date | ✅ | 保险历史报告请求日期（DD-MM-YYYY） |
| `convictions` | string | radio | ✅ | 是否有定罪（Yes, No） |
| `licence_suspensions` | string | radio | ✅ | 是否有驾照暂停（Yes, No） |
| `lapse_in_insurance` | string | radio | ✅ | 是否有保险中断（Yes, No） |
| `insured_without_interruption_since` | string | date | ✅ | 无中断保险自（YYYY-MM） |
| `risk_type` | string | dropdown | ✅ | 风险类型/车辆类型（All terrain Vehicle, Antique, Classic, Motorcycle, Motorhome, Private Passenger Vehicle, Snowmobile, Trailer） |
| `previous_insurer` | string | dropdown | ✅ | 前保险公司（共200+个选项） |
| `expiry_date` | string | date | ✅ | 到期日期（DD-MM-YYYY） |
| `previous_insurer_policy_number` | string | free_text | ❌ | 前保险公司保单号 |
| `number_of_years_with_previous_insurer` | number | free_text | ✅ | 与前保险公司合作的年数 |

---

## 8. assignment（用途信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `type_of_use` | string | dropdown | ✅ | 使用类型（Business, Farmer Personal Use, Pleasure, Vocational） |
| `km_toward_work` | number | free_text | ✅ | 上班行驶公里数 |
| `annual_km` | number | free_text | ✅ | 年行驶公里数 |
| `annual_business_km` | number | free_text | ✅ | 年业务行驶公里数 |
| `automobile_rented_or_leased_to_others` | string | radio | ✅ | 是否出租或租赁给他人（Yes, No） |
| `automobile_used_to_carry_passengers_for_compensation_or_hire` | string | radio | ✅ | 是否用于有偿载客（Yes, No） |
| `automobile_carry_explosives_or_radioactive_materials` | string | radio | ✅ | 是否运输爆炸物或放射性材料（Yes, No） |

---

## 9. claim（理赔信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `has_claim` | string | radio | ✅ | 是否有理赔（Yes, No） |
| `date_of_loss` | string | date | ✅ | 损失日期（DD-MM-YYYY） |
| `at_fault` | string | radio | ✅ | 是否过错（Yes, No） |
| `cause_of_loss` | string | dropdown | ✅ | 损失原因（共40个选项） |
| `total_amount_paid` | number | free_text | ✅ | 总支付金额（货币） |
| `coverage` | string | dropdown | ✅ | 保险类型（Accident Benefits, Collision, Comprehensive or Specified Perils, DCPD, Third Party Liability） |
| `assigned_vehicle` | string | dropdown | ✅ | 指定车辆 |

---

## 10. coverages（保险范围）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `limit` | number | free_text | ✅ | 限额金额（货币） |
| `accident_benefits_standard_benefits` | array | dropdown | ❌ | 意外保险标准福利（多选，共7个选项） |
| `dcpd_deductible` | number | dropdown | ✅ | DCPD免赔额（0, 300, 500） |
| `all_perils_or_collision_or_upset` | string | dropdown | ❌ | 全险或碰撞或翻车（Collision or Upset, All Perils） |
| `all_perils_or_collision_or_upset_deductible` | number | free_text | ❌ | 全险或碰撞或翻车免赔额 |
| `specified_perils_or_comprehensive` | string | dropdown | ❌ | 指定风险或综合险（Comprehensive, Specified Perils） |
| `specified_perils_or_comprehensive_deductible` | number | free_text | ❌ | 指定风险或综合险免赔额 |
| `responsible_driver_guarantee` | string | radio | ✅ | 负责任的驾驶员保证（Yes, No） |
| `claims_advantage` | string | radio | ✅ | 理赔优势（Yes, No） |
| `opcf_44r_family_protection_endorsement` | string | radio | ✅ | OPCF 44R - 家庭保护批单（Yes, No） |
| `section_optional_coverages` | array | dropdown | ❌ | 部分可选保险（多选，共15个选项） |

---

## 11. insureds（被保险人信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `automobile_insurance_cancelled_or_refused_in_last_3_years` | string | radio | ✅ | 过去3年是否取消或拒绝汽车保险（Yes, No） |
| `ubi_consent` | string | dropdown | ❌ | UBI同意（No, Not Requested, Yes） |

---

## 12. additional_info（附加信息）
**必填**: ✅

| 字段名 | 类型 | 模式 | 必填 | 描述 |
|--------|------|------|------|------|
| `named_insureds_have_additional_policies_with_intact_financial_corporation` | string | radio | ✅ | 指定被保险人是否在Intact Financial Corporation有额外保单（Yes, No） |

---

## 字段模式说明

### free_text（自由文本）
- 用户可自由输入文本
- 示例：姓名、地址、保单号等

### date（日期）
- 日期格式输入
- 注意：不同字段可能使用不同日期格式（YYYY-MM-DD 或 DD-MM-YYYY）

### dropdown（下拉菜单）
- 从预定义选项中选择
- 选项数量从2个到200+个不等

### radio（单选按钮）
- 通常为 Yes/No 选项
- 用于布尔类型的问题

### number（数字）
- 数字类型输入
- 用于金额、公里数、年数等

### array（数组）
- 多选字段
- 可选择一个或多个选项
- 目前用于：`accident_benefits_standard_benefits` 和 `section_optional_coverages`

---

## 注意事项

1. **字段顺序很重要**：字段的顺序决定了自动填写系统的填写顺序
2. **日期格式**：注意不同字段使用不同的日期格式
   - YYYY-MM-DD：`date_of_birth`, `date_of_purchase_or_lease`, `insured_without_interruption_since`
   - DD-MM-YYYY：`policy_effective_date`, `g_class_date_licensed`, `expiry_date` 等
   - YYYY-MM：`insured_without_interruption_since`
3. **必填字段**：标记为 `required: true` 的字段必须提供值
4. **多选字段**：`accident_benefits_standard_benefits` 和 `section_optional_coverages` 支持多选
5. **大型下拉菜单**：`previous_insurer` 和 `company_name` 包含大量选项，需要精确匹配
