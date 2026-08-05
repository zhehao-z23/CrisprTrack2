# Google Drive 归档契约（DSB v5）

状态：生效  
适用对象：OligoLiveFish-ML-ZZH v5 的 DSB 输入、分析产物与审计记录  
Drive 根目录：`G:\共享云端硬盘\LivevFISH data\2-25-26-dsb_E\more`

## 1. 目的与边界

本契约规定如何把 Sherlock 上的 v5 分析产物安全归档到 Google Drive，使结果可在本地直接审阅、可与实验人员共享，并且保持从原始 ND2、输入 TIFF 到最终轨迹和报告的完整可追溯性。

本契约不授权修改、移动、重命名或删除原始实验数据。任何自动化迁移都必须是 copy-only；禁止对原始目录使用会传播删除或覆盖的 `sync`、`move`、`delete`、`purge` 等操作。

## 2. 原始数据是只读来源

以下目录是原始数据来源，必须视为只读：

```text
G:\共享云端硬盘\LivevFISH data\2-25-26-dsb_E\more\a
```

对应 rclone 路径为：

```text
zhangzh:2-25-26-dsb_E/more/a
```

约束如下：

1. 不得在 `more/a` 内写入 v5 结果、补充 metadata、校验文件或说明文档。
2. 不得修改原始 ND2、TIFF、ROI、JSON、CSV、时间戳或文件属性。
3. 不得“清理”原目录中已有的测试文件、人工副本或旧版结果；这些内容属于来源现场的一部分。
4. 迁移前后若执行来源核查，只允许读取文件名、大小、时间戳和校验值。

## 3. literal 命名原则

所有映射和归档必须保留来源中的字面名称（literal name），不得根据编号、时间点或推测规则重新生成名称。

必须原样保留：

- FOV 目录名，例如 `fov4 2h`、`fov15 3h_1s`、`fov17_3h_forZH`；
- ND2 文件名，例如 `LiveFISH DSB.nd2`、`LiveFISH DSB003.nd2`、`LiveFISH 3h_DSB016.nd2`；
- cell/crop 名称和编号，包括空格、下划线、`.nd2`、零填充方式及大小写；
- 已生成的 TIFF、轨迹、mask、manifest 和报告文件名。

禁止：

- 将空格统一替换为下划线；
- 自动把 `fov4 2h` 改成 `fov4_2h`；
- 自动补齐或重排 DSB 编号；
- 在没有显式映射证据时，仅凭相似文件名合并两个样本；
- 把 `cell2 - Copy (...)` 等旧测试副本当作新的规范命名模板。

## 4. 新结果的唯一归档位置

v5 DSB 结果只能写入：

```text
G:\共享云端硬盘\LivevFISH data\2-25-26-dsb_E\more\zhehao\dsb_v5_results\a\<literal FOV>\
```

对应 rclone 路径为：

```text
zhangzh:2-25-26-dsb_E/more/zhehao/dsb_v5_results/a/<literal FOV>/
```

建议的归档骨架为：

```text
zhehao/
├── code_snapshots/
└── dsb_v5_results/
    └── a/
        ├── SOURCE_ND2_MAP.tsv
        ├── ARCHIVE_MANIFEST.tsv
        ├── ARCHIVE_AUDIT/
        ├── unmapped_review/
        └── <literal FOV>/
            ├── <literal TIFF/cell files and metadata>
            ├── trajectories/
            ├── qc/
            ├── manifests/
            └── audit/
```

具体流水线若已经形成稳定的 cell 结果子目录，可以保留其内部层级；但 `<literal FOV>` 这一层和所有输入/结果文件的 literal 名称不得改变。不同运行必须通过明确的 run ID、版本 manifest 或独立子目录区分，不得静默覆盖已有归档。

## 5. ND2 策略与 `SOURCE_ND2_MAP.tsv`

ND2 默认不复制到 `zhehao`。原始 ND2 已存在于同一 Shared Drive，重复复制会增加传输时间、存储消耗和版本歧义。

