# OligoLiveFish v5 轨迹延长开发计划

## 原则

- 每轮只改一个可解释模块。
- v4 输入与输出保持只读。
- 轨迹变长必须同时满足 identity/空间误差非劣。
- 开发 FOV 与验证 FOV 分开；验证结果不能反向调参。

## 阶段

| 阶段 | 唯一改动 | 当前状态 |
|---|---|---|
| dev1 | 全局空帧边界改为 `missing_frames > trackMem` 才切段 | 本地合成测试通过 |
| dev2 | actual timestamp + gap-scaled radius | 未开始 |
| dev3 | 稳健逐帧或 bleaching-normalized threshold | 未开始 |
| dev4 | 邻近峰分离诊断与候选检测改进 | 未开始 |
| dev5 | 有界动态 ROI | 低优先级，未开始 |
| dev6 | 无竞争、非重叠片段的保守 stitching | 最后考虑 |

## dev1 验收顺序

1. 本地 source-contract 与 MATLAB 合成回归；
2. Sherlock 10–20 个代表性 TIFF smoke test；
3. 人工审阅轨迹 overlay；
4. 219 个 exact-pixel TIFF benchmark；
5. 在锁定参数下比较 v4/v5 的长度与真实性指标；
6. dev1 通过后才进入 dev2。

## dev1 成功条件

- 轨迹点数或 frame span 有实质增加；
- 新恢复点集中在原 gap 两侧，而非远距离背景点；
- gap 后第一步位移不出现异常长尾；
- identity-switch proxy 不恶化；
- common-frame RMSE/MAE 不恶化到预先约定界限之外；
- 完整 GPR yield 不以明显错误连接为代价；
- GP/PR/GR distance、MSCD 等下游指标不出现明显非物理漂移。
