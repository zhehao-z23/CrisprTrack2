# v5 dev1 Sherlock 部署与 smoke-test 交接

本说明只部署 `5.0.0-dev1-trackmem-global-gap`。不得覆盖历史 v4 worktree、
历史结果目录或原始 TIFF/ND2。

## 1. 初始化环境

```bash
PROJECT="$SCRATCH/oligolivefish_nd2_to_trajectory"

module purge
module load system git/2.45.1
module load python/3.12.1
module load matlab/R2022b
hash -r
```

## 2. 建立独立 worktree

先定位服务器上实际包含 base commit 的仓库，不能只相信目录名：

```bash
BASE_REPO="$PROJECT/code/REPLACE_WITH_AUDITED_V42_REPO"
BASE_COMMIT="833515ee7a3da2ced4b34925c85107d54c006918"
V5_REPO="$PROJECT/code/OligoLiveFish-ML-ZZH-v5-dev1"

git -C "$BASE_REPO" cat-file -e "${BASE_COMMIT}^{commit}"
git -C "$BASE_REPO" status --short
```

`status --short` 必须人工确认。若不为空，不能覆盖或清理该 worktree；应从
同一 Git object store 新建独立 worktree：

```bash
git -C "$BASE_REPO" worktree add \
  -b experiment/v5-dev1-trackmem-global-gap \
  "$V5_REPO" \
  "$BASE_COMMIT"
```

若分支已经存在，应停止并审阅，不能加 `--force`。

## 3. 应用本地 overlay

把以下文件上传到 Sherlock 的 staging 目录：

- `v5_dev1_overlay_20260729.tar.gz`
- `v5_dev1_overlay_20260729.tar.gz.sha256`

在本地仓库中可先对压缩包内每个文件重新计算字节数和 SHA256：

```bash
bash tests/verify_v5_overlay.sh
```

预期标志为 `V5_OVERLAY_ARCHIVE_OK`。然后在 Sherlock：

```bash
STAGING="$PROJECT/staging/v5_dev1_20260729"
cd "$STAGING"
sha256sum -c v5_dev1_overlay_20260729.tar.gz.sha256

tar -tzf v5_dev1_overlay_20260729.tar.gz
tar -xzf v5_dev1_overlay_20260729.tar.gz -C "$V5_REPO"

test "$(cat "$V5_REPO/VERSION")" = \
  "5.0.0-dev1-trackmem-global-gap"
git -C "$V5_REPO" status --short
```

此时 `git status` 只应出现 overlay 清单中的文件。任何额外变化都必须停止审阅。

## 4. Sherlock 合成测试

```bash
cd "$V5_REPO"
PROJECT="$PROJECT" bash tests/run_v5_sherlock_tests.sh
```

预期最终标志：

```text
V5_SHERLOCK_TESTS_OK
```

本 runner 不运行依赖本地 sibling v4 目录的
`test_v42_v5_spt_batch_gap_control.m`；该对照已在本地执行。Sherlock 的真实
v4/v5 对照将在独立结果目录中完成。

## 5. 真实 TIFF smoke test

smoke test 只能使用独立输出根目录，例如：

```bash
RUN_TAG="v5_dev1_smoke_$(date +%Y%m%dT%H%M%S)"
V5_OUTPUT="$PROJECT/work/$RUN_TAG"
mkdir -p "$V5_OUTPUT"
```

第一批建议 10–20 个 cell，必须覆盖：

- warning 中存在 1–3 个 global empty frames；
- P/R baseline 明显偏短；
- G anchor 稳定但非 anchor 通道断裂；
- 至少两个邻近 allele/竞争候选；
- 无 gap 的阴性对照。

所有样本必须同时运行 base v4.2 和 v5 dev1，且：

- 输入 TIFF 字节及 SHA256 相同；
- profile、ROI、threshold、`trackMem=3`、`max_disp` 与随机性相同；
- v4 与 v5 使用不同输出目录；
- 保存 run manifest、stdout/stderr、baseline manifest 和 QC overlay。

## 6. smoke-test 放行条件

不能只看轨迹变长。至少比较：

- points、frame span、gap 分布；
- 新恢复帧；
- gap 后第一步位移；
- 异常速度/加速度尾部；
- candidate competition 与 identity-switch proxy；
- common-frame RMSE/MAE；
- G/P/R 完整 bundle yield；
- GP/PR/GR distance 与 MSCD 是否出现非物理漂移。

只有在人工 overlay 审阅与上述指标均通过后，才能提交 219 个 exact-pixel
TIFF benchmark。dev1 未通过前，不进入 timestamp/gap-scaled radius 的 dev2。
