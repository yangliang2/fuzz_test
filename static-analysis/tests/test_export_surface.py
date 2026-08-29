"""export_surface 的单元测试 + 对真实 DDG APK 的 golden test。

golden test 依赖：
- APK：环境变量 DDG_APK，缺省取 ~/project/duckduckgo-android/app/build/outputs/apk/internal/debug/*.apk
- aapt：环境变量 AAPT，缺省取 $ANDROID_HOME/build-tools 下最新版本
两者缺一则 skip。
"""

import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from export_surface import dump_xmltree, find_aapt, parse_xmltree  # noqa: E402

FIXTURE = """\
N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=2)
    A: android:versionCode(0x0101021b)=(type 0x10)0x327cce0
    A: android:versionName(0x0101021c)="5.294.0" (Raw: "5.294.0")
    A: package="com.example.debug" (Raw: "com.example.debug")
    E: uses-sdk (line=11)
      A: android:minSdkVersion(0x0101020c)=(type 0x10)0x1c
    E: application (line=100)
      A: android:label(0x01010001)=@0x7f140092
      E: activity (line=110)
        A: android:name(0x01010003)="com.example.FooActivity" (Raw: "com.example.FooActivity")
        A: android:exported(0x01010010)=(type 0x12)0xffffffff
        E: intent-filter (line=112)
          E: action (line=113)
            A: android:name(0x01010003)="android.intent.action.VIEW" (Raw: "android.intent.action.VIEW")
          E: category (line=115)
            A: android:name(0x01010003)="android.intent.category.BROWSABLE" (Raw: "android.intent.category.BROWSABLE")
          E: data (line=117)
            A: android:scheme(0x01010027)="https" (Raw: "https")
            A: android:host(0x01010028)="example.com" (Raw: "example.com")
          E: data (line=119)
            A: android:mimeType(0x01010026)="text/plain" (Raw: "text/plain")
      E: activity (line=125)
        A: android:name(0x01010003)="com.example.BarActivity" (Raw: "com.example.BarActivity")
        A: android:exported(0x01010010)=(type 0x12)0x0
      E: activity-alias (line=130)
        A: android:name(0x01010003)="com.example.FooAlias" (Raw: "com.example.FooAlias")
        A: android:enabled(0x0101000e)=(type 0x12)0x0
        A: android:exported(0x01010010)=(type 0x12)0xffffffff
        A: android:targetActivity(0x01010202)="com.example.FooActivity" (Raw: "com.example.FooActivity")
        E: intent-filter (line=135)
          E: action (line=136)
            A: android:name(0x01010003)="android.intent.action.MAIN" (Raw: "android.intent.action.MAIN")
          E: category (line=138)
            A: android:name(0x01010003)="android.intent.category.LAUNCHER" (Raw: "android.intent.category.LAUNCHER")
      E: service (line=145)
        A: android:name(0x01010003)="com.example.FooService" (Raw: "com.example.FooService")
      E: receiver (line=150)
        A: android:name(0x01010003)="com.example.FooReceiver" (Raw: "com.example.FooReceiver")
        A: android:exported(0x01010010)=(type 0x12)0x0
        A: android:permission(0x01010006)="com.example.PERMISSION" (Raw: "com.example.PERMISSION")
      E: provider (line=155)
        A: android:name(0x01010003)="com.example.FooProvider" (Raw: "com.example.FooProvider")
        A: android:exported(0x01010010)=(type 0x12)0x0
        A: android:authorities(0x01010018)="com.example.provider" (Raw: "com.example.provider")
"""


def by_name(components, name):
    for c in components:
        if c["name"] == name:
            return c
    raise AssertionError(f"component not found: {name}")


def filter_with_action(component, action):
    for f in component["intent_filters"]:
        if action in f["actions"]:
            return f
    raise AssertionError(f"{component['name']}: no intent-filter with action {action}")


class ParseXmltreeTest(unittest.TestCase):
    def setUp(self):
        self.manifest = parse_xmltree(FIXTURE)
        self.components = self.manifest["components"]

    def test_package_and_version(self):
        self.assertEqual(self.manifest["package"], "com.example.debug")
        self.assertEqual(self.manifest["version_name"], "5.294.0")

    def test_all_component_types_collected(self):
        types = {c["name"]: c["type"] for c in self.components}
        self.assertEqual(
            types,
            {
                "com.example.FooActivity": "activity",
                "com.example.BarActivity": "activity",
                "com.example.FooAlias": "activity-alias",
                "com.example.FooService": "service",
                "com.example.FooReceiver": "receiver",
                "com.example.FooProvider": "provider",
            },
        )

    def test_exported_true_false_and_absent(self):
        self.assertIs(by_name(self.components, "com.example.FooActivity")["exported"], True)
        self.assertIs(by_name(self.components, "com.example.BarActivity")["exported"], False)
        self.assertIs(by_name(self.components, "com.example.FooService")["exported"], None)

    def test_intent_filter_contents(self):
        foo = by_name(self.components, "com.example.FooActivity")
        self.assertEqual(len(foo["intent_filters"]), 1)
        f = foo["intent_filters"][0]
        self.assertEqual(f["actions"], ["android.intent.action.VIEW"])
        self.assertEqual(f["categories"], ["android.intent.category.BROWSABLE"])
        self.assertEqual(
            f["data"],
            [
                {"scheme": "https", "host": "example.com"},
                {"mimeType": "text/plain"},
            ],
        )

    def test_alias_target_and_enabled(self):
        alias = by_name(self.components, "com.example.FooAlias")
        self.assertEqual(alias["target_activity"], "com.example.FooActivity")
        self.assertIs(alias["enabled"], False)

    def test_permission_recorded(self):
        receiver = by_name(self.components, "com.example.FooReceiver")
        self.assertEqual(receiver["permission"], "com.example.PERMISSION")

    def test_empty_intent_filters(self):
        bar = by_name(self.components, "com.example.BarActivity")
        self.assertEqual(bar["intent_filters"], [])


