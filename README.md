# 竹迫研 ロボット：Arduino × THINKLET Cube フィジカルAI

## 最終目標

Arduino（basic robokit2）とTHINKLET Cubeを連携させてフィジカルAIを作る。
具体的なAI機能、両機器間の通信方式、実機動作の完了条件は今後決める。

## ファイル管理

[GitHub: MamoruKomo/physicalAI_thinklet](https://github.com/MamoruKomo/physicalAI_thinklet)でコード・設計・検証記録を管理する。
機器固有のシリアルやローカル設定は `config/devices.local.json` に保存し、Gitには含めない。
認証情報・APIキーはGitに含めない。

## 接続確認（2026-10-07・日本時間）

| 対象 | Macで確認した状態 |
| --- | --- |
| Arduino / basic robokit2 | USB認識あり。Arduino / Generic CDC、VID:PID `2341:0043`、シリアルポート `/dev/cu.usbmodem1101`。 |
| THINKLET Cube | USB認識あり。QUALCOMM / SDM450-QRD、VID:PID `05c6:90b8`。 |
| THINKLET Cubeの開発用ADB通信 | 接続成功。対象シリアルを指定した `adb get-state` は `device`。モデル `THINKLET LC02`、Android `8.1.0`、Fairy OS `15.000.0`。対象を指定した `getprop` の応答を確認。 |
| ArduinoとTHINKLET Cube間の通信・動作 | 未確認。Macに両機器が接続されていることと、両機器間の連携は別の検証。 |

## 次の確認

1. 実現したいAI機能と実機動作の完了条件を決める。
2. 両機器間の通信方式を決める。
3. Arduinoの書き込み・通信確認とTHINKLET Cube側のアプリ開発を進め、連携動作を検証する。

ADB操作時は対象シリアルを必ず指定する。

## 公式資料

- [THINKLETの起動とUSB接続](https://fairydevicesrd.github.io/thinklet.app.developer/docs/startGuide/useCamera/)
- [THINKLET Cube開発ガイドライン](https://fairydevicesrd.github.io/thinklet.app.developer/docs/devGuide/thinkletCube/)
- [THINKLET Cube LC-02取扱説明書](https://static-connected-worker.thinklet.fd.ai/support/tl-cube/ja/)