`dsb_v5_results/a/SOURCE_ND2_MAP.tsv` 是强制性文件，每个已归档 FOV 至少一行，建议字段为：

```text
literal_fov	source_nd2_name	source_drive_path	source_bytes	source_mtime	checksum_algorithm	source_checksum	mapping_evidence	mapping_status
```

要求：

- `literal_fov` 和 `source_nd2_name` 必须与 `more/a` 完全一致；
- `source_drive_path` 必须指向 `more/a` 中的原始文件；
- `mapping_status` 至少区分 `confirmed` 和 `unmapped_review`；
- 如果尚未安全计算 ND2 checksum，可以记录 `not_computed`，但不得伪造校验值；
- 后续确需复制 ND2 时，必须另行批准，并放入明确的 `nd2_copy/` 区域，不能改变原始文件，也不能取代本映射表。

## 6. 必须归档的产物

每个已确认映射并进入正式归档的 v5 样本，应按实际产出包括以下内容；不存在的产物要在 manifest 中标记为缺失或不适用，不能伪造：

1. **TIFF**：实际用于 v5 的 cell/crop TIFF、必要的校正 TIFF、channel TIFF、mask TIFF 和用于本地审阅的关键可视化 TIFF；
2. **轨迹**：最终选择轨迹、候选轨迹、逐通道轨迹、baseline/longest 轨迹及其索引；
3. **QC**：定位、轨迹长度、gap、完整 GPR、异常跳跃、失败样本和人工审阅所需的表格或图；
4. **manifests**：输入清单、参数、软件版本、运行 ID、sample/cell/FOV 映射、结果文件清单；
5. **audit**：完整性检查、数量检查、checksum、rclone 日志、失败与重试记录；
6. **报告**：逐样本结果、汇总统计、已知限制和未解决问题；
7. **metadata**：原始 metadata 的逐字节副本，以及在需要时单独生成的 Drive 路径适配副本。

不得只上传最终一张图而丢弃其输入轨迹、参数和 provenance。

## 7. metadata 不可变规则

来源 metadata 和 Sherlock 生成的原始 metadata 都是不可变证据：

1. 原件只能复制，不能原地编辑；
2. 原始 metadata 的文件名、内容、大小和校验值必须记录在 `ARCHIVE_MANIFEST.tsv`；
3. metadata 中的 `/scratch/...` 或旧本地绝对路径即使在 Drive 上不可直接使用，也必须保留；
4. 若本地审阅需要 Drive 可访问路径，应另建适配副本，例如：

```text
<name>_metadata.source_original.json
<name>_metadata.drive.json
```

5. 适配副本必须记录 `derived_from`、生成时间、生成脚本/版本和被替换的字段；不得冒充原件。

## 8. 映射不确定时的隔离规则

任何不能由 manifest、source path、crop metadata、明确 ID 映射或可靠校验共同确认的文件，不得进入正式 `<literal FOV>` 目录。

必须先放入：

```text
zhehao/dsb_v5_results/a/unmapped_review/<run_id>/
```

并附带至少以下字段：

```text
source_path	candidate_fov	candidate_cell	reason_unresolved	evidence	review_status
```

规则：

- `unmapped_review` 中的文件可以人工审阅，但默认不得进入生物学汇总分析；
- 只有在映射被确认、审阅者和证据被记录后，才可 copy 到正式 FOV 目录；
- 不得通过“最像的名字”或目录顺序自动认领不确定结果；
- 原隔离记录和决策审计必须保留。

## 9. `ARCHIVE_MANIFEST.tsv` 最低字段

正式归档必须维护文件级 `ARCHIVE_MANIFEST.tsv`，最低字段建议为：

```text
archive_run_id	pipeline_version	literal_fov	literal_cell_or_crop	artifact_role	source_path	destination_path	bytes	mtime	checksum_algorithm	checksum	mapping_status	transfer_status
```