def default_apk():
    env = os.environ.get("DDG_APK")
    if env:
        return env if os.path.exists(env) else None
    pattern = os.path.expanduser(
        "~/project/duckduckgo-android/app/build/outputs/apk/internal/debug/*.apk"
    )
    matches = sorted(glob.glob(pattern))
    return matches[-1] if matches else None


APK = default_apk()
AAPT = find_aapt(os.environ.get("AAPT"))


@unittest.skipUnless(APK and AAPT, "需要 DDG APK 与 aapt（见模块 docstring）")
class GoldenDdgApkTest(unittest.TestCase):
    """与源码初审已知暴露面比对（docs/validation-plan-ddg-three-layer-fuzzing.md 3.1）。"""

    @classmethod
    def setUpClass(cls):
        cls.manifest = parse_xmltree(dump_xmltree(APK, AAPT))
        cls.components = cls.manifest["components"]
        # 保证产物是可 JSON 序列化的
        json.dumps(cls.manifest)

    def test_committed_json_matches_apk(self):
        """已提交的 export-surface.json 不得与 APK 漂移；重生成方式见 README。"""
        path = os.path.join(os.path.dirname(__file__), "..", "export-surface.json")
        with open(path) as f:
            self.assertEqual(json.load(f), self.manifest)

    def test_intent_dispatcher_activity(self):
        c = by_name(self.components, "com.duckduckgo.app.dispatchers.IntentDispatcherActivity")
        self.assertEqual(c["type"], "activity")
        self.assertIs(c["exported"], True)

        view = filter_with_action(c, "android.intent.action.VIEW")
        schemes = {d.get("scheme") for f in c["intent_filters"] if "android.intent.action.VIEW" in f["actions"] for d in f["data"]}
        self.assertTrue({"http", "https", "duck"} <= schemes)
        self.assertIn("android.intent.category.BROWSABLE", view["categories"])

        send = filter_with_action(c, "android.intent.action.SEND")
        self.assertIn("text/plain", {d.get("mimeType") for d in send["data"]})

        filter_with_action(c, "android.nfc.action.NDEF_DISCOVERED")

    def test_launch_bridge_and_eight_aliases(self):
        c = by_name(self.components, "com.duckduckgo.app.launch.LaunchBridgeActivity")
        self.assertIs(c["exported"], True)
        filter_with_action(c, "android.intent.action.MAIN")

        aliases = [
            x for x in self.components
            if x["type"] == "activity-alias"
            and x["target_activity"] == "com.duckduckgo.app.launch.LaunchBridgeActivity"
        ]
        self.assertEqual(len(aliases), 8, [a["name"] for a in aliases])
        for a in aliases:
            self.assertIs(a["exported"], True)
            f = filter_with_action(a, "android.intent.action.MAIN")
            self.assertIn("android.intent.category.LAUNCHER", f["categories"])

    def test_browser_activity_exported_without_filter(self):
        c = by_name(self.components, "com.duckduckgo.app.browser.BrowserActivity")
        self.assertIs(c["exported"], True)
        self.assertEqual(c["intent_filters"], [])

    def test_system_search_activity(self):
        c = by_name(self.components, "com.duckduckgo.app.systemsearch.SystemSearchActivity")
        self.assertIs(c["exported"], True)
        filter_with_action(c, "android.intent.action.ASSIST")

    def test_custom_tab_service(self):
        c = by_name(self.components, "com.duckduckgo.customtabs.impl.service.DuckDuckGoCustomTabService")
        self.assertEqual(c["type"], "service")
        self.assertIs(c["exported"], True)
        filter_with_action(c, "android.support.customtabs.action.CustomTabsService")

    def test_no_exported_receiver_or_provider(self):
        # 源码初审称 "Provider/Receiver 均 exported=false"，但仅覆盖 DDG 自有组件；
        # 合并 manifest 里 androidx 库贡献了两个 DUMP 权限（signature 级）保护的 exported receiver，
        # 列入白名单，新增 exported receiver/provider 会让本测试失败。
        KNOWN_ANDROIDX = {
            "androidx.work.impl.diagnostics.DiagnosticsReceiver",
            "androidx.profileinstaller.ProfileInstallReceiver",
        }
        exported = [
            c for c in self.components
            if c["type"] in ("receiver", "provider") and c["exported"] is True
        ]
        self.assertEqual({c["name"] for c in exported}, KNOWN_ANDROIDX)
        for c in exported:
            self.assertEqual(c["permission"], "android.permission.DUMP")


if __name__ == "__main__":
    unittest.main()
