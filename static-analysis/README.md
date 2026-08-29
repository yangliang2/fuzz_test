# static-analysis/

暴露面盘点：从构建后 APK 的合并 manifest 提取 exported 组件，产出 JSON 清单（源码审计会漏 feature 模块的合并 manifest），附 golden test。

见 `docs/validation-plan-ddg-three-layer-fuzzing.md`。

## 用法

```bash
# aapt 缺省取 $ANDROID_HOME/build-tools 下最新版本，可用 --aapt 覆盖
python3 export_surface.py <apk> -o export-surface.json
```

输出 JSON：`package` / `version_name` / `components[]`，每个组件含 `name`、`type`（activity / activity-alias / service / receiver / provider）、`exported`（`null` = 未显式声明）、`enabled`、`permission`、`target_activity`（alias）、`intent_filters`（actions / categories / data）。

`export-surface.json` 为 DDG `5.294.0` internalDebug（基线 commit 见 `docs/ddg-build-recipe.md`）的产出：216 个组件，33 个 exported。

## 测试

```bash
python3 -m unittest discover -s static-analysis/tests -v
```

含 parser 单测（内置 fixture）与对真实 APK 的 golden test（比对已知暴露面样本）。golden test 依赖 APK（`DDG_APK` 环境变量，缺省取 `~/project/duckduckgo-android/app/build/outputs/apk/internal/debug/*.apk`）与 aapt，缺一则 skip。