其中：

- `artifact_role` 应能区分 `input_tif`、`mask_tif`、`trajectory`、`qc`、`manifest`、`audit`、`metadata_original`、`metadata_drive` 等；
- `pipeline_version` 必须写明 v5 版本和可验证的代码 snapshot；
- `transfer_status` 只能根据实际检查填写，例如 `verified`、`missing`、`failed`；
- 空文件必须显式记录，不得因大小为 0 而静默忽略。

## 10. 传输规则

1. 上传应使用新的、唯一的目标目录或 `--immutable` 等防覆盖保护；
2. 默认使用 `rclone copy`/`copyto`，不得使用会删除远端多余文件的 `sync`；
3. 上传日志写入本次 run 的 `audit/`；
4. 大量小文件可以先生成只读归档包以提高传输效率，但同时必须保留包内文件 manifest 和 checksum；
5. TIFF 应保持原始文件名和字节内容；若生成审阅版或压缩版，必须另命名并标为 derivative；
6. 任一失败任务不得被成功样本的汇总掩盖，失败列表和是否存在部分产物必须一并归档。

## 11. 验收标准

一个归档 run 只有同时满足以下条件才可标记为 `ACCEPTED`：

### 11.1 来源与命名

- `more/a` 来源目录未发生任何由归档操作导致的写入、删除、移动或重命名；
- 所有正式样本的 FOV、ND2、cell/crop 名称与来源 literal 名称一致；
- 每个正式 FOV 在 `SOURCE_ND2_MAP.tsv` 中存在唯一、可审计的确认映射；
- 所有不确定映射均位于 `unmapped_review`，且未进入正式分析汇总。

### 11.2 文件完整性

- `ARCHIVE_MANIFEST.tsv` 中所有 `transfer_status=verified` 的文件在 Drive 目标存在；
- 源与目标文件数符合 manifest，未解释的缺失、额外或重复文件数为 0；
- 源与目标大小一致；
- 可用时 checksum 一致，`rclone check` 或等价检查报告为 0 differences；
- 原始 metadata 的校验值与归档副本一致；
- TIFF、轨迹、QC、manifests 和 audit 的必需类别均已出现，或有明确的 `not_applicable`/`missing` 解释。

### 11.3 可追溯性与可复现性

- 归档记录 pipeline 版本、代码 snapshot、运行参数、run ID 和 Sherlock 来源路径；
- 任意最终轨迹或图表都能追溯到具体 TIFF、cell/crop、FOV 和原始 ND2 映射；
- Drive 路径适配 metadata 能明确追溯到未修改的原始 metadata；
- 失败、重试、排除和人工决策均有日志或 audit 表。

### 11.4 验收输出

每次归档至少产生：

```text
ARCHIVE_MANIFEST.tsv
SOURCE_ND2_MAP.tsv
ARCHIVE_AUDIT/transfer.log
ARCHIVE_AUDIT/check_report.txt
ARCHIVE_AUDIT/acceptance_summary.txt
```

`acceptance_summary.txt` 必须明确给出：

```text
SOURCE_MUTATION_DETECTED=NO
UNEXPLAINED_MISSING_FILES=0
UNEXPLAINED_EXTRA_FILES=0
CHECKSUM_DIFFERENCES=0
UNRESOLVED_FILES_IN_FORMAL_RESULTS=0
ARCHIVE_ACCEPTED=YES
```

任何一项不能证实时，必须填写真实状态并将 `ARCHIVE_ACCEPTED` 设为 `NO`；不得为通过门槛而补造结果或删除失败证据。

## 12. 当前明确禁止的操作

- 修改或整理 `more/a`；
- 以新结果覆盖旧结果；
- 默认复制全部 ND2；
- 将 `/scratch` metadata 原地改写为 `G:\...`；
- 把未确认映射样本纳入正式生物学结论；
- 仅凭文件名相似度推断 FOV/cell；
- 在缺少文件或校验失败时声称归档完成。

