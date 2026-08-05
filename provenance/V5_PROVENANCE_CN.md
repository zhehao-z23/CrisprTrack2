# OligoLiveFish v5 开发来源与实验边界

记录日期：2026-07-29  
当前版本：`5.0.0-dev1-trackmem-global-gap`

## 1. 来源

v5 从以下本地只读来源建立：

`D:\UGVR\Stanley\Genomic DNA Dynamics Predict Chromatin Density\code\OligoLiveFish-ML-ZZH-v4.2-candidate-qc`

来源状态：

- Git commit：`833515ee7a3da2ced4b34925c85107d54c006918`
- branch：`feature/v4.2.2-convex-hull-roi`
- `git status --short`：空，来源 worktree 干净
- 来源 `VERSION`：`4.2.2-convex-hull-roi`
- 复制时排除 `.git`、`__pycache__` 与 `*.pyc`
- 纳入复制的文件：1,151
- 总字节数：168,674,707
- v4.2 来源目录未被修改

关键来源文件的 SHA256 见
[`V5_BASELINE_MANIFEST.csv`](V5_BASELINE_MANIFEST.csv)。

## 2. dev1 唯一算法改动

旧版 `spt_track.m` 使用：

```matlab
jump = find(t_posnew);
```

即任何全局空检测帧都会在调用 `track.m` 之前切断 detection table。

dev1 改为：

```matlab
jump = find(t_posnew > param.mem);
```

其中 `t_posnew` 是相邻检测时刻之间的全局缺失帧数，`param.mem` 直接来自
`sptpara.trackMem`。因此：

- `trackMem=0`：与 v4.2 一致，任意全局空帧都切段；
- `trackMem=1`：允许跨 1 个全局空帧；
- `trackMem=2`：允许跨不超过 2 个全局空帧；
- 缺失帧数大于 `trackMem`：仍然切段。

不能直接删除全部预切段。当前 legacy `track.m` 按“具有检测的 unique time”
迭代，而不是按绝对 frame grid 迭代；若完全删除边界，会把相距任意多帧的两个
检测时刻当成相邻时刻，产生不受 `trackMem` 控制的误连。

## 3. 本阶段明确没有修改

- `sptpara.trackMem` 的配置值；
- `max_disp` 和其物理校准；
- detection threshold；
- 局部峰检测或 Gaussian fitting；
- tube/convex-hull ROI；
- minimum trajectory length；
- longest-only baseline selection；
- fragment stitching；
- timestamp-aware linking；
- gap-scaled search radius。

dev1 对允许的 gap 仍使用原固定 `max_disp`。timestamp 与 gap-scaled radius
属于下一项独立消融实验，不能与当前结果混合解释。

三个现有 trajectory runner 文件名为了兼容仍保留 `_v4.py`，但其 `VERSION`
元数据已统一更新为 `v5.0.0-dev1-trackmem-global-gap`。这只修复输出 manifest
身份，不改变 runner 参数或输出目录结构。

## 4. 本地验证

环境：

- Windows
- Python 3.12.11：`D:\MSYS2\ucrt64\bin\python.exe`
- MATLAB 25.2.0.3042426，R2025b Update 1

运行：

```powershell
.\tests\run_v5_local_tests.cmd
```

通过的测试：

1. dependency-free Python source/version contract；
2. 既有 MATLAB empty/single-track regression；
3. v5 MATLAB global-gap runtime regression：
   - `trackMem=0` 保留 v4 切段行为；
   - 1 个空帧在 `trackMem=1` 时续接；
   - 2 个空帧在 `trackMem=1` 时保持切断；
   - 2 个空帧在 `trackMem=2` 时续接；
   - production default `trackMem=3` 的两侧边界均通过；
   - 两条空间分离的竞争轨迹跨允许 gap 后仍保持两个身份；
   - 同一 detection table 中允许 gap 被保留、超界 gap 仍正确切成两条轨迹。
4. 临时 TIFF integration：
   - 运行真实 `spt_batch`；
   - 使用原 first-frame threshold、band-pass、peak detection 与 Gaussian fit；
   - 第 4 帧全局无检测；
   - 最终恢复帧 1/2/3/5/6/7 的单条轨迹。
5. 同一临时 TIFF 的 v4.2/v5 端到端对照：
   - detection 输入、threshold、`trackMem=3`、`max_disp=2 px` 完全相同；
   - v4.2 被切成不能通过原长度规则的短片段；
   - v5 恢复一条 6-point trajectory；
   - 标志：`V42_V5_SPT_BATCH_GAP_CONTROL_OK`。

最终标志：`V5_LOCAL_TESTS_OK`

额外 v4.2 对照确认：同一份“1 个全局空帧、`trackMem=1`”合成输入在 v4.2
仍被切成短片段，输出标志为 `V42_GLOBAL_GAP_SPLIT_CONFIRMED`。

## 5. 已知的既有本地测试限制

在修改 v5 之前，对 v4.2 执行全套 Python `unittest` 时已观察到：

- 当前 MSYS2 Python 缺少 `tifffile`，导致 3 个模块无法导入；
- `test_spt_analysis_packaging.py` 有 1 个 Windows 路径分隔符断言失败。

这些是 v4.2 基线环境/跨平台问题，不是 dev1 gap 修复导致。本阶段没有为了
让测试变绿而顺带修改依赖、打包逻辑或路径合同。

## 6. 进入真实数据前的限制

合成测试只能证明边界逻辑正确，不能证明真实轨迹更准确。下一步必须：

1. 在 Sherlock 使用与历史 v4 相同的 MATLAB/Fiji 环境；
2. 先跑包含 global empty frame、P/R 短轨迹和竞争 allele 的小样本；
3. 所有新输出写入独立目录，不覆盖 v4；
4. 同时比较长度、frame span、异常跳跃、gap 后第一步、identity switch proxy、
   common-frame RMSE 和完整 GPR yield；
5. 小样本通过后，才运行 219 个 exact-pixel TIFF benchmark。

Sherlock 的独立 worktree、overlay 校验、合成测试和真实 TIFF smoke-test
操作顺序见
[`../deployment/README_SHERLOCK_CN.md`](../deployment/README_SHERLOCK_CN.md)。
